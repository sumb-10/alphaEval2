"""Forward return / execution return 계산.

전부 positionwise(shift) 연산이므로 warmup 절단과 무관하게 full 패널에서
계산 후 슬라이스한다. qlib label `Ref($close,-1)/$close - 1`과 동일한
dtype 흐름(float32 나눗셈)을 따른다.

execution 모드별 return (t행 = t일에 관측된 신호에 귀속되는 수익):
  same_close        : close_{t+1}/close_t − 1     (legacy/optimistic —
                      t 종가 정보로 t 종가 체결 가정)
  next_open_oo      : open_{t+2}/open_{t+1} − 1   (t+1 시가 진입, t+2 시가 리밸런스)
  next_open_oc      : close_{t+1}/open_{t+1} − 1  (t+1 시가 진입, 당일 종가 청산)
  delayed_close_cc  : close_{t+2}/close_{t+1} − 1 (t+1 종가 진입, t+2 종가 청산)
"""
from __future__ import annotations

import numpy as np

EXECUTION_MODES = ("same_close", "next_open_oo", "next_open_oc", "delayed_close_cc")


def _lead(a: np.ndarray, k: int) -> np.ndarray:
    """a를 k일 미래로 당김: out[t] = a[t+k] (없으면 NaN)."""
    out = np.full_like(a, np.nan)
    if k == 0:
        out[:] = a
    else:
        out[:-k] = a[k:]
    return out


def forward_return(close: np.ndarray, k: int) -> np.ndarray:
    """close_{t+k}/close_t − 1 (float32 — qlib label과 동일 dtype 흐름)."""
    with np.errstate(all="ignore"):
        r = np.divide(_lead(close, k), close) - 1
    return r.astype(np.float32)


def execution_return(mode: str, close: np.ndarray, open_: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        if mode == "same_close":
            r = np.divide(_lead(close, 1), close) - 1
        elif mode == "next_open_oo":
            r = np.divide(_lead(open_, 2), _lead(open_, 1)) - 1
        elif mode == "next_open_oc":
            r = np.divide(_lead(close, 1), _lead(open_, 1)) - 1
        elif mode == "delayed_close_cc":
            r = np.divide(_lead(close, 2), _lead(close, 1)) - 1
        else:
            raise ValueError(f"unknown execution mode: {mode!r} (choose from {EXECUTION_MODES})")
        return r.astype(np.float32)
