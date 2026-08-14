"""Diagnostics cache — formula → {signed IC, validity stats, eval error}.

스펙 #20: threshold/constraint mode 적용과 **분리**된 순수 진단 캐시.
threshold가 바뀌어도 신호·진단은 재계산하지 않는다. effective fitness는
fitness.py가 이 진단으로부터 파생시킨다.

key 문맥(formula 외의 cache key 구성요소 — market/universe/기간/데이터셋/
의미론 버전)은 run 단위로 고정되므로 DiagnosticsCache.context에 1회 기록해
덤프에 포함시킨다 (run 간 재사용 시 context 일치 검증용).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class DiagnosticsCache:
    def __init__(self, context: Dict[str, Any]):
        # context: {market, universe_hash, search_start, search_end,
        #           dataset_uri, semantics_version}
        self.context = dict(context)
        self._memo: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def __contains__(self, formula: str) -> bool:
        return formula in self._memo

    def get(self, formula: str) -> Optional[Dict[str, Any]]:
        d = self._memo.get(formula)
        if d is not None:
            self.hits += 1
        return d

    def put(self, formula: str, diag: Dict[str, Any]) -> None:
        self.misses += 1
        self._memo[formula] = diag

    def __len__(self) -> int:
        return len(self._memo)

    def all_items(self):
        return self._memo.items()

    def stats(self) -> Dict[str, int]:
        return {"unique_evaluations": len(self._memo),
                "memo_hits": self.hits,
                "total_lookups": self.hits + self.misses}
