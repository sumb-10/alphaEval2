"""OOS signal-level metrics: daily IC/RankIC series와 집계.

정의 (research protocol):
  * daily IC   : 날짜 t의 valid cell(finite signal ∧ PIT universe ∧ finite
                 forward return)에서 Pearson corr. 유효쌍<2 또는 분산 0이면 NaN.
  * daily RankIC: 같은 cell 집합에서 일별 rank(tie=average) 후 Pearson(=Spearman).
  * Mean IC    : finite daily IC의 평균
  * ICIR       : mean(daily_IC)/std(daily_IC, ddof=1)  — raw (√252 없음)
                 (provenance: AlphaForge train_AFF.py의 icir 관례)
  * *_ann      : raw × √252 (별도 컬럼)

legacy와의 차이(문서화): AlphaEval ictester.calculate1은 ±inf 셀을 corr에
포함시켜 그날 IC를 NaN으로 만들고, NaN일 비율>50%면 0.0을 반환한다. ASB는
inf를 invalid cell로 제외하고(validity가 진단), 병리 요약은 0.0 치환이 아니라
validity/invalid_reason으로 보고한다.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

ANNUALIZATION_DAYS = 252


def masked_daily_corr(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """일별 cross-sectional Pearson corr (float64). 유효쌍<2 또는 퇴화 → NaN.

    provenance: AlphaEval scripts/tensor_eval.py `_daily_ic`의 합산식.
    """
    v = valid & np.isfinite(a) & np.isfinite(b)
    cnt = v.sum(axis=1)
    fa = np.where(v, a, 0).astype(np.float64)
    fb = np.where(v, b, 0).astype(np.float64)
    with np.errstate(all="ignore"):
        safe = np.where(cnt == 0, 1, cnt)
        sa, sb = fa.sum(1), fb.sum(1)
        cov = (fa * fb).sum(1) - sa * sb / safe
        va = (fa * fa).sum(1) - sa * sa / safe
        vb = (fb * fb).sum(1) - sb * sb / safe
        r = cov / np.sqrt(va * vb)
    r[cnt < 2] = np.nan
    r[~np.isfinite(r)] = np.nan
    return r


def daily_ic_series(values: np.ndarray, fwd: np.ndarray,
                    valid: np.ndarray) -> np.ndarray:
    return masked_daily_corr(values, fwd, valid)


def daily_rank_ic_series(values: np.ndarray, fwd: np.ndarray,
                         valid: np.ndarray) -> np.ndarray:
    """일별 Spearman = 쌍별 valid cell에서 rank(tie=average) 후 Pearson."""
    v = valid & np.isfinite(values) & np.isfinite(fwd)
    a = pd.DataFrame(np.where(v, values.astype(np.float64), np.nan)).rank(axis=1)
    b = pd.DataFrame(np.where(v, fwd.astype(np.float64), np.nan)).rank(axis=1)
    return masked_daily_corr(a.to_numpy(), b.to_numpy(), v)


def aggregate_ic(ic: np.ndarray) -> Dict[str, float]:
    """{mean, icir, icir_ann, n_obs} — finite 일별 값 기준. n_obs<2 → icir NaN."""
    finite = ic[np.isfinite(ic)]
    n = int(len(finite))
    mean = float(finite.mean()) if n else float("nan")
    if n >= 2:
        sd = float(finite.std(ddof=1))
        icir = mean / sd if sd > 0 else float("nan")
    else:
        icir = float("nan")
    return {
        "mean": mean,
        "icir": icir,
        "icir_ann": icir * np.sqrt(ANNUALIZATION_DAYS) if np.isfinite(icir) else float("nan"),
        "n_obs": n,
    }
