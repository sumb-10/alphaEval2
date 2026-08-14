"""Generation-level 통계 수집 (스펙 #15/16/18) — trajectory와 별도 산출물.

trajectory row 자체는 ASB inputs/trajectory.py TrajectoryWriter를 그대로
재사용한다 (genetic.py에서). 이 모듈은 세대별 population-collapse /
parent-diversity 진단을 담당한다.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def generation_row(gen: int, infos: List[Dict[str, Any]],
                   genomes: List[Dict[str, Any]],
                   wall_seconds: float,
                   n_memo_hits: int) -> Dict[str, Any]:
    """한 세대의 candidate info(list of apply_constraint 결과+진단 병합)와
    genome(list of {operation, parent_idx[, donor_idx]})로 통계 행 생성."""
    n = len(infos)
    formulas = [i["formula"] for i in infos]
    uniq = set(formulas)
    valid_mask = [bool(i["validity_pass"]) for i in infos]
    hard_inv = [bool(i["hard_invalid"]) for i in infos]
    res_inv = [bool(i["research_invalid"]) for i in infos]
    uniq_valid = {f for f, v in zip(formulas, valid_mask) if v}

    def _nanstat(vals, fn):
        arr = np.asarray([v for v in vals if v is not None], dtype=float)
        arr = arr[np.isfinite(arr)]
        return float(fn(arr)) if len(arr) else float("nan")

    raw = [i["raw_fitness"] for i in infos]
    raw_valid = [i["raw_fitness"] for i, v in zip(infos, valid_mask) if v]
    eff = [i["effective_fitness"] for i in infos]
    cov = [i.get("mean_daily_coverage_ratio") for i in infos]
    nvalid = [i.get("median_daily_n_valid") for i in infos]

    # parent diversity (스펙 #16) — 이 세대 offspring이 실제로 뽑은 부모 인덱스
    picks: List[int] = []
    for g in genomes:
        if g.get("parent_idx") is not None:
            picks.append(int(g["parent_idx"]))
        if g.get("donor_idx") is not None:
            picks.append(int(g["donor_idx"]))
    if picks:
        freq = Counter(picks)
        total = sum(freq.values())
        probs = np.array([c / total for c in freq.values()])
        entropy = float(-(probs * np.log(probs)).sum())
        top_share = float(max(freq.values()) / total)
        n_unique_parents = len(freq)
    else:  # gen 0
        entropy, top_share, n_unique_parents = float("nan"), float("nan"), 0

    return {
        "generation": int(gen),
        "population_size": n,
        "n_candidates": n,
        "n_unique": len(uniq),
        "n_unique_valid": len(uniq_valid),
        "n_hard_valid": int(sum(not h for h in hard_inv)),
        "n_research_valid": int(sum(not r for r in res_inv)),
        "n_invalid": int(sum(not v for v in valid_mask)),
        "hard_invalid_rate": float(sum(hard_inv) / n) if n else float("nan"),
        "research_invalid_rate": float(sum(res_inv) / n) if n else float("nan"),
        "valid_candidate_rate": float(sum(valid_mask) / n) if n else float("nan"),
        "mean_signal_coverage": _nanstat(cov, np.mean),
        "median_signal_coverage": _nanstat(cov, np.median),
        "median_n_valid": _nanstat(nvalid, np.median),
        "mean_raw_train_IC": _nanstat(raw, np.mean),
        "best_raw_train_IC": _nanstat(raw, np.max),
        "mean_valid_train_IC": _nanstat(raw_valid, np.mean),
        "best_valid_train_IC": _nanstat(raw_valid, np.max),
        "mean_effective_fitness": _nanstat(eff, np.mean),
        "best_effective_fitness": _nanstat(eff, np.max),
        "n_unique_parents_selected": n_unique_parents,
        "parent_selection_entropy": entropy,
        "top_parent_selection_share": top_share,
        "n_memo_hits": int(n_memo_hits),
        "wall_seconds": float(wall_seconds),
    }


class GenStatsCollector:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []

    def add(self, row: Dict[str, Any]) -> None:
        self.rows.append(row)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

    def save(self, path_base: str) -> str:
        df = self.to_frame()
        try:
            p = path_base + ".parquet"
            df.to_parquet(p, index=False)
        except Exception:
            p = path_base + ".csv"
            df.to_csv(p, index=False)
        return p
