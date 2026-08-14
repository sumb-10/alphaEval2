"""[Optional integration adapter] AutoAlpha trajectory 수집 — 최소 구현.

optional adapter이며 core의 필수 dependency가 아니다 (gplearn.py 주석 참조).

AutoAlpha(AlphaEval fork)의 알려진 한계(문서: AlphaEval/docs/AboutAutoAlpha.md):
  * 탐색이 전역 `random`을 사용해 seed 고정으로도 **비재현**
  * n_jobs>1에서 population 증식 버그, depth 계산 no-op 버그
따라서 이 어댑터는 "평가된 후보의 관찰 로깅"만 보장하며, genome 의미론은
best-effort다. 정식 Search-QD 비교는 gplearn 계열 또는 표준 스키마를
직접 생산하는 miner를 권장한다 (IMPLEMENTATION_NOTES.md).

사용: AutoAlpha 러너에서 evaluator를 감싼다 —
    ev = LoggingEvaluator(base_evaluator, writer, generation_provider)
평가 순간의 세대 번호를 알 수 없는 miner에는 generation_provider 콜백으로
현재 세대를 공급한다.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..inputs.trajectory import TrajectoryWriter


class LoggingEvaluator:
    """evaluator.evaluate(exprs) 호출을 가로채 trajectory에 기록하는 래퍼.

    miner-agnostic: 표준 evaluator 인터페이스(.evaluate, .ic_memo)만 가정.
    """

    def __init__(self, base, writer: TrajectoryWriter,
                 generation_provider: Optional[Callable[[], int]] = None):
        self._base = base
        self._writer = writer
        self._gen = generation_provider or (lambda: -1)
        self._idx = 0

    def __getattr__(self, name):
        return getattr(self._base, name)

    def evaluate(self, exprs):
        memo_before = set(getattr(self._base, "ic_memo", {}).keys())
        ics = self._base.evaluate(exprs)
        g = int(self._gen())
        for e, ic in zip(exprs, ics):
            self._writer.write(generation=g, idx_in_population=self._idx,
                               formula=e, raw_fitness=float(abs(ic)),
                               signed_train_IC=float(ic),
                               memo_hit=bool(e in memo_before))
            self._idx += 1
        return ics
