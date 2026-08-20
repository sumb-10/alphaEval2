"""unit — [B] 신뢰도 fitness 계열: ic_tstat 손계산·B2 조건 경계·fb_fitness·too_long."""
import math
import os
import sys
import types

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    sys.path.insert(0, _p)

from gplearn_asb.evaluator import MiningEvaluator, _ic_tstat        # noqa: E402
from gplearn_asb.fitness import apply_constraint, fb_fitness_value  # noqa: E402

TH = {"min_mean_daily_coverage_ratio": 0.05,
      "min_median_daily_n_valid": 30, "min_valid_day_ratio": 0.90}


def _diag(**over):
    d = {"formula": "f", "signed_train_IC": 0.05, "abs_train_IC": 0.05,
         "ic_tstat": float("nan"), "eval_failed": False, "hard_invalid": False,
         "invalid_reason": None, "n_ic_obs": 100,
         "mean_daily_coverage_ratio": 0.9, "median_daily_n_valid": 500,
         "valid_day_ratio": 1.0}
    d.update(over)
    return d


# ---------------------------------------------------------------- ic_tstat
def test_daily_ic_returns_std_handcalc():
    """T=4일, 일별 r을 손계산 → 3-튜플 (ic, n, std ddof=1) 대조."""
    ev = types.SimpleNamespace(
        label=np.array([[0.01, 0.02, 0.03, 0.04],
                        [0.04, 0.03, 0.02, 0.01],
                        [0.01, 0.02, 0.03, 0.04],
                        [0.01, 0.02, 0.03, 0.04]], dtype=np.float32),
        universe_mask=np.ones((4, 4), dtype=bool))
    F = np.array([[1, 2, 3, 4]] * 4, dtype=np.float32)
    ic, n, std = MiningEvaluator._daily_ic(ev, F)
    r = np.array([1.0, -1.0, 1.0, 1.0])     # 일별 Pearson (완전 상관)
    assert n == 4
    assert abs(ic - r.mean()) < 1e-9
    assert abs(std - r.std(ddof=1)) < 1e-9


def test_ic_tstat_handcalc_and_guards():
    assert abs(_ic_tstat(0.05, 100, 0.2) - 0.05 / (0.2 / 10)) < 1e-12
    assert math.isnan(_ic_tstat(0.05, 1, 0.2))       # n<2
    assert math.isnan(_ic_tstat(0.05, 100, 0.0))     # std=0
    assert math.isnan(_ic_tstat(0.05, 100, float("nan")))


def test_ic_tstat_metric_effective_and_nan_worst():
    d = _diag(ic_tstat=2.5)
    info = apply_constraint("strict_penalty", d, TH, -1.0, 0.03,
                            fitness_metric="ic_tstat")
    assert info["raw_fitness"] == 2.5 and info["effective_fitness"] == 2.5
    d = _diag(ic_tstat=float("nan"))
    info = apply_constraint("strict_penalty", d, TH, -1.0, 0.03,
                            fitness_metric="ic_tstat")
    assert info["effective_fitness"] == -1.0
    assert info["invalid_reason"] == "fitness_undefined:ic_tstat_nan"


# ---------------------------------------------------------------- B2 조건
def _ns_diag(ntd, signed=0.05, ns=1.5):
    return _diag(signed_train_IC=signed, abs_train_IC=abs(signed),
                 net_sharpe=ns, n_traded_days=ntd,
                 net_ann_ret_arith=0.1, mean_daily_turnover_oneway=0.01)


def test_min_traded_days_boundary():
    opts = {"net_sharpe_min_traded_days": 252}
    ok = apply_constraint("strict_penalty", _ns_diag(252), TH, -1e6, 0.03,
                          fitness_metric="net_sharpe", fitness_opts=opts)
    assert ok["effective_fitness"] == 1.5            # 경계값 >= → pass
    assert not ok["fitness_condition_failed"]
    bad = apply_constraint("strict_penalty", _ns_diag(251), TH, -1e6, 0.03,
                           fitness_metric="net_sharpe", fitness_opts=opts)
    assert bad["effective_fitness"] == -1e6
    assert bad["invalid_reason"] == "fitness_undefined:insufficient_traded_days"
    assert bad["raw_fitness"] == 1.5                 # 스펙 #19: raw 보존


def test_min_abs_ic_boundary():
    opts = {"net_sharpe_min_abs_ic": 0.01}
    ok = apply_constraint("strict_penalty", _ns_diag(300, signed=-0.01), TH,
                          -1e6, 0.03, fitness_metric="net_sharpe", fitness_opts=opts)
    assert ok["effective_fitness"] == 1.5            # |−0.01| >= 0.01 pass
    bad = apply_constraint("strict_penalty", _ns_diag(300, signed=0.009), TH,
                           -1e6, 0.03, fitness_metric="net_sharpe", fitness_opts=opts)
    assert bad["effective_fitness"] == -1e6
    assert bad["invalid_reason"] == "fitness_undefined:ic_below_floor"


def test_conditions_ignore_hard_invalid():
    d = _ns_diag(10)
    d.update({"hard_invalid": True, "invalid_reason": "all_nonfinite"})
    info = apply_constraint("strict_penalty", d, TH, -1e6, 0.03,
                            fitness_metric="net_sharpe",
                            fitness_opts={"net_sharpe_min_traded_days": 252})
    assert info["invalid_reason"] == "all_nonfinite"  # hard 사유가 우선
    assert not info["fitness_condition_failed"]


