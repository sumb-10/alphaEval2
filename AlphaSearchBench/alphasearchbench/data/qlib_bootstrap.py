"""Qlib 초기화 및 기본 데이터 접근 (Phase 0 범위).

formula 평가기는 qlib_provider.py(Phase 1)가 담당한다. 이 모듈은
- qlib.init (idempotent)
- 캘린더/유니버스/원시 필드 조회 헬퍼
만 제공한다. AlphaEval 내부 모듈은 import하지 않는다.
"""
from __future__ import annotations

from typing import List, Optional

_INITIALIZED_URI: Optional[str] = None


def bootstrap_qlib(provider_uri: str, region: str = "cn", kernels: int = 8) -> None:
    """qlib.init을 1회만 수행. 다른 uri로 재호출 시 에러 (조용한 재설정 방지)."""
    global _INITIALIZED_URI
    if _INITIALIZED_URI is not None:
        if _INITIALIZED_URI != provider_uri:
            raise RuntimeError(
                f"qlib already initialized with {_INITIALIZED_URI!r}; "
                f"refusing to re-init with {provider_uri!r}"
            )
        return
    import qlib
    qlib.init(provider_uri=provider_uri, region=region, kernels=kernels,
              expression_cache=None, dataset_cache=None)
    _INITIALIZED_URI = provider_uri


def get_calendar(start_time: str, end_time: str):
    from qlib.data import D
    return list(D.calendar(start_time=start_time, end_time=end_time, freq="day"))


def get_instruments_config(market: str):
    from qlib.data import D
    return D.instruments(market=market)


def list_instrument_spans(market: str, start_time: str, end_time: str):
    """종목별 point-in-time membership span dict: {inst: [(begin, end), ...]}"""
    from qlib.data import D
    return D.list_instruments(D.instruments(market=market),
                              start_time=start_time, end_time=end_time,
                              freq="day", as_list=False)


def fetch_field(instruments, field: str, start_time: str, end_time: str):
    """단일 원시 필드 조회 (MultiIndex (instrument, datetime) DataFrame)."""
    from qlib.data import D
    return D.features(instruments, [field], start_time=start_time,
                      end_time=end_time, freq="day")
