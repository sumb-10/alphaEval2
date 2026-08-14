"""Phase 3 smoke: QD core descriptor 순수 함수들의 방향성 검증 (synthetic).

qlib 불필요 — descriptors.py의 순수 함수 + rre.py를 직접 검증한다.
실데이터 통합은 Phase 9 E2E에서 확인.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.qd.rre import rre_qd, rre_legacy            # noqa: E402
from alphasearchbench.qd.descriptors import (                      # noqa: E402
    normalized_contrast, horizon_scalar, activation_breadth,
    signal_weight_turnover, liquidity_footprint, daily_liquidity_percentile)
from alphasearchbench.data.signal_context import daily_zscore      # noqa: E402
from alphasearchbench.oos.metrics import daily_ic_series           # noqa: E402

T, N = 50, 40
UNI = np.ones((T, N), dtype=bool)
RNG = np.random.default_rng(3)


# ---------------------------------------------------------------- RRE
def test_rre_identical_ranks_is_one():
    base = RNG.normal(size=N)
    sig = np.tile(base, (T, 1)) + np.arange(T)[:, None] * 10.0   # 순위 완전 보존
    out = rre_qd(sig, UNI)
    assert out["rre_qd"] == pytest.approx(1.0, abs=1e-12)
    assert out["rre_min_common_n"] == N


def test_rre_decreases_with_rank_flips():
    stable = np.tile(RNG.normal(size=N), (T, 1)) + RNG.normal(0, 1e-6, size=(T, N))
    flipping = RNG.normal(size=(T, N))                            # 매일 재추첨
    r_stable = rre_qd(stable, UNI)["rre_qd"]
    r_flip = rre_qd(flipping, UNI)["rre_qd"]
    assert r_stable > r_flip


def test_rre_qd_common_universe_only():
    sig = RNG.normal(size=(T, N))
    valid = UNI.copy()
    valid[10, 20:] = False                    # 하루 절반 결측 → 교집합 축소
    out = rre_qd(sig, valid)
    assert out["rre_min_common_n"] == 20
    assert out["rre_n_pairs_used"] == T - 1


def test_rre_legacy_reproduces_reference_shape():
    sig = RNG.normal(size=(T, N))
    v = rre_legacy(sig)
    assert 0.0 < v <= 1.0


# ---------------------------------------------------------------- contrast/H
def test_normalized_contrast_direction_and_flag():
    c = normalized_contrast(0.10, -0.10, eps=1e-4, denom_threshold=1e-3)
    assert c["value"] == pytest.approx(1.0, rel=1e-3)
    assert not c["denom_small"]
    c2 = normalized_contrast(1e-5, -1e-5, eps=1e-4, denom_threshold=1e-3)
    assert c2["denom_small"]


def test_horizon_weighted_abs_ic():
    h = horizon_scalar({1: 0.0, 5: 0.0, 10: 0.0, 20: 0.08},
                       "weighted_abs_ic", 1e-3)
    assert h["value"] == pytest.approx(20.0)
    h2 = horizon_scalar({1: 0.05, 5: 0.05, 10: 0.05, 20: 0.05},
                        "weighted_abs_ic", 1e-3)
    assert h2["value"] == pytest.approx((1 + 5 + 10 + 20) / 4)
    h3 = horizon_scalar({1: 0.0, 5: 0.0, 10: 0.0, 20: 0.0},
                        "weighted_abs_ic", 1e-3)
    assert np.isnan(h3["value"]) and h3["denom_small"]


# ---------------------------------------------------------------- breadth/coverage
def test_breadth_uniform_vs_concentrated():
    uniform = np.tile(np.linspace(-1, 1, N), (T, 1))              # 고른 분산
    z_u = daily_zscore(uniform, UNI)
    concentrated = np.zeros((T, N)); concentrated[:, 0] = 100.0   # 한 종목 집중
    z_c = daily_zscore(concentrated, UNI)
    b_u = activation_breadth(z_u, UNI)
    b_c = activation_breadth(z_c, UNI)
    assert b_u > 0.5
    assert b_c < b_u


def test_signal_weight_turnover_flip_and_freeze():
    base = RNG.normal(size=N)
    frozen = np.tile(base, (T, 1))
    z_f = daily_zscore(frozen, UNI)
    assert signal_weight_turnover(z_f) == pytest.approx(0.0, abs=1e-12)
    # 완전 부호 반전을 반복 → w가 매일 뒤집힘 → 0.5·Σ|Δw| = 0.5·2·Σ|w| = 1
    alt = np.tile(base, (T, 1)) * ((-1) ** np.arange(T))[:, None]
    z_a = daily_zscore(alt, UNI)
    assert signal_weight_turnover(z_a) == pytest.approx(1.0, abs=1e-9)


def test_liquidity_footprint_direction():
    pct = np.tile(np.linspace(0, 1, N), (T, 1))                   # 고정 유동성 순위
    hi = np.zeros((T, N)); hi[:, -1] = 1.0                        # 최고 유동성에 베팅
    lo = np.zeros((T, N)); lo[:, 0] = 1.0                         # 최저 유동성에 베팅
    f_hi = liquidity_footprint(daily_zscore(hi, UNI), pct, UNI)
    f_lo = liquidity_footprint(daily_zscore(lo, UNI), pct, UNI)
    assert f_hi > f_lo


def test_daily_liquidity_percentile_masks_universe():
    adv = RNG.uniform(1, 100, size=(T, N))
    uni = UNI.copy(); uni[:, :5] = False
    pct = daily_liquidity_percentile(adv, uni)
    assert np.isnan(pct[:, :5]).all()
    assert np.nanmax(pct) <= 1.0 and np.nanmin(pct) > 0.0


# ---------------------------------------------------------------- V/M 방향성
def test_regime_contrast_directionality():
    """상승장에서만 예측력이 있는 신호 → M > 0."""
    fwd = RNG.normal(0, 0.02, size=(T, N)).astype(np.float32)
    up_days = np.arange(T) % 2 == 0
    sig = np.where(up_days[:, None], fwd, RNG.normal(size=(T, N)).astype(np.float32))
    ic = daily_ic_series(sig, fwd, UNI)
    ic_up = float(np.nanmean(ic[up_days]))
    ic_dn = float(np.nanmean(ic[~up_days]))
    m = normalized_contrast(ic_up, ic_dn, 1e-4, 1e-3)
    assert ic_up > 0.9 and abs(ic_dn) < 0.3
    assert m["value"] > 0.5
