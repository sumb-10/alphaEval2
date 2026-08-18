"""[P0] 정적 사전검증층의 절감 기대치 실측 (기존 trajectory, 데이터 접근 없음).

측정: (a) 전체가 상수로 접히는 수식 비율, (b) bad window(<1/비정수) 비율,
(c) canonical 정규화(교환법칙 인자 정렬)로 합쳐지는 중복 평가 비율.
"""
import os
import sys
from glob import glob

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_ASB = os.path.dirname(_PKG)
sys.path.insert(0, _ASB)

from alphasearchbench.data.qlib_provider import parse_expression  # noqa: E402

COMMUTATIVE = {"Add", "Mul", "Greater", "Less"}
IDENTICAL_CONST = {"Sub", "Div"}   # f(x,x)→상수 (Greater/Less는 max/min=항등)
ROLLING_1ARG = {"Ref", "Mean", "Sum", "Std", "Var", "Skew", "Kurt", "Min", "Max",
                "IdxMin", "IdxMax", "Med", "Mad", "Delta", "Slope", "Rsquare",
                "Resi", "WMA", "EMA"}


def render(node):
    kind = node[0]
    if kind == "f":
        return node[1]
    if kind == "c":
        return repr(node[1])
    _, op, args = node
    return f"{op}({','.join(render(a) for a in args)})"


def canonical(node):
    kind = node[0]
    if kind != "call":
        return node
    _, op, args = node
    cargs = [canonical(a) for a in args]
    if op in COMMUTATIVE and len(cargs) == 2:
        cargs = sorted(cargs, key=render)
    return ("call", op, cargs)


def is_const(node):
    kind = node[0]
    if kind == "c":
        return True
    if kind == "f":
        return False
    _, op, args = node
    if all(is_const(a) for a in args):
        return True
    if op in IDENTICAL_CONST and len(args) == 2 and render(args[0]) == render(args[1]):
        return True
    return False


def bad_window(node):
    if node[0] != "call":
        return False
    _, op, args = node
    if op in ROLLING_1ARG and len(args) >= 2:
        w = args[-1]
        if w[0] == "c" and (not float(w[1]).is_integer() or int(w[1]) < 1):
            return True
    return any(bad_window(a) for a in args)


def main():
    rows = []
    for tj in sorted(glob(os.path.join(_PKG, "out", "pilot_csi800_*", "trajectory", "*.jsonl"))):
        rid = os.path.basename(tj).replace(".jsonl", "")
        t = pd.read_json(tj, lines=True)
        uniq = t.drop_duplicates("formula")["formula"]
        n = len(uniq)
        n_const = n_badw = n_parsefail = 0
        canon = {}
        for f in uniq:
            try:
                tree = parse_expression(f)
            except Exception:
                n_parsefail += 1
                continue
            if is_const(tree):
                n_const += 1
            if bad_window(tree):
                n_badw += 1
            canon.setdefault(render(canonical(tree)), 0)
            canon[render(canonical(tree))] += 1
        n_canon_dup = sum(v - 1 for v in canon.values() if v > 1)
        rows.append({"run": rid, "unique": n, "parse_fail": n_parsefail,
                     "const_expr": n_const, "bad_window": n_badw,
                     "canonical_merged": n_canon_dup,
                     "const%": 100 * n_const / n, "badw%": 100 * n_badw / n,
                     "canon%": 100 * n_canon_dup / n})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print("\n합계: unique {:,} / const {:,} / bad_window {:,} / canonical 병합 {:,}"
          .format(df["unique"].sum(), df["const_expr"].sum(),
                  df["bad_window"].sum(), df["canonical_merged"].sum()))


if __name__ == "__main__":
    main()
