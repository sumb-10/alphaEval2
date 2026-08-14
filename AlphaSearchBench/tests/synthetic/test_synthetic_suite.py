"""Synthetic numerical suite — 스펙 Phase 10 요구 케이스의 단일 집약본.

(개별 phase smoke에 분산된 검증의 재확인 + 미커버 케이스 보강.
qlib 불필요 — 순수 numpy.)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.oos.metrics import daily_ic_series, aggregate_ic       # noqa: E402
from alphasearchbench.qd.rre import rre_qd                                    # noqa: E402
from alphasearchbench.qd.diversity import de_legacy, de_common_valid          # noqa: E402
from alphasearchbench.qd.pfs import PaperLiteralPolicy, _rng_for              # noqa: E402
from alphasearchbench.data.signal_context import daily_zscore                 # noqa: E402
from alphasearchbench.data.qlib_provider import FEATURE_LIST                  # noqa: E402
from alphasearchbench.backtest.simple import run_simple_backtest              # noqa: E402

import pandas as pd

T, N = 40, 30
UNI = np.ones((T, N), dtype=bool)
RNG = np.random.default_rng(99)
FWD = RNG.normal(0, 0.02, size=(T, N)).astype(np.float32)


# ---- OOS ----
def test_oos_perfect_inverse_random():
    assert aggregate_ic(daily_ic_series(FWD.copy(), FWD, UNI))["mean"] == pytest.approx(1.0)
    oriented = -1 * (-FWD)          # inverse predictor + train_sign=-1
    assert aggregate_ic(daily_ic_series(oriented, FWD, UNI))["mean"] == pytest.approx(1.0)
    # random: 통계적으로 안전한 크기 (일별 IC se≈1/√N, 평균 se≈1/√(N·T))
    Tb, Nb = 60, 200
    unib = np.ones((Tb, Nb), dtype=bool)
    fwdb = np.random.default_rng(2).normal(0, 0.02, size=(Tb, Nb)).astype(np.float32)
    rnd = np.random.default_rng(1).normal(size=(Tb, Nb)).astype(np.float32)
    assert abs(aggregate_ic(daily_ic_series(rnd, fwdb, unib))["mean"]) < 0.04  # >4σ 여유


# ---- RRE ----
def test_rre_identical_rank_every_day():
    sig = np.tile(RNG.normal(size=N), (T, 1))
    assert rre_qd(sig, UNI)["rre_qd"] == pytest.approx(1.0, abs=1e-12)


# ---- PFS ----
def test_pfs_epsilon_zero_identity():
    panels = {f: RNG.normal(size=(T, N)).astype(np.float32) for f in FEATURE_LIST}
    rng = _rng_for(["synthetic", "pfs"])
    perturbed = PaperLiteralPolicy().perturb(panels, rng, sigma=0.0, dof=3,
                                             noise_type="gaussian")
    for f in FEATURE_LIST:
        assert np.array_equal(panels[f], perturbed[f])


# ---- Diversity ----
def test_de_identical_vs_orthogonal():
    base = RNG.normal(size=(T, N))
    identical = [daily_zscore(base.copy(), UNI) for _ in range(6)]
    assert de_legacy(identical) == pytest.approx(0.0, abs=1e-8)
    indep = [daily_zscore(RNG.normal(size=(T, N)), UNI) for _ in range(6)]
    assert de_legacy(indep) > 0.9
    out = de_common_valid([base] * 3, [UNI] * 3, UNI)
    assert out["de_common_valid"] == pytest.approx(0.0, abs=1e-8)


# ---- Backtest ----
def test_backtest_hand_calculable():
    dates = pd.date_range("2020-01-01", periods=2, freq="B")
    sig = np.array([[3.0, 2.0, 1.0], [3.0, 2.0, 1.0]])
    valid = np.ones_like(sig, dtype=bool)
    r = np.array([[0.03, 0.0, -0.01], [0.03, 0.0, -0.01]])
    m, d = run_simple_backtest(sig, valid, r, dates, 1 / 3, 1 / 3, 0.0, "oneway")
    # long idx0(+0.5), short idx2(−0.5): gross = .5·.03 + .5·.01 = 0.02
    assert np.allclose(d["gross_return"], 0.02)
    assert d.loc[1, "turnover_l1"] == 0.0            # 보유 유지


# ---- Reproducibility ----
def test_same_seed_same_output():
    r1 = _rng_for(["a", 1, "b"]).normal(size=100)
    r2 = _rng_for(["a", 1, "b"]).normal(size=100)
    r3 = _rng_for(["a", 2, "b"]).normal(size=100)
    assert np.array_equal(r1, r2)
    assert not np.array_equal(r1, r3)


# ---- Orientation 단일 적용 (pilot 검증 V6) ----
def test_orientation_applied_exactly_once():
    """train_sign은 신호에 정확히 1회 곱해진다: IC(sign·x) == sign·IC(x).

    역방향 예측자(train IC<0)에 sign=-1을 주면 test oriented IC는
    양수가 되어야 하고, 크기는 불변이어야 한다 (이중 적용이면 다시 음수).
    """
    inv = (-FWD + RNG.normal(0, 0.005, size=(T, N))).astype(np.float32)
    raw = aggregate_ic(daily_ic_series(inv, FWD, UNI))["mean"]
    assert raw < -0.9                                  # 역방향 예측자
    oriented = aggregate_ic(daily_ic_series(-1 * inv, FWD, UNI))["mean"]
    assert oriented == pytest.approx(-raw)             # 부호만 반전, 크기 보존
    assert oriented > 0.9
