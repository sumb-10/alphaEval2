"""Phase 1 smoke: FormulaEngine / SignalContext / Validity Gate.

- synthetic 6종 validity 판정
- silent fallback 제거 확인 (실패 formula → FormulaEvalError)
- 기존 TensorEvaluator(reference — 테스트 전용 import)와 numerical equivalence
- SignalContext: split 컨텍스트 + train_sign 복원

주의: qlib 패널 로드 때문에 수 분 소요.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHAEVAL_ROOT = os.path.dirname(ASB_ROOT)
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config                       # noqa: E402
from alphasearchbench.validity.evaluator import ValidityGate      # noqa: E402
from alphasearchbench.validity.metrics import compute_validity_stats  # noqa: E402
from alphasearchbench.data.qlib_provider import FormulaEvalError  # noqa: E402


# ---------------------------------------------------------------- synthetic
def _uni(T=30, N=50):
    return np.ones((T, N), dtype=bool)


def _gate(cfg_overrides=None):
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"),
                      overrides=cfg_overrides)
    return ValidityGate(cfg)


def test_validity_normal_factor():
    rng = np.random.default_rng(0)
    vals = rng.normal(size=(30, 50)).astype(np.float32)
    rep = _gate().assess("normal", vals, _uni())
    assert rep.hard_valid and rep.passes_gate
    assert rep.stats["valid_day_ratio"] == 1.0
    assert rep.stats["nan_cell_ratio"] == 0.0


def test_validity_constant_factor():
    vals = np.full((30, 50), 3.14, dtype=np.float32)
    rep = _gate().assess("const", vals, _uni())
    assert not rep.hard_valid
    assert rep.invalid_reason == "no_correlatable_day"
    assert rep.stats["const_day_ratio"] == 1.0


def test_validity_all_nan_factor():
    vals = np.full((30, 50), np.nan, dtype=np.float32)
    rep = _gate().assess("allnan", vals, _uni())
    assert not rep.hard_valid
    assert rep.invalid_reason == "all_nonfinite"
    assert rep.stats["nan_cell_ratio"] == 1.0


def test_validity_mostly_nan_factor():
    rng = np.random.default_rng(1)
    vals = np.full((30, 50), np.nan, dtype=np.float32)
    vals[:, :3] = rng.normal(size=(30, 3))       # 6% coverage
    rep = _gate().assess("sparse", vals, _uni())
    assert rep.hard_valid                          # 수학적으로는 정의 가능
    assert rep.stats["mean_daily_coverage_ratio"] == pytest.approx(0.06)
    # strict + threshold면 게이트됨
    strict = _gate({"validity": {"mode": "strict",
                                 "min_mean_daily_coverage_ratio": 0.5}})
    rep2 = strict.assess("sparse", vals, _uni())
    assert rep2.hard_valid and not rep2.research_pass and not rep2.passes_gate


def test_validity_inf_factor():
    rng = np.random.default_rng(2)
    vals = rng.normal(size=(30, 50)).astype(np.float32)
    vals[::3, ::5] = np.inf
    rep = _gate().assess("inf", vals, _uni())
    assert rep.hard_valid                          # inf는 invalid cell로 제외될 뿐
    assert rep.stats["inf_cell_ratio"] > 0
    assert rep.stats["mean_daily_coverage_ratio"] < 1.0


def test_validity_eval_error():
    rep = _gate().report_eval_failure("Bogus($close, 5)", "eval_error:unknown_operator:Bogus")
    assert not rep.hard_valid and not rep.passes_gate
    assert rep.to_row()["formula_eval_failed"] is True
    assert rep.invalid_reason.startswith("formula_eval_failed:")


# ---------------------------------------------------------------- 실데이터
@pytest.fixture(scope="module")
def ctx():
    from alphasearchbench.data.signal_context import SignalContext
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    return SignalContext(cfg)


def test_engine_no_silent_fallback(ctx):
    """평가 불가 수식은 반드시 FormulaEvalError — silent 성공/대체 신호 금지.

    signal engine 2단계(NOTES 구조적 제약 #4) 도입 후: FormulaEngine의
    unknown_operator는 qlib native로 재시도되고, qlib도 못 읽으면
    eval_error:qlib_native:* 로 전파된다 — 어느 경로든 raise가 계약이다.
    """
    with pytest.raises(FormulaEvalError) as ei:
        ctx.evaluate("ThisFunctionDoesNotExist($close, 5)", "test")
    assert ("unknown_operator" in str(ei.value)) or ("qlib_native" in str(ei.value))


def test_engine_equivalence_with_reference(ctx):
    """reference(TensorEvaluator, AlphaEval scripts — 테스트 전용 import)와
    float32 비트 단위 일치."""
    sys.path.insert(0, os.path.join(ALPHAEVAL_ROOT, "scripts"))
    import qlib
    _orig = qlib.init
    qlib.init = lambda *a, **k: None      # 이미 초기화됨 — reference의 재-init 차단
    try:
        from tensor_eval import TensorEvaluator
        start, end = ctx.splits_cfg["test"]
        tev = TensorEvaluator(start, end, market=ctx.market)
    finally:
        qlib.init = _orig
    # 패널 warmup 구간이 달라 컬럼 집합이 다를 수 있음(2005-2015 상장폐지 종목).
    # 공통 컬럼에서 값을 비교한다 — 공유 종목의 값은 비트 단위 일치해야 함.
    ours_cols = set(ctx.engine.columns)
    common = [c for c in tev.columns if c in ours_cols]
    assert len(common) >= 3000
    ref_ix = [tev.columns.get_loc(c) for c in common]
    our_ix = [ctx.engine.columns.get_loc(c) for c in common]
    for f in ["Mean($close, 30)", "Kurt($close, 64)", "WMA($close, 12)",
              "Power(Resi($high, 30), Slope($close, 12))",
              "Sub(Std(Div($high, $low), 12), Mean($close, 5))"]:
        ours = ctx.engine.compute(f, start, end)[:, our_ix]
        ref = tev.frame(f).to_numpy()[:, ref_ix]
        both_nan = np.isnan(ours) & np.isnan(ref)
        assert bool(((ours == ref) | both_nan).all()), f"mismatch: {f}"


def test_signal_context_and_train_sign(ctx):
    values, valid = ctx.evaluate("Mean($close, 30)", "test")
    assert values.shape == valid.shape
    assert valid.sum() > 0
    signed = ctx.signed_ic_on_train("Mean($close, 30)")
    assert np.isfinite(signed)
    sign = 1 if signed >= 0 else -1
    oriented = ctx.oriented(values, sign)
    assert oriented.shape == values.shape
    # regime 캘리브레이션은 train에서 freeze
    assert ctx.regime["vol_low_threshold"] < ctx.regime["vol_high_threshold"]


def test_combined_signal(ctx):
    combo, mask = ctx.combined_signal(
        ["Mean($close, 30)", "Std($high, 12)"], [0.7, -0.3], "test")
    assert combo.shape == mask.shape
    assert np.isfinite(combo).all()      # z-score 결측은 0
