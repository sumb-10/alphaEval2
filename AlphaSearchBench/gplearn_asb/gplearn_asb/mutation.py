"""[v2] typed point mutation — legacy 결함(정수 유입)을 제거한 형별 교체.

legacy(vendored _program.py:708-755)는 terminal 교체 시
`randint(n_features)` **정수 인덱스를 그대로 노드에 대입**해
① feature 자리에 상수 유사 노드(`Add(3, $close)`),
② rolling window 자리에 window_lengths 밖 값(`Var($factor, 6)`)을 만든다.

v2 규칙 (Vanilla_GP_v2.md §2.2):
  연산자        → 동일 arity 군의 다른 연산자 (legacy와 동일 — 자기 자신 허용)
  feature 이름  → **다른** feature 이름 (자기 자신 제외 — 교체 보장)
  window 정수   → **다른** window_lengths 값 (자기 자신 제외)

RNG는 개체별 random_state를 사용하며 legacy와 소비 순서가 다르다 —
v2는 새 baseline이므로 legacy 재현성과 무관하다(재현 앵커는 v2 자체
결정성 fixture).
"""
from __future__ import annotations

from copy import copy
from typing import List, Tuple

import numpy as np

from .vendored_gplearn.config import functions_arity, window_lengths


def typed_point_mutation(program: List, random_state,
                         p_point_replace: float,
                         feature_names: List[str],
                         arities: dict) -> Tuple[List, List[int]]:
    """flattened tree의 형별(type-preserving) point mutation.

    반환: (새 program, 교체된 노드 인덱스 목록) — vendored와 동일 계약.
    """
    program = copy(program)
    mutate = np.where(random_state.uniform(size=len(program))
                      < p_point_replace)[0]

    for node_idx in mutate:
        node = program[node_idx]
        if isinstance(node, str) and node in functions_arity:
            # 연산자 → 동일 arity 군 (legacy 의미론 유지: 자기 자신 허용)
            arity = functions_arity[node]
            group = arities[arity]
            program[node_idx] = group[random_state.randint(len(group))]
        elif isinstance(node, str):
            # feature 이름 → 다른 feature 이름
            candidates = [f for f in feature_names if f != node]
            if candidates:
                program[node_idx] = candidates[random_state.randint(len(candidates))]
        else:
            # 수치 노드 = rolling window → 다른 window_lengths 값
            candidates = [w for w in window_lengths if w != node]
            if candidates:
                program[node_idx] = candidates[random_state.randint(len(candidates))]

    return program, list(mutate)
