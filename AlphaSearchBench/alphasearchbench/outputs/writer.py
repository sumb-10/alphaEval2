"""표준 결과 파일 writer — parquet 기본, 실패 시 pickle 폴백(기록 남김)."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import pandas as pd


class OutputWriter:
    def __init__(self, root: str):
        self.root = root
        for sub in ("metrics", "daily", "trajectory", "manifests", "cache", "plots"):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        self.written: List[str] = []
        self.fallbacks: List[str] = []

    def write_table(self, df: pd.DataFrame, name: str, subdir: str = "metrics") -> str:
        base = os.path.join(self.root, subdir, name)
        try:
            path = base + ".parquet"
            df.to_parquet(path, index=False)
        except Exception:
            path = base + ".pkl"
            df.to_pickle(path)
            self.fallbacks.append(path)
        self.written.append(path)
        return path

    def manifest_path(self, name: str) -> str:
        return os.path.join(self.root, "manifests", name)
