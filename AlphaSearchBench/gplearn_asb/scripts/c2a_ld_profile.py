#!/usr/bin/env python
"""[C-2a] complexity(L/D) 프로파일러 — trajectory에서 bloat tail 실측.

계약 (docs/experiments/2026-08-19_C2_LD_evidence.md §C-2a, 동결):
  * 모집단 = 전체 generated candidate attempts (중복·invalid 무관 전부);
    admissible-only(validity_pass)는 보조 병기.
  * 완전성 assertion (분석 선행 gate — 위반 시 통계 없이 중단):
      rows == budget(=pop×gens) / 세대별 rows == population / 계량 실패 0
  * 고정 산출: overall P(L>Lb ∨ D>Db), 세대별 p95/p99/max/exceedance,
    전체 p95/p99/p99.9/max, 최종 population 분포, pool winner L/D.

계량: Python ast 기반 L(노드 수)/D(깊이, 잎=1) — GP prefix 문법에서
static_check._tree_size/_tree_depth와 동치(500수식 대조 불일치 0,
2026-08-19 검증; C2_LD_evidence.md와 동일 정의).

사용:
  python scripts/c2a_ld_profile.py --runs out/<run1> out/<run2> ... \
      [--bound-l 40 --bound-d 10] [--out <combined_summary.csv>]
"""
import argparse
import ast
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


def py_ld(formula: str):
    """ast 기반 (L, D). Call/BinOp/UnaryOp = 내부 노드 1, Name/Constant = 잎 1."""
    t = ast.parse(str(formula).replace("$", "F_"), mode="eval").body

    def size(n):
        if isinstance(n, ast.Call):
            return 1 + sum(size(a) for a in n.args)
        if isinstance(n, ast.BinOp):
            return 1 + size(n.left) + size(n.right)
        if isinstance(n, ast.UnaryOp):
            return 1 + size(n.operand)
        return 1

    def depth(n):
        if isinstance(n, ast.Call):
            return 1 + max(depth(a) for a in n.args)
        if isinstance(n, ast.BinOp):
            return 1 + max(depth(n.left), depth(n.right))
        if isinstance(n, ast.UnaryOp):
            return 1 + depth(n.operand)
        return 1

    return size(t), depth(t)


