"""Validity statistics — formula signal의 유효성 진단.

정의:
  * universe cell     : point-in-time universe mask가 True인 (일, 종목)
  * valid cell        : universe cell ∧ finite(signal)
  * daily coverage    : n_valid(t) / n_universe(t)   (n_universe=0이면 0)
  * correlatable day  : n_valid(t) ≥ 2 이고 그날 valid 값의 분산 > 0
  * const day         : n_valid(t) ≥ 2 이고 그날 valid 값이 전부 동일
  * 일별 통계(mean/median/p10 등)는 split의 **전체 거래일** 기준
    (valid cell이 없는 날은 n_valid=0, coverage=0으로 포함)

모든 임계값 비교는 ValidityGate(evaluator.py)의 몫이다 — 여기서는 통계만.
"""
from __future__ import annotations

from typing import Dict

import numpy as np


def compute_validity_stats(values: np.ndarray, universe_mask: np.ndarray) -> Dict:
    if values.shape != universe_mask.shape:
        raise ValueError("values와 universe_mask shape 불일치")
    T = values.shape[0]
    uni = universe_mask
    n_uni_daily = uni.sum(axis=1)
    n_uni_cells = int(n_uni_daily.sum())

    finite = np.isfinite(values) & uni
    nan_cells = int((np.isnan(values) & uni).sum())
    inf_cells = int((np.isinf(values) & uni).sum())

    n_valid_daily = finite.sum(axis=1)
    with np.errstate(all="ignore"):
        coverage_daily = np.where(n_uni_daily > 0, n_valid_daily / np.maximum(n_uni_daily, 1), 0.0)

    # 일별 상수/상관가능 판정 (valid 값 기준)
    v = np.where(finite, values.astype(np.float64), np.nan)
    import warnings as _w
    with np.errstate(all="ignore"), _w.catch_warnings():
        _w.simplefilter("ignore", category=RuntimeWarning)
        vmax = np.nanmax(v, axis=1)
        vmin = np.nanmin(v, axis=1)
    two_plus = n_valid_daily >= 2
    zero_var_day = two_plus & np.isclose(vmax, vmin, rtol=0.0, atol=0.0, equal_nan=False)
    correlatable_day = two_plus & ~zero_var_day

    n_valid_days = int((n_valid_daily >= 1).sum())
    stats = {
        "n_total_days": int(T),
        "n_valid_days": n_valid_days,
        "valid_day_ratio": n_valid_days / T if T else 0.0,
        "mean_daily_n_valid": float(n_valid_daily.mean()) if T else 0.0,
        "median_daily_n_valid": float(np.median(n_valid_daily)) if T else 0.0,
        "min_daily_n_valid": int(n_valid_daily.min()) if T else 0,
        "mean_daily_coverage_ratio": float(coverage_daily.mean()) if T else 0.0,
        "median_daily_coverage_ratio": float(np.median(coverage_daily)) if T else 0.0,
        "p10_daily_coverage_ratio": float(np.percentile(coverage_daily, 10)) if T else 0.0,
        "const_day_ratio": float(zero_var_day.sum() / max(int(two_plus.sum()), 1)),
        "n_correlatable_days": int(correlatable_day.sum()),
        "nan_cell_ratio": nan_cells / n_uni_cells if n_uni_cells else 1.0,
        "inf_cell_ratio": inf_cells / n_uni_cells if n_uni_cells else 0.0,
        "n_universe_cells": n_uni_cells,
        "n_valid_cells": int(n_valid_daily.sum()),
    }
    return stats
