"""gplearn_asb CLI — validity-aware GP mining 실행.

사용 (AlphaSearchBench/gplearn_asb/ 에서):
  python -m gplearn_asb.cli mine --config configs/smoke.yaml \
      [--mode off|hard_penalty|strict_penalty] [--seed N] [--out DIR] [--run-id ID]

import 순서 계약 (원본 러너 scripts/run_gplearn_fast.py:56-68 패턴):
  (1) 실제 qlib bootstrap → (2) qlib.init no-op 치환(ictester의 placeholder
  init 차단) → (3) backtest.backtester sys.modules 사전 등록 → (4) 그 후에만
  vendored gplearn import (모듈 기본 인자가 import 시점에 D를 평가).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                  # AlphaSearchBench/gplearn_asb
_ASB_ROOT = os.path.dirname(_PKG_ROOT)              # AlphaSearchBench
_REPO_ROOT = os.path.dirname(_ASB_ROOT)             # AlphaEval
for p in (_ASB_ROOT, _REPO_ROOT, _PKG_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from gplearn_asb.config import load_config, normalize_mode      # noqa: E402
from gplearn_asb import METHOD_NAME, SEMANTICS_VERSION, __version__  # noqa: E402


def ensure_backtest_importable(repo_root: str) -> None:
    """backtest/__init__.py가 import하는 누락 모듈(backtest.backtester)을
    Alphaagent/backtester.py로 사전 등록 — 원본 무수정 우회.
    provenance: AlphaEval/scripts/fast_eval.py:27-44 포팅."""
    import importlib.util
    if "backtest.backtester" in sys.modules:
        return
    src = os.path.join(repo_root, "Alphaagent", "backtester.py")
    spec = importlib.util.spec_from_file_location("backtest.backtester", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["backtest.backtester"] = mod


def cmd_mine(args) -> int:
    overrides = {}
    if args.mode:
        overrides["constraint"] = {"mode": args.mode}
    if args.seed is not None:
        overrides["seed"] = int(args.seed)
    cfg = load_config(args.config, overrides or None)
    mode = normalize_mode(cfg.get("constraint.mode", "off"))
    seed = int(cfg.require("seed"))
    worst = float(cfg.get("constraint.worst_fitness", -1.0))
    thresholds = {
        "min_mean_daily_coverage_ratio": cfg.get("validity.min_mean_daily_coverage_ratio"),
        "min_median_daily_n_valid": cfg.get("validity.min_median_daily_n_valid"),
        "min_valid_day_ratio": cfg.get("validity.min_valid_day_ratio"),
    }
    if mode == "strict_penalty" and all(v is None for v in thresholds.values()):
        raise SystemExit("strict_penalty에는 validity threshold가 최소 1개 필요합니다 "
                         "(config validity.* — hard-code 금지 원칙)")

    parsimony = float(cfg.get("gp.parsimony_coefficient", 0.0))
    from gplearn_asb.fitness import check_sentinel_separation
    warn = check_sentinel_separation(worst, parsimony)
    if warn:
        print(f"[gplearn_asb][WARN] {warn}")

    run_id = args.run_id or cfg.get("run_id") or f"{METHOD_NAME}_{mode}_{seed}"
    out_root = args.out or cfg.get("output.root") or os.path.join(_PKG_ROOT, "out", run_id)

    # ---------------- qlib / 원본 import 순서 계약 ----------------
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    import qlib
    qlib.init = lambda *a, **k: None          # placeholder 재-init 차단
    ensure_backtest_importable(_REPO_ROOT)

    from qlib.data import D
    from gplearn_asb.vendored_gplearn import genetic as VG
    from gplearn_asb.vendored_gplearn.genetic import SymbolicTransformer
    from gplearn_asb.vendored_gplearn.config import functions_arity, FEATURE_LIST
    from gplearn_asb.vendored_gplearn._program import _Program
    from gplearn_asb.vendored_gplearn.utils import check_random_state

    from alphasearchbench.outputs.writer import OutputWriter
    from alphasearchbench.inputs.trajectory import TrajectoryWriter
    from gplearn_asb.evaluator import MiningEvaluator
    from gplearn_asb.genetic import make_asb_parallel_evolve
    from gplearn_asb.trajectory import GenStatsCollector

    market = cfg.require("market")
    start, end = str(cfg.require("search.start_date")), str(cfg.require("search.end_date"))
    print(f"[gplearn_asb] mode={mode} market={market} window={start}..{end} "
          f"pop={cfg.require('gp.population_size')} gens={cfg.require('gp.generations')} "
          f"seed={seed} worst={worst}")

    t0 = time.perf_counter()
    evaluator = MiningEvaluator(cfg)
    t_panel = time.perf_counter() - t0
    print(f"[gplearn_asb] panel+universe ready in {t_panel:.1f}s "
          f"(universe_hash={evaluator.universe_hash}, close_ic={evaluator.close_signed_ic:+.5f})")

    writer_out = OutputWriter(out_root)
    traj_path = os.path.join(out_root, "trajectory", f"{run_id}.jsonl")
    gen_stats = GenStatsCollector()

    instruments = D.instruments(market=market)
    qlib_config = {"data_client": D, "instruments": instruments,
                   "start_time": start, "end_time": end, "freq": "day"}

    t1 = time.perf_counter()
    with TrajectoryWriter(traj_path, run_id=run_id, method=METHOD_NAME,
                          seed=seed) as traj:
        VG._parallel_evolve = make_asb_parallel_evolve(
            evaluator, mode, thresholds, worst, traj, gen_stats,
            constraint_mode_field=mode,
            vendored_program_cls=_Program,
            vendored_check_random_state=check_random_state)

        transformer = SymbolicTransformer(
            population_size=int(cfg.require("gp.population_size")),
            hall_of_fame=int(cfg.get("gp.hall_of_fame", 25)),
            n_components=int(cfg.get("gp.n_components", 10)),
            generations=int(cfg.require("gp.generations")),
            tournament_size=int(cfg.get("gp.tournament_size", 20)),
            stopping_criteria=float(cfg.get("gp.stopping_criteria", 1.0)),
            p_crossover=float(cfg.get("gp.p_crossover", 0.9)),
            p_subtree_mutation=float(cfg.get("gp.p_subtree_mutation", 0.01)),
            p_hoist_mutation=float(cfg.get("gp.p_hoist_mutation", 0.01)),
            p_point_mutation=float(cfg.get("gp.p_point_mutation", 0.01)),
            p_point_replace=float(cfg.get("gp.p_point_replace", 0.05)),
            max_samples=float(cfg.get("gp.max_samples", 1.0)),
            init_depth=tuple(cfg.get("gp.init_depth", [1, 4])),
            init_method=str(cfg.get("gp.init_method", "half and half")),
            function_set=functions_arity.keys(),
            metric=str(cfg.get("gp.metric", "pearson")),
            parsimony_coefficient=parsimony,
            qlib_config=qlib_config,
            feature_names=FEATURE_LIST,
            random_state=seed,
            n_jobs=1,   # 원본 러너와 동일 — memo 공유·재현성 전제
        )
        transformer.fit()
    t_fit = time.perf_counter() - t1

    # ---------------- 산출물 ----------------
    import numpy as np
    import pandas as pd
    from alphasearchbench.inputs.trajectory import load_trajectory
    from gplearn_asb.fitness import apply_constraint

    # 최종 pool (원본 러너와 동일한 _best_programs; IC=fitness_ 컬럼 유지 + 확장)
    pool_rows = []
    for p in transformer._best_programs:
        f = str(p)
        diag = evaluator.diagnose(f)   # 캐시 히트
        info = apply_constraint(mode, diag, thresholds, worst, evaluator.close_signed_ic)
        pool_rows.append({
            "formula": f,
            "IC": float(p.fitness_),                       # 원본 CSV 호환(=effective 기반)
            "signed_train_IC": info["signed_train_IC"],
            "train_sign": 1 if info["signed_train_IC"] >= 0 else -1,
            "abs_train_IC": info["abs_train_IC"],
            "raw_fitness": info["raw_fitness"],
            "effective_fitness": info["effective_fitness"],
            "hard_invalid": info["hard_invalid"],
            "research_invalid": info["research_invalid"],
            "validity_pass": info["validity_pass"],
            "invalid_reason": info["invalid_reason"],
            "mean_daily_coverage_ratio": diag.get("mean_daily_coverage_ratio"),
            "median_daily_n_valid": diag.get("median_daily_n_valid"),
            "valid_day_ratio": diag.get("valid_day_ratio"),
            "method": METHOD_NAME, "constraint_mode": mode, "seed": seed,
        })
    pool_df = pd.DataFrame(pool_rows)
    pool_csv = os.path.join(out_root, "metrics", f"final_pool_{run_id}.csv")
    pool_df.to_csv(pool_csv, index=False)
    writer_out.write_table(pool_df, f"final_pool_{run_id}")

    # 후보 단위 진단 (unique formula; first_seen은 trajectory에서 병합)
    traj_df = load_trajectory(traj_path)
    first_seen = (traj_df.sort_values(["generation", "idx_in_population"])
                  .drop_duplicates("formula")[["formula", "generation",
                                               "idx_in_population"]]
                  .rename(columns={"generation": "first_seen_generation",
                                   "idx_in_population": "first_seen_candidate_id"}))
    diag_rows = []
    for f, d in evaluator.cache.all_items():
        info = apply_constraint(mode, d, thresholds, worst, evaluator.close_signed_ic)
        row = dict(d)
        row.update({k: info[k] for k in
                    ("raw_fitness", "effective_fitness", "hard_invalid",
                     "research_invalid", "validity_pass", "invalid_reason",
                     "fallback_used")})
        row.update({"method": METHOD_NAME, "constraint_mode": mode, "seed": seed})
        diag_rows.append(row)
    diag_df = pd.DataFrame(diag_rows).merge(first_seen, on="formula", how="left")
    writer_out.write_table(diag_df, f"candidate_diagnostics_{run_id}")

    # 세대 통계 + budget + manifest
    writer_out.write_table(gen_stats.to_frame(), f"generation_stats_{run_id}")
    # budget은 mining 중의 수치만 (post-fit 재조회는 cache_stats에만 반영됨)
    budget = {
        "total_evaluations": int(len(traj_df)),
        "unique_evaluations": int(traj_df["formula"].nunique()),
        "memo_hits": int(traj_df["memo_hit"].sum()),
        "wall_clock_seconds": t_fit,
        "panel_setup_seconds": t_panel,
        "cache_stats_incl_postfit": evaluator.cache.stats(),
    }
    manifest = {
        "gplearn_asb_version": __version__,
        "semantics_version": SEMANTICS_VERSION,
        "run_id": run_id, "method": METHOD_NAME, "constraint_mode": mode,
        "seed": seed, "worst_fitness": worst, "thresholds": thresholds,
        "market": market, "search_window": [start, end],
        "label_horizon": int(cfg.get("label.horizon", 1)),
        "universe_hash": evaluator.universe_hash,
        "close_fallback_signed_ic": evaluator.close_signed_ic,
        "gp_params": {k: cfg.get(f"gp.{k}") for k in
                      ("population_size", "generations", "hall_of_fame",
                       "n_components", "tournament_size", "p_crossover",
                       "p_subtree_mutation", "p_hoist_mutation",
                       "p_point_mutation", "p_point_replace", "init_depth",
                       "init_method", "parsimony_coefficient", "metric",
                       "stopping_criteria", "max_samples")},
        "budget": budget,
        "cache_context": evaluator.cache.context,
        "outputs": {"final_pool_csv": pool_csv, "trajectory": traj_path},
        "config_echo": cfg.to_dict(),
    }
    mpath = writer_out.manifest_path(f"run_{run_id}.json")
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    print(pool_df[["formula", "IC", "signed_train_IC", "validity_pass"]]
          .to_string(index=False, max_colwidth=60))
    print(f"[gplearn_asb] fit {t_fit:.1f}s  budget={budget}")
    print(f"[gplearn_asb] outputs → {out_root}")
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="gplearn_asb")
    sub = ap.add_subparsers(dest="command")
    m = sub.add_parser("mine", help="validity-aware GP mining 실행")
    m.add_argument("--config", required=True)
    m.add_argument("--mode", default=None,
                   choices=["off", "hard_penalty", "strict_penalty"])
    m.add_argument("--seed", default=None, type=int)
    m.add_argument("--out", default=None)
    m.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)
    if args.command == "mine":
        return cmd_mine(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
