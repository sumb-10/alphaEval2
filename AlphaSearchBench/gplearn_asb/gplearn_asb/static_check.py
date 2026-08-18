"""[P2] 정적 사전검증 — 파스 트리 위 규칙 검사 (데이터 접근 없음).

사전 실측(scripts/measure_static_savings.py, 13 run/22,539 unique):
상수식 0.77%, bad_window 0%, canonical 병합 1.2% → canonical memo(P2-4)는
보류하고 1(상수 접기)·2(window 정합)·3(길이 상한, 기본 off)만 구현.

의미론 (캐시 순수성): 이 모듈의 산출은 전부 **formula-결정적**이라
DiagnosticsCache에 저장해도 안전하다. mode/config 의존 판정(길이 상한,
static gate의 데이터 스킵 여부)은 여기 두지 않는다 — 길이 상한은 fitness.py가
`program_size`와 config로 판정하고, 데이터 스킵은 evaluator가 penalty 모드
전용 캐시 네임스페이스에서만 수행한다(off 모드 루프홀 parity 보존).

static invalid ⊂ hard invalid 증명(행동 불변의 근거): 상수식은 단면 분산이
0 → 모든 날 r=NaN → zero_ic_observations/no_correlatable_day(hard).
따라서 penalty 모드에서 정적 선분류는 effective fitness를 바꾸지 않고
사유 문자열과 데이터 비용만 바꾼다.

주의 — window 규칙은 invalid가 아니라 **flag**다: 엔진(qlib 미러)은
window 0=expanding, 0<w<1 float=지수창으로 **유효 평가**하므로
(qlib_provider.extended_window), "w<1 → invalid"는 static ⊂ hard를 깨는
오판정이 된다 (계획 문구를 실측으로 정정; 13 run 실측 발생률 0%).
"""
from __future__ import annotations

from typing import Dict

ROLLING_OPS = {"Ref", "Mean", "Sum", "Std", "Var", "Skew", "Kurt", "Min", "Max",
               "IdxMin", "IdxMax", "Med", "Mad", "Delta", "Slope", "Rsquare",
               "Resi", "WMA", "EMA"}
# f(x,x) → 상수인 연산자만 (Sub→0, Div→1). Greater/Less는 qlib에서
# element-wise max/min이라 f(x,x)=x 항등 — 상수 아님 (qlib_provider.py:14,107).
IDENTICAL_CONST = {"Sub", "Div"}


def _render(node) -> str:
    kind = node[0]
    if kind == "f":
        return node[1]
    if kind == "c":
        return repr(node[1])
    _, op, args = node
    return f"{op}({','.join(_render(a) for a in args)})"


def _is_const(node) -> bool:
    kind = node[0]
    if kind == "c":
        return True
    if kind == "f":
        return False
    _, op, args = node
    if all(_is_const(a) for a in args):
        return True
    if (op in IDENTICAL_CONST and len(args) == 2
            and _render(args[0]) == _render(args[1])):
        return True
    return False


def _has_const_subtree(node) -> bool:
    if node[0] != "call":
        return False
    _, op, args = node
    if (op in IDENTICAL_CONST and len(args) == 2
            and _render(args[0]) == _render(args[1])):
        return True
    return any(_has_const_subtree(a) for a in args)


def _nonstd_window(node) -> bool:
    """비표준 window (w<0, 비정수) — 엔진은 대부분 유효 평가하므로 flag 전용."""
    if node[0] != "call":
        return False
    _, op, args = node
    if op in ROLLING_OPS and len(args) >= 2:
        w = args[-1]
        if w[0] == "c":
            try:
                if not float(w[1]).is_integer() or float(w[1]) < 0:
                    return True
            except (TypeError, ValueError):
                return True
    return any(_nonstd_window(a) for a in args)


def _tree_size(node) -> int:
    """노드 수 (gplearn program length와 동일 계량: 함수+터미널)."""
    if node[0] != "call":
        return 1
    return 1 + sum(_tree_size(a) for a in node[2])


def static_check(tree) -> Dict:
    """파스 트리 정적 검사 (formula-결정적 — 캐시 안전). 반환:
       static_invalid_reason: None | 'static_invalid:constant_expression'
         (static ⊂ hard가 증명된 규칙만 invalid — 모듈 docstring 참조)
       static_flag_constant_subtree: bool (기록 전용 — 탐색 불개입)
       static_flag_nonstd_window: bool (기록 전용 — 엔진은 유효 평가)
       program_size: int (길이 상한 판정 재료 — 판정 자체는 fitness.py)
    """
    reason = None
    if _is_const(tree):
        reason = "static_invalid:constant_expression"
    return {"static_invalid_reason": reason,
            "static_flag_constant_subtree": _has_const_subtree(tree),
            "static_flag_nonstd_window": _nonstd_window(tree),
            "program_size": _tree_size(tree)}
