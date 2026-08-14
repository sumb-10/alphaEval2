"""Diversity Entropy — pool-level (individual descriptor로 사용 금지).

두 종류를 구분한다:

AlphaEval_DE_legacy (provenance: backtest/modeltester.py 202-229행 재현):
  * 각 factor를 일별 cross-sectional z-score → **결측 NaN→0** → (time,asset)
    flatten → np.cov(rowvar=False) → eigvalsh → 음수 0 클립 →
    DE = −Σ p log p / log(m).
  * NaN→0 채움은 상장 기간이 다른 종목이 많을수록 λ 스펙트럼을 평평하게
    만들어 DE를 부풀릴 수 있다(문서화된 legacy 동작).

DE_common_valid (research):
  * validity gate 통과 factor만 사용 (호출자가 필터, n_factors_dropped 기록)
  * 모든 factor가 동시에 valid한 **common cells**에서만 계산.
  * common cells에서 일별 z-score 후 공분산 (일별 관측<2인 날의 z는 0).
  * 표본 불충분(n_common_cells < 2)이면 억지 값 대신 NaN + reason.
  * pairwise DE는 v0.1 공식 metric으로 구현하지 않는다 (PSD 문제 — 스펙).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np


def _eig_entropy(cov: np.ndarray, m: int) -> float:
    eigs = np.linalg.eigvalsh(cov)
    eigs = np.clip(eigs, 0, None)
    total = eigs.sum()
    if total <= 0 or m < 2:
        return float("nan")
    p = eigs / total
    p = p[p > 0]
    return float(-(p * np.log(p)).sum() / np.log(m))


def de_legacy(z_filled_list: Sequence[np.ndarray]) -> float:
    """입력: factor별 (T×N) — 이미 일별 z-score + NaN→0 처리된 행렬."""
    m = len(z_filled_list)
    if m < 2:
        return float("nan")
    mat = np.stack([z.reshape(-1) for z in z_filled_list], axis=1)
    if mat.shape[0] < 2:
        return float("nan")
    cov = np.cov(mat, rowvar=False)
    return _eig_entropy(cov, m)


def de_common_valid(values_list: Sequence[np.ndarray],
                    valid_list: Sequence[np.ndarray],
                    universe_mask: np.ndarray,
                    n_factors_dropped: int = 0) -> Dict:
    """모든 factor가 valid한 common cells에서의 DE.

    반환 dict: de_common_valid, n_common_cells, common_cell_ratio,
               n_factors_used, n_factors_dropped, reason(optional)
    """
    m = len(values_list)
    base = {
        "n_factors_used": m,
        "n_factors_dropped": int(n_factors_dropped),
    }
    if m < 2:
        return {**base, "de_common_valid": float("nan"),
                "n_common_cells": 0, "common_cell_ratio": 0.0,
                "reason": "insufficient_factors"}
    common = valid_list[0].copy()
    for v in valid_list[1:]:
        common &= v
    n_common = int(common.sum())
    n_uni = int(universe_mask.sum())
    base.update({
        "n_common_cells": n_common,
        "common_cell_ratio": n_common / n_uni if n_uni else 0.0,
    })
    if n_common < 2:
        return {**base, "de_common_valid": float("nan"),
                "reason": "insufficient_common_cells"}

    # common cells에서 일별 z-score (factor별) 후 공분산
    cols = []
    for values in values_list:
        v = np.where(common, values.astype(np.float64), np.nan)
        with np.errstate(all="ignore"):
            mu = np.nanmean(v, axis=1, keepdims=True)
            sd = np.nanstd(v, axis=1, keepdims=True)
            sd = np.where(sd < 1e-8, 1.0, sd)
            z = (v - mu) / sd
        z[~np.isfinite(z)] = 0.0
        cols.append(z.reshape(-1)[common.reshape(-1)])
    mat = np.stack(cols, axis=1)
    cov = np.cov(mat, rowvar=False)
    return {**base, "de_common_valid": _eig_entropy(cov, m), "reason": None}