# ---------------------------------------------------------------- fb_fitness
def test_fb_fitness_handcalc():
    # ns=2, annret=0.126, 일평균 turnover 0.001 → ann 0.252 → 2*sqrt(0.5)
    v = fb_fitness_value(2.0, 0.126, 0.001)
    assert abs(v - 2.0 * math.sqrt(0.126 / 0.252)) < 1e-12
    assert math.isnan(fb_fitness_value(2.0, 0.1, 0.0))          # turnover 0
    assert math.isnan(fb_fitness_value(float("nan"), 0.1, 0.01))
    assert fb_fitness_value(-1.0, 0.126, 0.001) < 0             # 부호는 ns 따름


def test_fb_metric_wiring_and_nan_worst():
    d = _ns_diag(300)
    info = apply_constraint("strict_penalty", d, TH, -1e6, 0.03,
                            fitness_metric="fb_fitness")
    expect = fb_fitness_value(1.5, 0.1, 0.01)
    assert abs(info["raw_fitness"] - expect) < 1e-12
    assert info["effective_fitness"] == info["raw_fitness"]
    d2 = _ns_diag(300)
    d2["mean_daily_turnover_oneway"] = 0.0
    info2 = apply_constraint("strict_penalty", d2, TH, -1e6, 0.03,
                             fitness_metric="fb_fitness")
    assert info2["effective_fitness"] == -1e6
    assert info2["invalid_reason"] == "fitness_undefined:fb_fitness_nan"


def test_fb_turnover_floor_param_mechanism():
    """[③] min_annual_turnover 파라미터: 기본 0.0 = legacy 의미론 불변,
    명시 floor 아래 연회전 → NaN. (canonical 값 자체는 별도 승인 사항 —
    여기서는 메커니즘만 고정.)"""
    # ann_turn = 0.005 (일평균 0.005/252): 기본값에서는 유한 (legacy 불변)
    tiny = 0.005 / 252.0
    v_legacy = fb_fitness_value(1.0, 0.1, tiny)
    assert math.isfinite(v_legacy)
    # 동일 입력 + floor 0.01 → NaN (floor 미달)
    assert math.isnan(fb_fitness_value(1.0, 0.1, tiny, min_annual_turnover=0.01))
    # floor 바로 위(ann 0.011)는 유한
    assert math.isfinite(fb_fitness_value(1.0, 0.1, 0.011 / 252.0,
                                          min_annual_turnover=0.01))
    # 경계값: ann_turn == floor → 통과 (value >= threshold 규약과 일관)
    assert math.isfinite(fb_fitness_value(1.0, 0.1, 0.01 / 252.0,
                                          min_annual_turnover=0.01))


def test_fb_finite_guarantee():
    """[③] 반환값 finite 보장 — 구성값이 유한해도 곱이 overflow하면 NaN."""
    v = fb_fitness_value(1e308, 1e308, 1e-9)
    assert math.isnan(v)                      # inf로 새지 않음
    # 정상 범위에서는 물론 유한
    assert math.isfinite(fb_fitness_value(2.0, 0.126, 0.001))


def test_fb_floor_wiring_in_apply_constraint():
    """[③] fitness_opts.fb_min_annual_turnover 배선: floor 미달 → worst +
    사유 기록. opts 미지정 시 동일 diag가 유한 raw (legacy 경로 불변)."""
    d = _ns_diag(300)
    d["mean_daily_turnover_oneway"] = 0.005 / 252.0     # ann 0.005
    base = apply_constraint("strict_penalty", d, TH, -1e6, 0.03,
                            fitness_metric="fb_fitness")
    assert math.isfinite(base["raw_fitness"])           # 기본 = floor 없음
    info = apply_constraint("strict_penalty", dict(d), TH, -1e6, 0.03,
                            fitness_metric="fb_fitness",
                            fitness_opts={"fb_min_annual_turnover": 0.01})
    assert math.isnan(info["raw_fitness"])
    assert info["effective_fitness"] == -1e6
    assert info["invalid_reason"] == "fitness_undefined:fb_fitness_nan"


# ---------------------------------------------------------------- P2-3/스텁
def test_max_program_length_penalty_only():
    d = _diag(program_size=6)
    opts = {"max_program_length": 5}
    strict = apply_constraint("strict_penalty", d, TH, -1.0, 0.03,
                              fitness_opts=opts)
    assert strict["effective_fitness"] == -1.0
    assert strict["invalid_reason"] == "static_invalid:too_long"
    assert strict["hard_invalid"] is True
    off = apply_constraint("off", d, TH, -1.0, 0.03, fitness_opts=opts)
    assert off["effective_fitness"] == d["abs_train_IC"]   # off는 원형 유지
    boundary = apply_constraint("strict_penalty", _diag(program_size=5), TH,
                                -1.0, 0.03, fitness_opts=opts)
    assert boundary["effective_fitness"] == 0.05           # == max → pass


def test_static_stub_reason_passthrough():
    d = _diag(signed_train_IC=float("nan"), abs_train_IC=float("nan"),
              hard_invalid=True,
              invalid_reason="static_invalid:constant_expression")
    info = apply_constraint("strict_penalty", d, TH, -1.0, 0.03)
    assert info["effective_fitness"] == -1.0
    assert info["invalid_reason"] == "static_invalid:constant_expression"


def test_close_raw_fitness_fallback_off_mode():
    d = _diag(eval_failed=True, hard_invalid=True,
              signed_train_IC=float("nan"), abs_train_IC=float("nan"),
              invalid_reason="formula_eval_failed:parse")
    info = apply_constraint("off", d, TH, -1e6, 0.03,
                            fitness_metric="ic_tstat", close_raw_fitness=3.3)
    assert info["fallback_used"] and info["effective_fitness"] == 3.3