def profile_run(run_root: str, bound_l: int, bound_d: int) -> dict:
    run_id = os.path.basename(run_root.rstrip("/"))
    traj_path = os.path.join(run_root, "trajectory", f"{run_id}.jsonl")
    rows = []
    with open(traj_path) as fh:
        for line in fh:
            d = json.loads(line)
            rows.append((d["generation"], d["formula"],
                         bool(d.get("validity_pass", False))))
    df = pd.DataFrame(rows, columns=["generation", "formula", "validity_pass"])

    # ---- manifest에서 예산·population (완전성 기준) ----
    man_path = glob.glob(os.path.join(run_root, "manifests", "run_*.json"))[0]
    man = json.load(open(man_path))
    pop = int(man["gp_params"]["population_size"])
    gens = int(man["gp_params"]["generations"])
    budget = pop * gens

    # ---- 완전성 assertion (분석 선행 gate) ----
    errors = []
    if len(df) != budget:
        errors.append(f"rows={len(df)} != budget={budget}")
    gen_counts = df.groupby("generation").size()
    bad_gens = gen_counts[gen_counts != pop]
    if len(bad_gens):
        errors.append(f"세대별 rows != population: {dict(bad_gens)}")
    ld, fails = [], 0
    for f in df["formula"]:
        try:
            ld.append(py_ld(f))
        except Exception:
            ld.append((None, None)); fails += 1
    if fails:
        errors.append(f"L/D 계량 실패 rows={fails}")
    if errors:
        raise AssertionError(
            f"[{run_id}] trajectory 완전성 위반 — 분석 중단 (selection-bias "
            f"위험): " + "; ".join(errors))

    df["L"] = [x[0] for x in ld]
    df["D"] = [x[1] for x in ld]
    exceed = (df["L"] > bound_l) | (df["D"] > bound_d)

    # ---- 세대별 표 ----
    gen_rows = []
    for g, sub in df.groupby("generation"):
        gen_rows.append({
            "generation": g,
            "L_p95": float(np.percentile(sub["L"], 95)),
            "L_p99": float(np.percentile(sub["L"], 99)),
            "L_max": int(sub["L"].max()),
            "D_p95": float(np.percentile(sub["D"], 95)),
            "D_p99": float(np.percentile(sub["D"], 99)),
            "D_max": int(sub["D"].max()),
            "exceed_rate": float(exceed[sub.index].mean()),
        })
    gen_df = pd.DataFrame(gen_rows).sort_values("generation")
    out_csv = os.path.join(run_root, "metrics", "c2a_ld_profile_gen.csv")
    gen_df.to_csv(out_csv, index=False)

    # ---- pool winner ----
    pool_csv = glob.glob(os.path.join(run_root, "metrics", "final_pool_*.csv"))
    pool_ld = []
    if pool_csv:
        pf = pd.read_csv(pool_csv[0])
        pool_ld = [py_ld(f) for f in pf["formula"]]

    adm = df[df["validity_pass"]]
    summary = {
        "run_id": run_id, "population": pop, "generations": gens,
        "n_attempts": len(df),
        "exceed_overall": float(exceed.mean()),
        "n_exceed": int(exceed.sum()),
        "L_p95": float(np.percentile(df["L"], 95)),
        "L_p99": float(np.percentile(df["L"], 99)),
        "L_p999": float(np.percentile(df["L"], 99.9)),
        "L_max": int(df["L"].max()),
        "D_p95": float(np.percentile(df["D"], 95)),
        "D_p99": float(np.percentile(df["D"], 99)),
        "D_p999": float(np.percentile(df["D"], 99.9)),
        "D_max": int(df["D"].max()),
        "final_gen_L_max": int(df[df["generation"] == df["generation"].max()]["L"].max()),
        "final_gen_D_max": int(df[df["generation"] == df["generation"].max()]["D"].max()),
        "pool_L_max": max((x[0] for x in pool_ld), default=None),
        "pool_D_max": max((x[1] for x in pool_ld), default=None),
        # 보조: admissible-only
        "adm_n": len(adm),
        "adm_exceed": float(((adm["L"] > bound_l) | (adm["D"] > bound_d)).mean()) if len(adm) else float("nan"),
        "adm_L_max": int(adm["L"].max()) if len(adm) else None,
        "adm_D_max": int(adm["D"].max()) if len(adm) else None,
        "gen_table": out_csv,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="run root 디렉토리들")
    ap.add_argument("--bound-l", type=int, default=40)
    ap.add_argument("--bound-d", type=int, default=10)
    ap.add_argument("--out", default=None, help="combined summary CSV")
    args = ap.parse_args()

    summaries = []
    for r in args.runs:
        s = profile_run(r, args.bound_l, args.bound_d)
        summaries.append(s)
        print(f"\n[{s['run_id']}] {s['population']}x{s['generations']} "
              f"attempts={s['n_attempts']}")
        print(f"  exceed(L>{args.bound_l} ∨ D>{args.bound_d}): "
              f"{s['exceed_overall']*100:.3f}% (n={s['n_exceed']})")
        print(f"  L: p95={s['L_p95']:.0f} p99={s['L_p99']:.0f} "
              f"p99.9={s['L_p999']:.0f} max={s['L_max']}")
        print(f"  D: p95={s['D_p95']:.0f} p99={s['D_p99']:.0f} "
              f"p99.9={s['D_p999']:.0f} max={s['D_max']}")
        print(f"  final gen max L/D = {s['final_gen_L_max']}/{s['final_gen_D_max']}"
              f" | pool max L/D = {s['pool_L_max']}/{s['pool_D_max']}"
              f" | admissible-only exceed = {s['adm_exceed']*100:.3f}%")
    if args.out:
        pd.DataFrame(summaries).drop(columns=["gen_table"]).to_csv(args.out, index=False)
        print(f"\ncombined summary → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
