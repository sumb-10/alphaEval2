"""Point-in-time universe mask.

Provenance: AlphaEval scripts/tensor_eval.py `_build_universe_mask` 재구현.
csi 계열 instruments 파일은 (편입일, 편출일) span을 담으므로 이 마스크는
생존 편향 없는 point-in-time membership이다.
"""
from __future__ import annotations

import hashlib
from typing import Tuple

import numpy as np
import pandas as pd


def build_universe_mask(market: str, sel_dates: pd.DatetimeIndex,
                        columns: pd.Index) -> Tuple[np.ndarray, str]:
    """(len(sel_dates) × len(columns)) bool 마스크 + universe hash."""
    from qlib.data import D
    spans_d = D.list_instruments(
        D.instruments(market=market),
        start_time=str(sel_dates[0].date()), end_time=str(sel_dates[-1].date()),
        freq="day", as_list=False)
    mask = np.zeros((len(sel_dates), len(columns)), dtype=bool)
    col_pos = {c: i for i, c in enumerate(columns)}
    h = hashlib.sha256()
    for inst in sorted(spans_d):
        spans = spans_d[inst]
        j = col_pos.get(inst)
        for b, e in spans:
            h.update(f"{inst}|{b}|{e};".encode())
            if j is None:
                continue
            i0 = sel_dates.searchsorted(pd.Timestamp(b))
            i1 = sel_dates.searchsorted(pd.Timestamp(e), side="right")
            mask[i0:i1, j] = True
    return mask, h.hexdigest()[:16]
