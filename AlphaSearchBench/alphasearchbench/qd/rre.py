"""RRE — Relative Rank Entropy. legacy와 research(QD) 구현을 분리한다.

RRE_legacy  (provenance: AlphaEval backtest/modeltester.py 313-327행 재현):
  * union 그리드에서 pandas rank(axis=1) (ascending, tie=average)
  * p = R/ΣR (그날 자기 유니버스 정규화)
  * KL 항에 eps=1e-8이 분자·분모에 들어가고, universe가 바뀌면
    **재정규화 없는 교집합 합산**이 된다 (진짜 KL 아님 — 문서화된 legacy 동작)
  * sign 반전에 불변이 아님 (실측: v2 blueprint §C5)

RRE_qd (research):
  * train_sign 적용된 oriented signal 사용 (호출자가 orientation 적용)
  * 날짜쌍마다 공통 universe U_t ∩ U_{t-1}에서 rank/정규화를 **다시** 계산
  * KL_t = Σ p_t log(p_t/p_{t-1}),  RRE = mean_t 1/(1+KL_t)
  * mean_common_n / min_common_n / n_pairs_used / n_pairs_skipped 기록
  * eps 불필요 (rank≥1 → p>0)

두 값을 같은 이름으로 저장하지 않는다.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def rre_legacy(values_with_nan: np.ndarray, eps: float = 1e-8) -> float:
    """AlphaEval 공개코드 재현. 입력: (T×N), 비유니버스/결측은 NaN."""
    df = pd.DataFrame(values_with_nan)
    ranks = df.rank(axis=1)                          # ascending, tie=average
    probs = ranks.div(ranks.sum(axis=1), axis=0)
    probs_prev = probs.shift(1)
    kl = (probs * np.log((probs + eps) / (probs_prev + eps))).sum(axis=1)
    rre_series = kl.iloc[1:].dropna()
    if len(rre_series) == 0:
        return float("nan")
    return float((1.0 / (1.0 + rre_series)).mean())


def rre_qd(oriented: np.ndarray, valid: np.ndarray,
           min_common: int = 2) -> Dict[str, float]:
    """교집합 재정규화 RRE (research). 반환: rre_qd + 공통표본 진단."""
    T = oriented.shape[0]
    v = valid & np.isfinite(oriented)
    rres = []
    common_ns = []
    skipped = 0
    for t in range(1, T):
        m = v[t] & v[t - 1]
        nc = int(m.sum())
        if nc < min_common:
            skipped += 1
            continue
        r_t = rankdata(oriented[t, m])               # ascending, tie=average
        r_p = rankdata(oriented[t - 1, m])
        p_t = r_t / r_t.sum()
        p_p = r_p / r_p.sum()
        kl = float((p_t * np.log(p_t / p_p)).sum())
        rres.append(1.0 / (1.0 + kl))
        common_ns.append(nc)
    if not rres:
        return {"rre_qd": float("nan"), "rre_mean_common_n": float("nan"),
                "rre_min_common_n": 0, "rre_n_pairs_used": 0,
                "rre_n_pairs_skipped": skipped}
    return {"rre_qd": float(np.mean(rres)),
            "rre_mean_common_n": float(np.mean(common_ns)),
            "rre_min_common_n": int(np.min(common_ns)),
            "rre_n_pairs_used": len(rres),
            "rre_n_pairs_skipped": skipped}
