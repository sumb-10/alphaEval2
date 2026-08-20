"""unit — [C-2a.3] ε-lexicographic tournament 선택 계약 (qlib 불필요).

계약: ε 밖 → fitness 우선 / ε 안 → 최소 L → 최소 D → 최소 인덱스 /
전원 sentinel → 현행 argmax semantics / 순수 함수(RNG 불소비·결정성).
"""
import os
import sys

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gplearn_asb.genetic import flat_program_depth, lexi_select  # noqa: E402

# 문법: Div/Less binary(2), Mean rolling(마커 4 → 실효 2)
NA = {"Div": 2, "Less": 2, "Mean": 4, "Abs": 1}
WORST = -1e6

P_LEN7 = ["Div", "Less", "$low", "$change", "Mean", "$amount", 5]   # L7 D3
P_LEN5 = ["Less", "Abs", "$low", "Mean", "$close"]                  # 구조 무관 — 길이만 사용
P_LEN3_D2 = ["Abs", "Abs", "$low"]                                  # L3 D3
P_LEN3_FLAT = ["Div", "$low", "$high"]                              # L3 D2
P_TERM = ["$close"]                                                 # L1 D1


def test_depth_handcalc():
    assert flat_program_depth(P_TERM, NA) == 1
    assert flat_program_depth(P_LEN7, NA) == 3      # Div(Less(l,c), Mean(a,5))
    assert flat_program_depth(P_LEN3_D2, NA) == 3   # Abs(Abs(x))
    assert flat_program_depth(P_LEN3_FLAT, NA) == 2
    assert flat_program_depth(["Mean", "$close", 12], NA) == 2


def test_fitness_wins_outside_epsilon():
    # 차이 0.02 > ε=0.01 → 긴 쪽이라도 fitness 승리 (현행과 동일 승자)
    j = lexi_select([0.10, 0.12], [P_LEN3_FLAT, P_LEN7], True, WORST, 0.01, NA)
    assert j == 1


def test_shorter_wins_inside_epsilon():
    # 차이 0.005 ≤ ε=0.01 → 짧은 후보 승리
    j = lexi_select([0.115, 0.12], [P_LEN3_FLAT, P_LEN7], True, WORST, 0.01, NA)
    assert j == 0
    # exact tie도 당연히 ε 안
    j = lexi_select([0.12, 0.12], [P_LEN7, P_LEN3_FLAT], True, WORST, 0.01, NA)
    assert j == 1


def test_same_length_shallower_wins():
    j = lexi_select([0.12, 0.12], [P_LEN3_D2, P_LEN3_FLAT], True, WORST, 0.01, NA)
    assert j == 1                                    # L 동일 3, D 3 vs 2


def test_full_tie_deterministic_first_index():
    j = lexi_select([0.12, 0.12], [P_LEN3_FLAT, list(P_LEN3_FLAT)],
                    True, WORST, 0.01, NA)
    assert j == 0


def test_all_sentinel_keeps_argmax_semantics():
    # 전원 worst → 현행 np.argmax(첫 최대) 그대로, tie-break 미개입
    j = lexi_select([WORST, WORST, WORST], [P_LEN7, P_LEN3_FLAT, P_TERM],
                    True, WORST, 0.01, NA)
    assert j == 0
    # sentinel 혼재: sentinel은 near-tie 후보에서 제외
    j = lexi_select([WORST, 0.12, 0.115], [P_TERM, P_LEN7, P_LEN3_FLAT],
                    True, WORST, 0.01, NA)
    assert j == 2                                    # ε 안 valid 중 최단


def test_pure_function_no_rng_and_deterministic():
    args = ([0.115, 0.12], [P_LEN3_FLAT, P_LEN7], True, WORST, 0.01, NA)
    assert lexi_select(*args) == lexi_select(*args)  # 재호출 동일 (RNG 인자 자체가 없음)
