"""Phase 5 smoke: trajectory 입출력 + Search-QD 세대 지표 (synthetic 3세대)."""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.inputs.trajectory import TrajectoryWriter, load_trajectory  # noqa: E402
from alphasearchbench.inputs.schemas import SchemaError                            # noqa: E402
from alphasearchbench.qd.trajectory import (                                       # noqa: E402
    unique_candidates, search_budget, generation_metrics)
from alphasearchbench.qd.grid import QDGrid                                        # noqa: E402


def _write_synthetic_trajectory(path: str) -> pd.DataFrame:
    """3세대: 세대가 진행되며 새 formula가 등장하고 PC 공간에서 우측으로 이동."""
    with TrajectoryWriter(path, run_id="r1", method="synthetic", seed=0) as w:
        # gen0: f0~f3 (한 구석), 중복 포함
        for i, f in enumerate(["f0", "f1", "f2", "f3", "f0", "f1"]):
            w.write(0, i, f, raw_fitness=0.01 * (i + 1), memo_hit=(i >= 4))
        # gen1: 절반 유지 + 새 formula
        for i, f in enumerate(["f2", "f3", "f4", "f5", "f4", "f2"]):
            w.write(1, i, f, raw_fitness=0.02 * (i + 1), memo_hit=(f in ("f2", "f3")))
        # gen2: 더 멀리 이동
        for i, f in enumerate(["f5", "f6", "f7", "f8", "f8", "f6"]):
            w.write(2, i, f, raw_fitness=0.03 * (i + 1), memo_hit=False)
    return load_trajectory(path)


def _formula_info() -> pd.DataFrame:
    # f0..f8이 PC1 축을 따라 이동; f7은 invalid
    rows = []
    for k in range(9):
        rows.append({"formula": f"f{k}", "pc1": 0.1 * k, "pc2": 0.05 * (k % 3),
                     "valid": (k != 7), "quality": 0.01 * k})
    return pd.DataFrame(rows)


def test_trajectory_roundtrip_and_schema():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "traj.jsonl")
        traj = _write_synthetic_trajectory(p)
        assert len(traj) == 18
        assert set(["run_id", "method", "seed", "generation",
                    "idx_in_population", "formula", "raw_fitness"]).issubset(traj.columns)
        # 스키마 위반 검출
        bad = os.path.join(td, "bad.jsonl")
        with open(bad, "w") as f:
            f.write('{"formula": "x"}\n')
        with pytest.raises(SchemaError):
            load_trajectory(bad)


def test_dedup_preserves_original():
    with tempfile.TemporaryDirectory() as td:
        traj = _write_synthetic_trajectory(os.path.join(td, "t.jsonl"))
        uniq = unique_candidates(traj)
        assert len(uniq) == 9                      # f0..f8
        assert len(traj) == 18                     # 원본 보존


def test_search_budget():
    with tempfile.TemporaryDirectory() as td:
        traj = _write_synthetic_trajectory(os.path.join(td, "t.jsonl"))
        b = search_budget(traj, wall_clock_seconds=12.5)
        assert b["total_evaluations"] == 18
        assert b["unique_evaluations"] == 9
        assert b["generations"] == 3
        assert b["population_size"] == 6
        assert 0 < b["memo_hit_ratio"] < 1
        assert b["wall_clock_seconds"] == 12.5


def test_generation_metrics_coverage_and_centroid_move():
    with tempfile.TemporaryDirectory() as td:
        traj = _write_synthetic_trajectory(os.path.join(td, "t.jsonl"))
    info = _formula_info()
    grid = QDGrid([[-0.05, 0.95], [-0.05, 0.15]], [10, 2])
    gm = generation_metrics(traj, info, grid, quality_col="quality",
                            hq_threshold=0.03)
    assert list(gm["generation"]) == [0, 1, 2]
    # 세대가 진행되며 누적 점유 bin 증가
    assert gm["cumulative_occupied_bins"].is_monotonic_increasing
    assert gm.loc[2, "new_occupied_bins"] >= 1
    # centroid가 PC1 양의 방향으로 이동
    assert gm.loc[2, "centroid_pc1"] > gm.loc[0, "centroid_pc1"]
    assert np.isfinite(gm.loc[1, "centroid_displacement"])
    # invalid formula(f7)가 valid rate에 반영 (gen2: f5,f6,f7,f8 중 1개 invalid)
    assert gm.loc[2, "valid_candidate_rate"] == pytest.approx(3 / 4)


def test_no_trajectory_graceful():
    """trajectory 파일이 없으면 FileNotFoundError — 러너는 final-pool QD만 수행."""
    with pytest.raises(FileNotFoundError):
        load_trajectory("/nonexistent/traj.jsonl")
