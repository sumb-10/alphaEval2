"""Phase 4 smoke: projection persist/reload 재현, grid/pool metrics, DE 2종."""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.qd.projection import QDProjection, descriptor_diagnostics  # noqa: E402
from alphasearchbench.qd.grid import (                                            # noqa: E402
    QDGrid, nn_distances, hq_filter, rarefaction_coverage)
from alphasearchbench.qd.diversity import de_legacy, de_common_valid             # noqa: E402
from alphasearchbench.data.signal_context import daily_zscore                     # noqa: E402

RNG = np.random.default_rng(11)
COLS = ["a", "b", "c", "d"]


def _desc(n=60):
    return pd.DataFrame(RNG.normal(size=(n, 4)), columns=COLS)


# ---------------------------------------------------------------- projection
def test_projection_fit_transform_and_reload_reproduces():
    ref = _desc()
    proj = QDProjection(COLS, 2).fit_reference(ref, {"reference_split": "valid"})
    pcs1, ok1 = proj.transform(ref)
    assert ok1.all()
    with tempfile.TemporaryDirectory() as td:
        proj.save(td)
        loaded = QDProjection.load(td)
        pcs2, _ = loaded.transform(ref)
        assert np.array_equal(pcs1, pcs2)          # reload 후 완전 재현
        assert loaded.meta["reference_split"] == "valid"
        assert len(loaded.meta["explained_variance_ratio"]) == 2


def test_projection_nan_rows_not_projected():
    ref = _desc()
    proj = QDProjection(COLS, 2).fit_reference(ref)
    q = _desc(5)
    q.iloc[2, 1] = np.nan
    pcs, ok = proj.transform(q)
    assert not ok[2] and np.isnan(pcs[2]).all()
    assert ok.sum() == 4


def test_diagnostics_shapes():
    d = descriptor_diagnostics(_desc(), COLS)
    assert d["pearson"].shape == (4, 4)
    assert d["missing_ratio"]["missing_ratio"].max() == 0.0


# ---------------------------------------------------------------- grid
def test_grid_single_bin_vs_spread():
    grid = QDGrid([[-1, 1], [-1, 1]], [4, 4])
    clustered = np.full((30, 2), 0.1)
    spread = RNG.uniform(-0.99, 0.99, size=(64, 2))
    m1 = grid.pool_metrics(clustered)
    m2 = grid.pool_metrics(spread)
    assert m1["coverage"] == pytest.approx(1 / 16)
    assert m1["occupancy_evenness"] == 1.0          # N_occupied=1 예외 처리
    assert m2["coverage"] > m1["coverage"]
    assert m2["occupancy_entropy_global"] > m1["occupancy_entropy_global"]


def test_grid_overflow_recorded_not_clipped():
    grid = QDGrid([[-1, 1], [-1, 1]], [4, 4])
    pts = np.array([[0.0, 0.0], [5.0, 0.0], [-5.0, 0.0], [0.0, 9.0], [np.nan, 0.0]])
    a = grid.assign(pts)
    assert a["in_bounds"].tolist() == [True, False, False, False, False]
    assert a["pc1_overflow"][1] and a["pc1_underflow"][2] and a["pc2_overflow"][3]
    m = grid.pool_metrics(pts)
    assert m["overflow_ratio"] == pytest.approx(3 / 4)   # NaN은 n_points에서 제외


def test_nn_hq_rarefaction():
    pts = RNG.uniform(-1, 1, size=(50, 2))
    nn = nn_distances(pts)
    assert nn["nn_mean"] > 0 and nn["n_points"] == 50
    q = RNG.normal(0.02, 0.02, size=50)
    hq = hq_filter(q, 0.02)
    assert 0 < hq.sum() < 50
    assert hq_filter(q, None).sum() == 0            # threshold 미지정 → 미실행
    grid = QDGrid([[-1, 1], [-1, 1]], [5, 5])
    r = rarefaction_coverage(grid, pts, n=10, repeats=30, seed=7)
    r2 = rarefaction_coverage(grid, pts, n=10, repeats=30, seed=7)
    assert r == r2                                   # seed 결정론
    assert 0 < r["expected_coverage_at_n"] <= grid.pool_metrics(pts)["coverage"] + 1e-12


# ---------------------------------------------------------------- DE
T, N = 40, 30
UNI = np.ones((T, N), dtype=bool)


def _zfill(sig):
    return daily_zscore(sig, UNI & np.isfinite(sig))


def test_de_identical_factors_near_zero():
    base = RNG.normal(size=(T, N))
    zs = [_zfill(base.copy()) for _ in range(5)]
    assert de_legacy(zs) == pytest.approx(0.0, abs=1e-8)


def test_de_orthogonalish_factors_high():
    zs = [_zfill(RNG.normal(size=(T, N))) for _ in range(5)]
    assert de_legacy(zs) > 0.9


def test_de_common_valid_and_insufficient():
    sigs = [RNG.normal(size=(T, N)) for _ in range(4)]
    valids = [UNI.copy() for _ in sigs]
    valids[0][:, N // 2:] = False                    # 한 factor가 절반만 유효
    out = de_common_valid(sigs, valids, UNI, n_factors_dropped=1)
    assert out["n_factors_used"] == 4 and out["n_factors_dropped"] == 1
    assert out["common_cell_ratio"] == pytest.approx(0.5)
    assert 0.9 < out["de_common_valid"] <= 1.0

    # 표본 불충분 → NaN + reason (억지 값 금지)
    empty_valids = [np.zeros((T, N), dtype=bool) for _ in sigs]
    out2 = de_common_valid(sigs, empty_valids, UNI)
    assert np.isnan(out2["de_common_valid"])
    assert out2["reason"] == "insufficient_common_cells"
