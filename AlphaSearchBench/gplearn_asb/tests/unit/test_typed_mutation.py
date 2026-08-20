"""unit — [v2] typed point mutation: 형별 교체 보장 (qlib 불필요).

legacy 결함(feature 인덱스 정수 대입 → 문법 밖 표본)이 v2에서 소멸함을 고정.
"""
import os
import sys

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gplearn_asb.mutation import typed_point_mutation                 # noqa: E402
from gplearn_asb.vendored_gplearn.config import (FEATURE_LIST,        # noqa: E402
                                                 functions_arity,
                                                 window_lengths)

ARITIES = {}
for op, ar in functions_arity.items():
    ARITIES.setdefault(ar, []).append(op)

PROGRAM = ["Div", "Less", "$low", "$change", "Mean", "$amount", 5]


def _mutate_many(p_replace=1.0, n=200, seed0=0):
    outs = []
    for s in range(seed0, seed0 + n):
        prog, mutated = typed_point_mutation(
            list(PROGRAM), np.random.RandomState(s), p_replace,
            FEATURE_LIST, ARITIES)
        outs.append((prog, mutated))
    return outs


def test_types_preserved_across_many_seeds():
    for prog, _m in _mutate_many():
        for orig, new in zip(PROGRAM, prog):
            if isinstance(orig, str) and orig in functions_arity:
                # 연산자 → 동일 arity 군의 연산자
                assert isinstance(new, str) and new in functions_arity
                assert functions_arity[new] == functions_arity[orig]
            elif isinstance(orig, str):
                # feature → feature 이름 (정수 유입 금지 = legacy 결함 소멸)
                assert isinstance(new, str) and new in FEATURE_LIST
            else:
                # window → window_lengths 내 값
                assert new in window_lengths


def test_feature_and_window_replacement_excludes_self():
    for prog, mutated in _mutate_many(p_replace=1.0, n=100):
        for i in mutated:
            orig, new = PROGRAM[i], prog[i]
            if isinstance(orig, str) and orig not in functions_arity:
                assert new != orig                      # feature는 반드시 교체
            elif not isinstance(orig, str):
                assert new != orig                      # window도 반드시 교체


def test_no_mutation_when_p_zero():
    prog, mutated = typed_point_mutation(list(PROGRAM), np.random.RandomState(0),
                                         0.0, FEATURE_LIST, ARITIES)
    assert prog == PROGRAM and mutated == []


def test_deterministic_given_seed():
    a, ma = typed_point_mutation(list(PROGRAM), np.random.RandomState(7), 0.5,
                                 FEATURE_LIST, ARITIES)
    b, mb = typed_point_mutation(list(PROGRAM), np.random.RandomState(7), 0.5,
                                 FEATURE_LIST, ARITIES)
    assert a == b and ma == mb


def _is_structurally_valid(program) -> bool:
    """flatten tree 구조 검사 — vendored validate_program과 동일 의미론의
    자체 구현 (vendored _program은 import 시 qlib 계약이 필요해 unit에서 배제).
    rolling(arity 4)은 자식 2개(입력, window)로 소비된다."""
    stack = [1]
    for node in program:
        if isinstance(node, str) and node in functions_arity:
            stack[-1] -= 1
            arity = functions_arity[node]
            stack.append(2 if arity == 4 else arity)
        else:
            stack[-1] -= 1
        while stack and stack[-1] == 0:
            stack.pop()
    return stack == []


def test_structure_still_valid_program():
    """교체 후에도 유효 트리인지 — typed mutation은 노드 교체만 하므로
    구조 불변이어야 한다."""
    assert _is_structurally_valid(PROGRAM)
    for prog, _m in _mutate_many(n=50):
        assert _is_structurally_valid(prog), prog
