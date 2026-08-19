"""Phase 10 — signal engine 2단계 (qlib native fallback) smoke.

AlphaAgent류 miner가 생성하는 qlib 전체 문법(infix 등)이 ASB 평가에서
hard-invalid로 오판되지 않는지 검증한다 (IMPLEMENTATION_NOTES 구조적 제약 #4).
실행: AlphaSearchBench/ 에서 pytest tests/smoke/test_phase10_qlib_native_fallback.py
"""
import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config                     # noqa: E402
from alphasearchbench.data.signal_context import SignalContext  # noqa: E402


@pytest.fixture(scope="module")
def ctx():
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    return SignalContext(cfg)


def test_infix_formula_falls_back_to_qlib_native(ctx):
    values, valid = ctx.evaluate("($high - $low) / $close", "train")
    assert ctx.engine_used("($high - $low) / $close") == "qlib_native"
    assert valid.any()
    assert np.isfinite(values[valid]).all()


def test_function_syntax_stays_on_formula_engine(ctx):
    f = "Div(Sub($high, $low), $close)"
    v1, valid = ctx.evaluate(f, "train")
    assert ctx.engine_used(f) == "formula_engine"
    # 두 엔진의 수학적 동등성: infix == 함수형 (동일 수식)
    v2, _ = ctx.evaluate("($high - $low) / $close", "train")
    both = np.isfinite(v1) & np.isfinite(v2)
    assert both.any()
    assert np.allclose(v1[both], v2[both], rtol=0, atol=0), \
        "qlib native와 FormulaEngine의 동일 수식 결과가 다릅니다"


def test_true_eval_error_still_propagates(ctx):
    from alphasearchbench.data.qlib_provider import FormulaEvalError
    with pytest.raises(FormulaEvalError):
        ctx.evaluate("NotAnOperatorAnywhere($close, 5) +", "train")
