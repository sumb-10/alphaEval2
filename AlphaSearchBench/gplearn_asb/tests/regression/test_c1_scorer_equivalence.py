"""regression — [C-1] scorer 계약의 production path 대조 (qlib 필요).

① n=1 single-factor equivalence: scorer([A]) == canonical candidate 평가
   (동일 창의 MiningEvaluator._net_sharpe + fb_fitness_value — 테스트용
   재계산 아님, 실제 production 함수 호출).
   parity: long/short membership(W), daily net return, 일평균/연환산
   turnover, AnnRet, Sharpe, fb.
② orientation source: pool CSV의 signed_train_IC가 orientation 적용 전
   raw signed train IC임을 고정 (음수 보존 + diagnose 재계산 대조).
"""
import math
import os
import sys

import numpy as np
import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WINDOW = ("2018-01-01", "2019-06-30")   # smoke와 동일 소형 창 (번들 내)
MARKET = "csi300"


@pytest.fixture(scope="module")
def evaluator():
    import yaml
    from gplearn_asb.config import Config, DEFAULT_CONFIG_PATH
    with open(DEFAULT_CONFIG_PATH) as fh:
        base = yaml.safe_load(fh) or {}
    cfg = Config({
        "dataset": base.get("dataset", {}),
        "market": MARKET,
        "search": {"start_date": WINDOW[0], "end_date": WINDOW[1]},
        "label": {"horizon": 1, "tail_exclusion": True},
        "gp": {"fitness_metric": "fb_fitness", "static_gate": True},
        "constraint": {"mode": "strict_penalty"},
        "backtest": {"transaction_cost_rate": 0.0015,
                     "long_short_quantile": 0.2},
    })
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    import qlib
    qlib.init = lambda *a, **k: None
    from gplearn_asb.evaluator import MiningEvaluator
    return MiningEvaluator(cfg)


# Sub(a,b) = −Sub(b,a) — 역순 쌍 포함으로 어떤 창에서든 음수 sic 보장
FORMULAS = ["Div($close, Mean($close, 12))", "Sub($open, $close)",
            "Sub($close, $open)", "Std($change, 12)", "Delta($vwap, 5)",
            "Delta($close, 12)", "Sub($vwap, $close)", "Sub($close, $vwap)"]


def _sic(evaluator, f):
    return float(evaluator.diagnose(f)["signed_train_IC"])


def test_n1_equivalence_full_chain(evaluator):
    from gplearn_asb.cli import V2_FB_MIN_ANNUAL_TURNOVER
    from gplearn_asb.fitness import fb_fitness_value
    from gplearn_asb.validation_scorer import (combine_pool_signals,
                                               score_pool, train_signs)
    checked = 0
    for f in FORMULAS:
        sic = _sic(evaluator, f)
        if math.isnan(sic):
            continue
        sign = 1 if sic >= 0 else -1
        sig = evaluator.engine.compute(f, evaluator.search_start,
                                       evaluator.search_end)
        # --- production candidate path (동일 함수, 재계산 아님) ---
        ns_p, st_p = evaluator._net_sharpe(sig, sign, return_weights=True)
        fb_p = fb_fitness_value(ns_p, st_p["net_ann_ret_arith"],
                                st_p["mean_daily_turnover_oneway"],
                                min_annual_turnover=V2_FB_MIN_ANNUAL_TURNOVER)
        # --- scorer path (n=1 pool) ---
        valid = np.isfinite(sig) & evaluator.universe_mask
        combined, _ = combine_pool_signals([sig], [valid], [sign])
        ns_s, st_s = evaluator._net_sharpe(combined, 1, return_weights=True)
        # membership + 가중치 (일별 포트폴리오 구성원 완전 일치)
        assert (np.abs(st_p["weights"]) > 0).sum() > 0     # 비어있지 않음
        assert np.allclose(st_p["weights"], st_s["weights"], atol=1e-12)
        # daily net return 시계열
        assert np.allclose(st_p["net_daily"], st_s["net_daily"], atol=1e-12)
        # turnover 일평균 ↔ 연환산 연결
        assert abs(st_p["mean_daily_turnover_oneway"]
                   - st_s["mean_daily_turnover_oneway"]) < 1e-12
        assert abs(st_p["mean_daily_turnover_oneway"] * 252
                   - st_s["mean_daily_turnover_oneway"] * 252) < 1e-9
        # AnnRet·Sharpe·fb
        assert abs(st_p["net_ann_ret_arith"] - st_s["net_ann_ret_arith"]) < 1e-9
        assert abs(ns_p - ns_s) < 1e-9
        # score_pool 공개 API도 동일 결과
        res = score_pool(evaluator, [f], [sic], pool_size=1)
        assert res["integrity_pass"]
        if math.isnan(fb_p):
            assert math.isnan(res["pool_fb"])
        else:
            assert abs(res["pool_fb"] - fb_p) < 1e-9
        assert abs(res["net_sharpe"] - ns_p) < 1e-9
        checked += 1
    assert checked >= 3                                    # 대조 표본 보장


def test_orientation_source_is_raw_signed_ic(evaluator):
    """pool CSV의 signed_train_IC == diagnose raw 값 (음수 보존)."""
    from gplearn_asb.hof import build_pool_rows
    sics = {f: _sic(evaluator, f) for f in FORMULAS}
    usable = {f: v for f, v in sics.items() if not math.isnan(v)}
    assert any(v < 0 for v in usable.values()), \
        f"음수 train IC fixture 없음 — 표본 교체 필요: {usable}"
    thresholds = {"min_mean_daily_coverage_ratio": 0.05,
                  "min_median_daily_n_valid": 30,
                  "min_valid_day_ratio": 0.90}
    rows = build_pool_rows(list(usable), evaluator, "strict_penalty",
                           thresholds, -1e6, 0, "test_c1")
    for row in rows:
        f = row["formula"]
        assert abs(float(row["signed_train_IC"]) - usable[f]) < 1e-12
    neg = [r for r in rows if float(r["signed_train_IC"]) < 0]
    assert neg, "pool 행에서 음수 signed_train_IC가 보존되어야 함"
