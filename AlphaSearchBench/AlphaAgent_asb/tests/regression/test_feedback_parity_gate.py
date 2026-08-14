"""regression — ★ Phase C evaluator parity gate (지도 원칙 1).

(1) vendored FactorBacktester == 원본 FactorBacktester (fixture formula 전수,
    AnnRet/IC 완전 동일 — verbatim 사본의 실측 확인)
(2) MiningEvaluator IC · ASB simple backtest AnnRet vs 원본 — 차이를 측정해
    표로 저장(문서화). 동일성 assert는 하지 않는다: 기본 설계가 feedback/
    diagnostics 분리이며, 이 표는 "대체 가능 여부"의 근거 자료다.

실행 비용: qlib 쿼리 다수 — Slurm 제출 가능 (사용자 허용).
"""
import importlib.util
import os
import sys
import types

import pandas as pd
import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
_REPO_ROOT = os.path.dirname(_ASB_ROOT)
for p in (_PKG_ROOT, _ASB_ROOT, os.path.join(_ASB_ROOT, "gplearn_asb"), _REPO_ROOT):
    sys.path.insert(0, p)

from alphaagent_asb.config import load_config                    # noqa: E402

# 원형 pool(alpha_agent.txt) 일부 + 정상/실패 혼합 — smoke 창(csi300)에서 평가
FIXTURES = [
    "($low - $high) / $close",
    "(2 * $close - ($high + $low) / 2) / $open",
    "$high / Ref($close, 1)",
    "WMA($low, 5) / $close",
    "Mean($close, 5) / $close",
]
START, END, MARKET = "2018-01-01", "2019-06-30", "csi300"


@pytest.fixture(scope="module")
def ctx():
    cfg = load_config(overrides={
        "market": MARKET,
        "search": {"start_date": START, "end_date": END},
    })
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    from qlib.data import D
    return cfg, D.instruments(market=MARKET)


def _load_original_backtester():
    spec = importlib.util.spec_from_file_location(
        "orig_backtester", os.path.join(_REPO_ROOT, "Alphaagent", "backtester.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FactorBacktester


def test_vendored_equals_original(ctx):
    cfg, instruments = ctx
    from alphaagent_asb.vendored_alphaagent.backtester import FactorBacktester as V
    O = _load_original_backtester()
    for f in FIXTURES:
        pv = _perf(V, f, instruments)
        po = _perf(O, f, instruments)
        pd.testing.assert_frame_equal(pv, po)   # 완전 동일 (반올림·버그 포함)


def _perf(cls, f, instruments):
    bt = cls(factor_expr=f, start_date=START, end_date=END,
             instruments=instruments, freq="day")
    bt.load_data()
    return bt.calculate_performance()


def test_mining_asb_vs_original_documented(ctx, tmp_path):
    """분리 유지 근거 표 생성 — MiningEvaluator/ASB backtest와 원본의 차이 실측."""
    cfg, instruments = ctx
    from alphaagent_asb.vendored_alphaagent.backtester import FactorBacktester as V
    from alphaagent_asb.diagnostics import DiagnosticsWithQlibFallback
    from gplearn_asb.evaluator import MiningEvaluator
    ev = DiagnosticsWithQlibFallback(MiningEvaluator(cfg))
    rows = []
    for f in FIXTURES:
        bt = V(factor_expr=f, start_date=START, end_date=END,
               instruments=instruments, freq="day")
        bt.load_data()
        perf = bt.calculate_performance().to_dict()
        diag = ev.diagnose(f)
        rows.append({
            "formula": f,
            "orig_IC_prompt": perf["IC"]["total"],
            "orig_IC_raw": float(bt.ic_series.mean()),
            "mining_signed_IC": diag["signed_train_IC"],
            "diagnostics_source": diag["diagnostics_source"],
            "abs_diff_raw": abs(float(bt.ic_series.mean()) - diag["signed_train_IC"]),
        })
    df = pd.DataFrame(rows)
    out = os.path.join(_PKG_ROOT, "out", "verification")
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, "feedback_parity_table.csv"), index=False)
    # 게이트 산출물 존재 + 진단이 실제로 채워졌는지 (infix 문법은 qlib_fallback 경유)
    assert df["orig_IC_raw"].notna().all()
    assert df["mining_signed_IC"].notna().all()
    print(df.to_string(index=False))
