"""unit — constraint/fitness 의미론 (qlib 불필요).

스펙 #9(worst sentinel), #24(threshold 경계 >= pass), #26(selection은
effective fitness), #19(invalid의 raw IC 보존), off 모드 fallback.
"""
import os
import sys

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PKG_ROOT)

from gplearn_asb.fitness import (apply_constraint, research_failures,  # noqa: E402
                                 check_sentinel_separation)

TH = {"min_mean_daily_coverage_ratio": 0.05,
      "min_median_daily_n_valid": 30,
      "min_valid_day_ratio": 0.90}
WORST = -1.0


def _diag(signed=0.1, hard=False, eval_failed=False, reason=None,
          cov=0.5, med_n=2000, vdr=1.0):
    return {"signed_train_IC": signed, "abs_train_IC": abs(signed),
            "hard_invalid": hard, "eval_failed": eval_failed,
            "invalid_reason": reason,
            "mean_daily_coverage_ratio": cov,
            "median_daily_n_valid": med_n, "valid_day_ratio": vdr}


# ---- threshold 경계 (#24): value >= threshold → pass, 경계값 정확히 통과 ----
def test_threshold_boundary_exact_pass():
    d = _diag(cov=0.050, med_n=30, vdr=0.900)
    assert research_failures(d, TH) == []


def test_threshold_below_fails_each():
    assert research_failures(_diag(cov=0.0499), TH) == ["min_mean_daily_coverage_ratio"]
    assert research_failures(_diag(med_n=29), TH) == ["min_median_daily_n_valid"]
    assert research_failures(_diag(vdr=0.8999), TH) == ["min_valid_day_ratio"]


def test_threshold_nan_fails_and_null_skipped():
    assert research_failures(_diag(cov=float("nan")), TH) == ["min_mean_daily_coverage_ratio"]
    # null threshold는 게이트 아님
    assert research_failures(_diag(cov=0.0), {**TH, "min_mean_daily_coverage_ratio": None}) == []


# ---- worst sentinel 순서 (#9): 모든 invalid < 모든 valid ----
def test_sentinel_below_all_valid():
    inv = apply_constraint("strict_penalty", _diag(signed=0.80, cov=0.001),
                           TH, WORST, close_signed_ic=0.03)
    ok = apply_constraint("strict_penalty", _diag(signed=0.0001),
                          TH, WORST, close_signed_ic=0.03)
    assert inv["effective_fitness"] == WORST
    assert np.isfinite(inv["effective_fitness"])          # NaN/-inf 금지
    assert inv["effective_fitness"] < ok["effective_fitness"]
    # raw IC 보존 (#19): raw_fitness=0.80, effective=WORST 공존
    assert inv["raw_fitness"] == 0.80
    assert inv["research_invalid"] and not inv["hard_invalid"]


def test_hard_penalty_only_hard():
    # coverage 실패지만 hard는 아님 → hard_penalty에서는 통과
    d = _diag(signed=0.80, cov=0.001)
    r = apply_constraint("hard_penalty", d, TH, WORST, 0.03)
    assert r["effective_fitness"] == 0.80 and not r["research_invalid"]
    # hard invalid는 두 penalty 모드 모두에서 worst
    dh = _diag(signed=float("nan"), hard=True, eval_failed=True,
               reason="formula_eval_failed:parse_error:x")
    for mode in ("hard_penalty", "strict_penalty"):
        rh = apply_constraint(mode, dh, TH, WORST, 0.03)
        assert rh["effective_fitness"] == WORST and rh["hard_invalid"]


# ---- selection은 effective 사용 (#26) — tournament argmax 시뮬레이션 ----
def test_tournament_prefers_valid_despite_high_raw_ic():
    invalid = apply_constraint("strict_penalty", _diag(signed=0.80, cov=0.001),
                               TH, WORST, 0.03)
    valid = apply_constraint("strict_penalty", _diag(signed=0.02),
                             TH, WORST, 0.03)
    # gplearn _tournament: fitness_(=raw_fitness_−0·len) argmax
    fitness_ = [invalid["effective_fitness"], valid["effective_fitness"]]
    assert int(np.argmax(fitness_)) == 1                  # valid가 부모로 선택됨
    assert invalid["raw_fitness"] > valid["raw_fitness"]  # raw로는 invalid가 우세했음


# ---- off 모드: 원본 $close fallback 재현 + validity는 기록만 ----
def test_off_mode_fallback_and_no_gating():
    dh = _diag(signed=float("nan"), hard=True, eval_failed=True,
               reason="formula_eval_failed:eval_error:x")
    r = apply_constraint("off", dh, TH, WORST, close_signed_ic=-0.0482)
    assert r["fallback_used"]
    assert r["signed_train_IC"] == -0.0482
    assert r["effective_fitness"] == abs(-0.0482)         # 원본 루프홀 그대로
    # research 실패도 off에서는 게이트 아님
    d = _diag(signed=0.3, cov=0.001)
    r2 = apply_constraint("off", d, TH, WORST, 0.03)
    assert r2["effective_fitness"] == 0.3 and not r2["research_invalid"]


def test_sentinel_separation_warning():
    assert check_sentinel_separation(-1.0, 0.0) is None
    assert check_sentinel_separation(-1.0, 0.01, max_len_estimate=500) is not None
