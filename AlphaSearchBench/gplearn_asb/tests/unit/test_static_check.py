"""unit — [P2] static_check: 상수 접기·flag·program_size (qlib 불필요).

핵심 회귀: Greater/Less는 qlib에서 element-wise max/min이라 f(x,x)=x 항등 —
상수로 오판하면 valid 후보를 죽인다 (실측 13 run에서 101건이 이 부류).
"""
import os
import sys

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    sys.path.insert(0, _p)

from alphasearchbench.data.qlib_provider import parse_expression   # noqa: E402
from gplearn_asb.static_check import static_check                  # noqa: E402


def _check(formula):
    return static_check(parse_expression(formula))


def test_constant_identities():
    for f in ("Sub($close,$close)", "Div($open,$open)"):
        r = _check(f)
        assert r["static_invalid_reason"] == "static_invalid:constant_expression", f


def test_constant_propagation_through_ops():
    # 전 인자 상수 → 상수 (elementwise/rolling 무관)
    assert _check("Abs(Sub($close,$close))")["static_invalid_reason"] is not None
    assert _check("Mean(Div($low,$low),5)")["static_invalid_reason"] is not None
    assert _check("Add(Sub($close,$close),Div($open,$open))")["static_invalid_reason"] is not None


def test_greater_less_are_identity_not_constant():
    # qlib Greater/Less = np.maximum/minimum → f(x,x)=x (유효 신호)
    for f in ("Greater($close,$close)", "Less($volume,$volume)",
              "Mean(Greater($close,$close),5)"):
        r = _check(f)
        assert r["static_invalid_reason"] is None, f


def test_non_constant_pass():
    for f in ("$close", "Add($close,1.0)", "Sub($close,$open)",
              "Div(EMA($close,12),$vwap)"):
        assert _check(f)["static_invalid_reason"] is None, f


def test_constant_subtree_flag_only():
    r = _check("Add($close,Sub($open,$open))")
    assert r["static_invalid_reason"] is None          # 전체는 상수 아님
    assert r["static_flag_constant_subtree"] is True   # 기록만
    assert _check("Sub($close,$open)")["static_flag_constant_subtree"] is False


def test_nonstd_window_flag_only():
    # window 0 = expanding(유효), 정수 음수 아님 → flag 없음
    assert _check("Mean($close,0)")["static_flag_nonstd_window"] is False
    assert _check("Mean($close,5)")["static_flag_nonstd_window"] is False
    # 비정수 창은 flag (엔진은 유효 평가 — invalid 아님)
    assert _check("EMA($close,0.5)")["static_flag_nonstd_window"] is True
    assert _check("EMA($close,0.5)")["static_invalid_reason"] is None


def test_program_size():
    assert _check("$close")["program_size"] == 1
    assert _check("Sub($close,$open)")["program_size"] == 3
    assert _check("Mean(Sub($close,$open),5)")["program_size"] == 5
