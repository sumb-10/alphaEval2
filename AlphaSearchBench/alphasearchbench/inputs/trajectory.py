"""Trajectory JSONL 입출력 (표준 스키마 — schemas.py 참조)."""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

import pandas as pd

from .schemas import TRAJECTORY_REQUIRED, SchemaError, validate_columns


def load_trajectory(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    rows = []
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SchemaError(f"trajectory {path}:{ln} JSON 파싱 실패: {e}")
    if not rows:
        raise SchemaError(f"trajectory가 비어 있습니다: {path}")
    df = pd.DataFrame(rows)
    validate_columns(df, TRAJECTORY_REQUIRED, "trajectory")
    df["formula"] = df["formula"].astype(str)
    df["generation"] = df["generation"].astype(int)
    return df


class TrajectoryWriter:
    """세대별 후보 로그 append writer. miner adapter(instrumentation)가 사용."""

    def __init__(self, path: str, run_id: str, method: str, seed):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.base = {"run_id": run_id, "method": method, "seed": seed}
        self._fh = open(path, "a")

    def write(self, generation: int, idx_in_population: int, formula: str,
              raw_fitness: float, **extra) -> None:
        rec: Dict = dict(self.base)
        rec.update({"generation": int(generation),
                    "idx_in_population": int(idx_in_population),
                    "formula": str(formula),
                    "raw_fitness": float(raw_fitness)})
        rec.update(extra)
        self._fh.write(json.dumps(rec, default=str) + "\n")
        self._fh.flush()   # 장시간 마이닝 중단 시에도 진행분 보존 (내구성)

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
