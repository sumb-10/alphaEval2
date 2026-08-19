"""QD grid + pool-level diversity/density metrics.

원칙:
  * 정량 분석에서 bounds 밖 점을 clipping하지 않는다 — under/overflow를
    기록하고 grid 지표에서는 in-bounds 점만 사용, overflow_ratio를 보고.
  * KDE는 시각화 전용(별도 함수) — 정량 coverage는 fixed grid로만.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


class QDGrid:
    def __init__(self, bounds: Sequence[Sequence[float]], resolution: Sequence[int]):
        """bounds = [[pc1_min, pc1_max], [pc2_min, pc2_max]], resolution = [nx, ny]"""
        self.bounds = [list(map(float, b)) for b in bounds]
        self.resolution = [int(r) for r in resolution]
        if len(self.bounds) != 2 or len(self.resolution) != 2:
            raise ValueError("QDGrid는 2차원 전용입니다")
        self.edges = [np.linspace(b[0], b[1], r + 1)
                      for b, r in zip(self.bounds, self.resolution)]

    @classmethod
    def from_reference(cls, pcs: np.ndarray, resolution: Sequence[int],
                       margin: float = 0.05) -> "QDGrid":
        """reference PC 분포에서 bounds 결정(±margin) — 이후 manifest에 freeze."""
        ok = np.isfinite(pcs).all(axis=1)
        p = pcs[ok]
        bounds = []
        for d in range(2):
            lo, hi = float(p[:, d].min()), float(p[:, d].max())
            pad = (hi - lo) * margin or 1e-6
            bounds.append([lo - pad, hi + pad])
        return cls(bounds, resolution)

    # ------------------------------------------------------------------
    def assign(self, pcs: np.ndarray) -> Dict[str, np.ndarray]:
        """각 점의 bin 인덱스 + overflow 플래그. bounds 밖/NaN은 bin=-1."""
        n = len(pcs)
        res: Dict[str, np.ndarray] = {
            "bin_x": np.full(n, -1, dtype=int),
            "bin_y": np.full(n, -1, dtype=int),
            "pc1_underflow": np.zeros(n, dtype=bool),
            "pc1_overflow": np.zeros(n, dtype=bool),
            "pc2_underflow": np.zeros(n, dtype=bool),
            "pc2_overflow": np.zeros(n, dtype=bool),
        }
        finite = np.isfinite(pcs).all(axis=1)
        for d, (name_u, name_o) in enumerate(
                [("pc1_underflow", "pc1_overflow"), ("pc2_underflow", "pc2_overflow")]):
            lo, hi = self.bounds[d]
            res[name_u] = finite & (pcs[:, d] < lo)
            res[name_o] = finite & (pcs[:, d] > hi)
        inb = finite & ~(res["pc1_underflow"] | res["pc1_overflow"]
                         | res["pc2_underflow"] | res["pc2_overflow"])
        for d, key in enumerate(("bin_x", "bin_y")):
            idx = np.searchsorted(self.edges[d], pcs[inb, d], side="right") - 1
            idx = np.clip(idx, 0, self.resolution[d] - 1)   # 경계점 안정화(내부 전용)
            res[key][inb] = idx
        res["in_bounds"] = inb
        return res

    # ------------------------------------------------------------------
    def bin_counts(self, assign: Dict[str, np.ndarray]) -> np.ndarray:
        counts = np.zeros(self.resolution, dtype=int)
        inb = assign["in_bounds"]
        np.add.at(counts, (assign["bin_x"][inb], assign["bin_y"][inb]), 1)
        return counts

    def pool_metrics(self, pcs: np.ndarray) -> Dict[str, float]:
        a = self.assign(pcs)
        counts = self.bin_counts(a)
        n_total_bins = int(np.prod(self.resolution))
        occupied = counts[counts > 0]
        n_occ = int(len(occupied))
        n_points = int(np.isfinite(pcs).all(axis=1).sum())
        n_inb = int(a["in_bounds"].sum())
        out = {
            "n_points": n_points,
            "n_in_bounds": n_inb,
            "overflow_ratio": (n_points - n_inb) / n_points if n_points else float("nan"),
            "coverage": n_occ / n_total_bins,
            "n_occupied_bins": n_occ,
            "n_total_bins": n_total_bins,
        }
        if n_occ == 0:
            out["occupancy_entropy_global"] = float("nan")
            out["occupancy_evenness"] = float("nan")
            return out
        p = occupied / occupied.sum()
        h = float(-(p * np.log(p)).sum())
        out["occupancy_entropy_global"] = h / np.log(n_total_bins)
        out["occupancy_evenness"] = (h / np.log(n_occ)) if n_occ > 1 else 1.0
        return out


# ---------------------------------------------------------------- NN / HQ / rarefaction
def nn_distances(points: np.ndarray) -> Dict[str, float]:
    """자기 자신 제외 최근접 거리의 mean/median (finite 행만)."""
    ok = np.isfinite(points).all(axis=1)
    p = points[ok]
    if len(p) < 2:
        return {"nn_mean": float("nan"), "nn_median": float("nan"), "n_points": int(len(p))}
    from scipy.spatial import cKDTree
    tree = cKDTree(p)
    d, _ = tree.query(p, k=2)
    nn = d[:, 1]
    return {"nn_mean": float(nn.mean()), "nn_median": float(np.median(nn)),
            "n_points": int(len(p))}


def hq_filter(quality: np.ndarray, threshold: Optional[float]) -> np.ndarray:
    """quality metric ≥ threshold 마스크. threshold=None이면 전부 False(미실행)."""
    if threshold is None:
        return np.zeros(len(quality), dtype=bool)
    return np.isfinite(quality) & (quality >= threshold)


def rarefaction_coverage(grid: QDGrid, pcs: np.ndarray, n: int, repeats: int,
                         seed: int) -> Dict[str, float]:
    """고정 N개 비복원 subsampling을 repeats회 → E[coverage@N], std."""
    ok = np.isfinite(pcs).all(axis=1)
    p = pcs[ok]
    if len(p) < n or n <= 0:
        return {"expected_coverage_at_n": float("nan"),
                "std_coverage_at_n": float("nan"), "rarefaction_n": n,
                "rarefaction_repeats": repeats}
    rng = np.random.default_rng(seed)
    covs = []
    for _ in range(repeats):
        idx = rng.choice(len(p), size=n, replace=False)
        covs.append(grid.pool_metrics(p[idx])["coverage"])
    return {"expected_coverage_at_n": float(np.mean(covs)),
            "std_coverage_at_n": float(np.std(covs)),
            "rarefaction_n": n, "rarefaction_repeats": repeats}
