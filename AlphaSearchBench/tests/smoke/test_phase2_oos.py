"""Phase 2 smoke: OOS metrics — synthetic 수치 검증 + 손계산 combined.

synthetic 부분은 qlib 불필요 (metrics 순수 함수).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.oos.metrics import (          # noqa: E402
    daily_ic_series, daily_rank_ic_series, aggregate_ic)
from alphasearchbench.data.signal_context import daily_zscore  # noqa: E402

T, N = 40, 60
UNI = np.ones((T, N), dtype=bool)
RNG = np.random.default_rng(42)
FWD = RNG.normal(0, 0.02, size=(T, N)).astype(np.float32)


def test_perfect_positive_signal():
    ic = daily_ic_series(FWD.copy(), FWD, UNI)          # 신호 = 미래수익
    assert np.allclose(ic, 1.0)
    agg = aggregate_ic(ic)
    assert agg["mean"] == pytest.approx(1.0)


def test_inverse_signal_with_train_sign():
    raw = -FWD                                           # 완전 역방향 신호
    ic_raw = daily_ic_series(raw, FWD, UNI)
    assert np.allclose(ic_raw, -1.0)
    oriented = -1 * raw                                  # train_sign=-1 적용
    ic = daily_ic_series(oriented, FWD, UNI)
    assert np.allclose(ic, 1.0)


def test_random_signal_ic_near_zero():
    sig = np.random.default_rng(7).normal(size=(T, N)).astype(np.float32)
    agg = aggregate_ic(daily_ic_series(sig, FWD, UNI))
    assert abs(agg["mean"]) < 0.05
    # ICIR raw vs ann 관계
    assert agg["icir_ann"] == pytest.approx(agg["icir"] * np.sqrt(252))


def test_constant_signal_gives_nan_ic():
    sig = np.full((T, N), 2.0, dtype=np.float32)
    ic = daily_ic_series(sig, FWD, UNI)
    assert np.isnan(ic).all()
    assert aggregate_ic(ic)["n_obs"] == 0


def test_rank_ic_monotone_transform_invariance():
    """RankIC는 단조변환에 불변 — exp(signal)과 signal의 RankIC 동일."""
    sig = RNG.normal(size=(T, N)).astype(np.float32)
    r1 = daily_rank_ic_series(sig, FWD, UNI)
    r2 = daily_rank_ic_series(np.exp(sig), FWD, UNI)
    assert np.allclose(r1, r2, atol=1e-12)


def test_rank_ic_ties_average():
    """tie=average 확인: 손계산 예제 (하루, 4종목)."""
    sig = np.array([[1.0, 2.0, 2.0, 3.0]], dtype=np.float64)
    fwd = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    uni = np.ones((1, 4), dtype=bool)
    # ranks(sig) = [1, 2.5, 2.5, 4]; ranks(fwd) = [1,2,3,4]
    # Pearson([1,2.5,2.5,4],[1,2,3,4]) = 손계산
    a = np.array([1, 2.5, 2.5, 4.0]); b = np.array([1, 2, 3, 4.0])
    expected = np.corrcoef(a, b)[0, 1]
    got = daily_rank_ic_series(sig, fwd, uni)[0]
    assert got == pytest.approx(expected, abs=1e-12)


def test_combined_signal_hand_calc():
    """2-factor 손계산: combined = w1·z1 + w2·z2 → IC를 직접 대조."""
    sig1 = RNG.normal(size=(T, N)).astype(np.float32)
    sig2 = RNG.normal(size=(T, N)).astype(np.float32)
    w1, w2 = 0.7, -0.3
    z1 = daily_zscore(sig1, UNI)
    z2 = daily_zscore(sig2, UNI)
    combo = w1 * z1 + w2 * z2
    ic_combo = daily_ic_series(combo, FWD, UNI)
    # 독립 재계산 (numpy corrcoef per day)
    for t in (0, T // 2, T - 1):
        expected = np.corrcoef(combo[t], FWD[t].astype(np.float64))[0, 1]
        assert ic_combo[t] == pytest.approx(expected, abs=1e-10)
    # component 평균이 아님을 확인
    ic1 = aggregate_ic(daily_ic_series(sig1, FWD, UNI))["mean"]
    ic2 = aggregate_ic(daily_ic_series(sig2, FWD, UNI))["mean"]
    naive = w1 * ic1 + w2 * ic2
    assert aggregate_ic(ic_combo)["mean"] != pytest.approx(naive, abs=1e-6)


def test_missing_cells_excluded():
    sig = FWD.copy()
    sig[:, ::2] = np.nan                     # 절반 결측 — 나머지는 완전 신호
    ic = daily_ic_series(sig, FWD, UNI)
    assert np.allclose(ic, 1.0)
