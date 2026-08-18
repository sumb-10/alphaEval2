"""unit — net_sharpe fitness: 손계산 대조 + sentinel/판정 경로 (qlib 불필요)."""
import math
import os
import sys
import types

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    sys.path.insert(0, _p)

from gplearn_asb.evaluator import MiningEvaluator          # noqa: E402
from gplearn_asb.fitness import apply_constraint            # noqa: E402

TH = {"min_mean_daily_coverage_ratio": 0.05,
      "min_median_daily_n_valid": 30, "min_valid_day_ratio": 0.90}
WORST = -1e6


def _bare_eval(label, mask, cost=0.0015, q=0.2):
    ev = types.SimpleNamespace(label=label, universe_mask=mask,
                               cost_rate=cost, ls_quantile=q)
    return ev


def test_net_sharpe_hand_calculation():
    """T=3, N=5, q=0.2 → k=1 (top1 long +0.5 / bottom1 short −0.5)."""
    F = np.array([[5, 4, 3, 2, 1],
                  [5, 4, 3, 2, 1],
                  [1, 2, 3, 4, 5]], dtype=np.float32)
    L = np.array([[0.02, 0.01, 0.0, -0.01, -0.02]] * 3, dtype=np.float64)
    mask = np.ones((3, 5), dtype=bool)
    ev = _bare_eval(L, mask, cost=0.0015)
    ns, stats = MiningEvaluator._net_sharpe(ev, F, sign=1)
    # 손계산: gross = [0.5*0.02 - 0.5*(-0.02)]*2일 = 0.02, 3일째 뒤집힘 → 0.5*(-0.02)-0.5*0.02 = -0.02
    # turnover_l1: 첫날 건립 1.0, 둘째 0, 셋째 |ΔW| = (0.5+0.5)*2 = 2.0 → oneway [0.5, 0, 1.0]
    # net = [0.02-0.5*0.0015, 0.02, -0.02-1.0*0.0015] = [0.01925, 0.02, -0.0215]
    net = np.array([0.02 - 0.0015 * 0.5, 0.02, -0.02 - 0.0015 * 1.0])
    expected = net.mean() / net.std(ddof=1) * np.sqrt(252)
    assert math.isclose(ns, expected, rel_tol=1e-12), (ns, expected)
    assert stats["n_traded_days"] == 3
    assert math.isclose(stats["mean_daily_turnover_oneway"], (0.5 + 0 + 1.0) / 3,
                        rel_tol=1e-12)


def test_net_sharpe_sign_flip_and_min_cross_section():
    F = np.array([[5, 4, 3, 2, 1]] * 3, dtype=np.float32)
    # 일별 라벨을 다르게 해 net 분산 > 0 보장 (상수 net → std=0 → NaN)
    L = np.array([[0.02, 0.01, 0.0, -0.01, -0.02],
                  [0.03, 0.01, 0.0, -0.01, -0.03],
                  [0.01, 0.005, 0.0, -0.005, -0.01]], dtype=np.float64)
    mask = np.ones((3, 5), dtype=bool)
    ev = _bare_eval(L, mask, cost=0.0)
    ns_pos, _ = MiningEvaluator._net_sharpe(ev, F, sign=1)
    ns_neg, _ = MiningEvaluator._net_sharpe(ev, -F, sign=-1)   # oriented 동일
    assert math.isclose(ns_pos, ns_neg, rel_tol=1e-12)
    # 단면 n<5 → 무포지션 → 분산 0 → NaN
    mask2 = mask.copy(); mask2[:, 2:] = False
    ns_small, st = MiningEvaluator._net_sharpe(ev, F, sign=1)
    ev2 = _bare_eval(L, mask2)
    ns2, st2 = MiningEvaluator._net_sharpe(ev2, F, sign=1)
    assert math.isnan(ns2) and st2["n_traded_days"] == 0


def _diag(signed=0.05, ns=0.8, hard=False, eval_failed=False,
          cov=0.5, med_n=2000, vdr=1.0, with_ns=True):
    d = {"signed_train_IC": signed, "abs_train_IC": abs(signed),
         "hard_invalid": hard, "eval_failed": eval_failed, "invalid_reason": None,
         "mean_daily_coverage_ratio": cov, "median_daily_n_valid": med_n,
         "valid_day_ratio": vdr}
    if with_ns:
        d["net_sharpe"] = ns
    return d


def test_apply_constraint_net_sharpe_paths():
    # valid: raw = net_sharpe (음수도 valid — sentinel보다 큼)
    r = apply_constraint("strict_penalty", _diag(ns=-3.2), TH, WORST, 0.03,
                         fitness_metric="net_sharpe")
    assert r["raw_fitness"] == -3.2 and r["effective_fitness"] == -3.2
    assert r["effective_fitness"] > WORST
    assert r["abs_train_IC"] == 0.05          # IC 필드는 IC 의미 유지
    # research invalid → worst
    ri = apply_constraint("strict_penalty", _diag(ns=2.0, cov=0.001), TH, WORST, 0.03,
                          fitness_metric="net_sharpe")
    assert ri["effective_fitness"] == WORST and ri["raw_fitness"] == 2.0
    # net_sharpe NaN(무거래) → worst + 사유
    rn = apply_constraint("strict_penalty", _diag(ns=float("nan")), TH, WORST, 0.03,
                          fitness_metric="net_sharpe")
    assert rn["effective_fitness"] == WORST
    assert rn["invalid_reason"] == "fitness_undefined:net_sharpe_nan"
    # off + eval 실패 → close net_sharpe 상속
    rf = apply_constraint("off", _diag(signed=float("nan"), hard=True,
                                       eval_failed=True, with_ns=False),
                          TH, WORST, -0.02, fitness_metric="net_sharpe",
                          close_net_sharpe=-0.7)
    assert rf["fallback_used"] and rf["raw_fitness"] == -0.7
    # abs_ic 기본 경로 회귀 없음
    ra = apply_constraint("strict_penalty", _diag(), TH, -1.0, 0.03)
    assert ra["raw_fitness"] == 0.05 and ra["fitness_metric"] == "abs_ic"
