#!/usr/bin/env python
"""[C-2a.3] preregistration 계산기 — treatment 실행 전, control 데이터만 사용.

A. ε = production-equivalent tournament 재구성에서 관측된
   strictly-positive (best − second_best) gap 분포의 p10.
   - tournament size 20, 복원추출, sentinel 처리 동일
   - gap은 best·second_best 모두 non-sentinel인 tournament에서만 수집
   - exact tie(gap=0)는 분포에서 제외하되 ε 안 취급(구현이 자동 보장)
   - 분석용 MC RNG seed 고정·기록 (treatment 아님 — preregistration 분석)
B. loose safety cap 후보표 — 후보 bound별 attempt/run/pool-winner exceedance.

사용: python scripts/c2a3_preregister.py --runs <5 control run roots> \
      --caps 80:18 100:20 --mc-seed 20260819 --out <prereg json>
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

WORST = -1e6
TOURNAMENT = 20
N_MC_PER_GEN = 2000     # 세대당 재구성 tournament 수


def py_ld(formula):
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


def load_run(run_root):
    run_id = os.path.basename(run_root.rstrip("/"))
    rows = []
    with open(os.path.join(run_root, "trajectory", f"{run_id}.jsonl")) as fh:
        for line in fh:
            d = json.loads(line)
            rows.append((d["generation"], d["formula"],
                         float(d["effective_fitness"])))
    return run_id, pd.DataFrame(rows, columns=["generation", "formula",
                                               "effective_fitness"])


def tournament_gaps(df, rng):
    """세대별 population(=그 세대의 전 개체)에서 production-equivalent
    tournament를 MC 재구성 — strictly positive non-sentinel gap 수집."""
    gaps = []
    for _, sub in df.groupby("generation"):
        f = sub["effective_fitness"].to_numpy()
        n = len(f)
        idx = rng.randint(0, n, size=(N_MC_PER_GEN, TOURNAMENT))
        samp = f[idx]
        samp.sort(axis=1)
        best, second = samp[:, -1], samp[:, -2]
        ok = (best > WORST) & (second > WORST)
        g = best[ok] - second[ok]
        gaps.append(g[g > 0])
    return np.concatenate(gaps) if gaps else np.array([])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--caps", nargs="+", default=["80:18", "100:20"])
    ap.add_argument("--mc-seed", type=int, default=20260819)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rng = np.random.RandomState(args.mc_seed)
    all_gaps, per_run = [], {}
    frames = {}
    for r in args.runs:
        run_id, df = load_run(r)
        frames[run_id] = df
        g = tournament_gaps(df, rng)
        per_run[run_id] = {"n_gaps": int(len(g)),
                           "p05": float(np.percentile(g, 5)),
                           "p10": float(np.percentile(g, 10)),
                           "p25": float(np.percentile(g, 25)),
                           "median": float(np.median(g))}
        all_gaps.append(g)
    pooled = np.concatenate(all_gaps)
    epsilon = float(np.percentile(pooled, 10))

    # ---- cap 후보표 ----
    cap_table = {}
    ld_cache = {}
    for run_id, df in frames.items():
        ld_cache[run_id] = np.array([py_ld(f) for f in df["formula"]])
    pool_ld = {}
    for r in args.runs:
        run_id = os.path.basename(r.rstrip("/"))
        pf = glob.glob(os.path.join(r, "metrics", "final_pool_*.csv"))
        pool_ld[run_id] = ([py_ld(f) for f in pd.read_csv(pf[0])["formula"]]
                           if pf else [])
    for cap in args.caps:
        L, D = (int(x) for x in cap.split(":"))
        runs_detail, total_exc, total_n, pool_exc = {}, 0, 0, 0
        for run_id in frames:
            ld = ld_cache[run_id]
            exc = int(((ld[:, 0] > L) | (ld[:, 1] > D)).sum())
            runs_detail[run_id] = {"exceed_n": exc,
                                   "exceed_pct": exc / len(ld) * 100}
            total_exc += exc
            total_n += len(ld)
            pool_exc += sum(1 for (l, d) in pool_ld[run_id]
                            if l > L or d > D)
        cap_table[f"L{L}_D{D}"] = {"overall_pct": total_exc / total_n * 100,
                                   "pool_winner_exceed": pool_exc,
                                   "per_run": runs_detail}

    out = {"mc_seed": args.mc_seed, "tournament_size": TOURNAMENT,
           "n_mc_per_gen": N_MC_PER_GEN,
           "gap_stats_pooled": {"n": int(len(pooled)),
                                "p05": float(np.percentile(pooled, 5)),
                                "p10": epsilon,
                                "p25": float(np.percentile(pooled, 25)),
                                "median": float(np.median(pooled))},
           "epsilon_p10": epsilon,
           "gap_stats_per_run": per_run,
           "cap_candidates": cap_table}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps({k: out[k] for k in
                      ("epsilon_p10", "gap_stats_pooled", "cap_candidates")},
                     indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
