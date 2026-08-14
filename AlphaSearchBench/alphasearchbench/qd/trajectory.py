"""Search-QD — trajectory의 behavior-space 탐색 분석.

Final-Pool QD("최종적으로 무엇을 남겼는가")와 Search-QD("어떤 행동 공간을
어떻게 탐색했는가")는 별개 분석이다. 이 모듈은 후자를 담당한다.

입력 계약: 표준 trajectory DataFrame(inputs/trajectory.py) +
formula별 정보 테이블(descriptor/PC/quality/valid — 외부에서 계산).
core는 miner 내부 구현을 모른다.

dedup 원칙: QD point는 formula string exact dedup(첫 등장 기준),
원본 population 기록은 보존한다(이 함수들은 입력을 변경하지 않음).
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .grid import QDGrid


def unique_candidates(traj: pd.DataFrame) -> pd.DataFrame:
    """formula exact dedup(첫 등장 순서 보존). 원본은 그대로 둔다."""
    return traj.drop_duplicates(subset="formula", keep="first").reset_index(drop=True)


def search_budget(traj: pd.DataFrame,
                  wall_clock_seconds: Optional[float] = None) -> Dict:
    gens = traj["generation"]
    per_gen = traj.groupby("generation")["formula"].count()
    budget = {
        "total_evaluations": int(len(traj)),
        "unique_evaluations": int(traj["formula"].nunique()),
        "generations": int(gens.nunique()),
        "population_size": int(per_gen.max()) if len(per_gen) else 0,
        "wall_clock_seconds": wall_clock_seconds,
    }
    if "memo_hit" in traj.columns:
        mh = traj["memo_hit"].fillna(False).astype(bool)
        budget["memo_hit_ratio"] = float(mh.mean())
    return budget


def generation_metrics(traj: pd.DataFrame, formula_info: pd.DataFrame,
                       grid: QDGrid,
                       quality_col: str = "quality",
                       hq_threshold: Optional[float] = None) -> pd.DataFrame:
    """세대별 탐색 지표.

    formula_info: [formula, pc1, pc2, valid(bool), <quality_col>] — 세대 지표는
    각 세대의 **unique·valid·projected** 후보 기준으로 계산한다.
    """
    need = {"formula", "pc1", "pc2", "valid"}
    if not need.issubset(formula_info.columns):
        raise ValueError(f"formula_info에 {sorted(need)} 컬럼이 필요합니다")
    info = formula_info.drop_duplicates(subset="formula").set_index("formula")

    rows = []
    seen_bins = set()
    prev_centroid = None
    for g in sorted(traj["generation"].unique()):
        pop = traj[traj["generation"] == g]
        uniq = pop.drop_duplicates(subset="formula")
        merged = uniq.join(info, on="formula", how="left", rsuffix="_info")
        valid = merged["valid"].fillna(False).astype(bool)
        pcs = merged.loc[valid, ["pc1", "pc2"]].to_numpy(dtype=float)
        projected = np.isfinite(pcs).all(axis=1) if len(pcs) else np.array([], dtype=bool)
        pts = pcs[projected] if len(pcs) else pcs

        row: Dict = {
            "generation": int(g),
            "n_candidates": int(len(pop)),
            "n_unique": int(len(uniq)),
            "valid_candidate_rate": float(valid.mean()) if len(merged) else float("nan"),
        }
        q = merged.loc[valid, quality_col].astype(float) if quality_col in merged else pd.Series(dtype=float)
        row["mean_quality"] = float(q.mean()) if len(q) else float("nan")
        row["median_quality"] = float(q.median()) if len(q) else float("nan")
        if hq_threshold is not None and len(q):
            row["hq_rate"] = float((q >= hq_threshold).mean())

        if len(pts):
            pm = grid.pool_metrics(pts)
            row.update({"coverage": pm["coverage"],
                        "occupancy_entropy": pm["occupancy_entropy_global"],
                        "overflow_ratio": pm["overflow_ratio"]})
            a = grid.assign(pts)
            bins = {(int(x), int(y)) for x, y in
                    zip(a["bin_x"][a["in_bounds"]], a["bin_y"][a["in_bounds"]])}
            row["new_occupied_bins"] = len(bins - seen_bins)
            seen_bins |= bins
            row["cumulative_occupied_bins"] = len(seen_bins)
            centroid = pts.mean(axis=0)
            row["centroid_pc1"], row["centroid_pc2"] = float(centroid[0]), float(centroid[1])
            row["centroid_displacement"] = (
                float(np.linalg.norm(centroid - prev_centroid))
                if prev_centroid is not None else float("nan"))
            prev_centroid = centroid
        else:
            row.update({"coverage": float("nan"), "occupancy_entropy": float("nan"),
                        "overflow_ratio": float("nan"), "new_occupied_bins": 0,
                        "cumulative_occupied_bins": len(seen_bins),
                        "centroid_pc1": float("nan"), "centroid_pc2": float("nan"),
                        "centroid_displacement": float("nan")})
        rows.append(row)
    return pd.DataFrame(rows)
