"""AlphaAgent_asb CLI.

사용 (AlphaSearchBench/AlphaAgent_asb/ 에서):
  python -m alphaagent_asb.cli mine --config configs/smoke.yaml --fake
  python -m alphaagent_asb.cli mine --config ... --replay <llm_calls.jsonl>
  python -m alphaagent_asb.cli mine --config ...           # live (OPENAI_API_KEY 필요)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                  # AlphaSearchBench/AlphaAgent_asb
_ASB_ROOT = os.path.dirname(_PKG_ROOT)              # AlphaSearchBench
_REPO_ROOT = os.path.dirname(_ASB_ROOT)             # AlphaEval
for p in (_ASB_ROOT, os.path.join(_ASB_ROOT, "gplearn_asb"), _PKG_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from alphaagent_asb.config import load_config, normalize_choice   # noqa: E402
from alphaagent_asb import METHOD_NAME, COMPAT_MODES, CONSTRAINT_MODES, \
    TRAJECTORY_SEMANTICS, __version__                              # noqa: E402


def cmd_mine(args) -> int:
    overrides = {}
    if args.seed is not None:
        overrides["seed"] = int(args.seed)
    cfg = load_config(args.config, overrides or None)
    compat = normalize_choice(cfg.get("compatibility.mode", "parity"),
                              COMPAT_MODES, "compatibility.mode")
    constraint_mode = normalize_choice(cfg.get("constraint.mode", "off"),
                                       CONSTRAINT_MODES, "constraint.mode")
    seed = int(cfg.get("seed", 42))
    llm_mode = "fake" if args.fake else ("replay" if args.replay else "live")
    run_id = (args.run_id or cfg.get("run_id")
              or f"{METHOD_NAME}_{compat}_{llm_mode}_{seed}")
    out_root = args.out or cfg.get("output.root") or os.path.join(_PKG_ROOT, "out", run_id)

    thresholds = {k: cfg.get(f"validity.{k}") for k in
                  ("min_mean_daily_coverage_ratio", "min_median_daily_n_valid",
                   "min_valid_day_ratio")}
    if constraint_mode == "strict_penalty" and all(v is None for v in thresholds.values()):
        raise SystemExit("strict_penalty overlay에는 validity threshold가 필요합니다")

    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    from qlib.data import D
    from alphasearchbench.outputs.writer import OutputWriter
    from alphasearchbench.inputs.trajectory import TrajectoryWriter, load_trajectory
    from gplearn_asb.evaluator import MiningEvaluator
    from alphaagent_asb.llm import make_llm
    from alphaagent_asb.loop import run_mining

    market = cfg.require("market")
    start, end = str(cfg.require("search.start_date")), str(cfg.require("search.end_date"))
    print(f"[alphaagent_asb] compat={compat} constraint={constraint_mode} "
          f"llm={llm_mode} market={market} window={start}..{end} "
          f"rounds={cfg.get('agent.max_rounds')} seed_range={cfg.get('agent.seed_range')}")

    t0 = time.perf_counter()
    from alphaagent_asb.diagnostics import DiagnosticsWithQlibFallback
    mining_eval = DiagnosticsWithQlibFallback(MiningEvaluator(cfg))
    print(f"[alphaagent_asb] diagnostics panel ready in {time.perf_counter()-t0:.1f}s "
          f"(universe_hash={mining_eval.universe_hash})")

    writer_out = OutputWriter(out_root)
    llm = make_llm(cfg, llm_mode,
                   log_path=os.path.join(out_root, "trajectory", "llm_calls.jsonl"),
                   replay_path=args.replay)
    instruments = D.instruments(market=market)

    t1 = time.perf_counter()
    traj_path = os.path.join(out_root, "trajectory", f"{run_id}.jsonl")
    with TrajectoryWriter(traj_path, run_id=run_id, method=METHOD_NAME,
                          seed=seed) as traj:
        summary = run_mining(cfg, llm, mining_eval, traj, constraint_mode,
                             thresholds, float(cfg.get("constraint.worst_fitness", -1.0)),
                             instruments)
    llm.close()
    t_mine = time.perf_counter() - t1

    # ---------------- 산출물 ----------------
    import numpy as np
    import pandas as pd

    pool_rows = []
    for f, meta in zip(summary["pool"], summary["pool_meta"]):
        sic = meta.get("signed_train_IC")
        pool_rows.append({
            "formula": f,
            "IC": abs(sic) if sic is not None and np.isfinite(sic) else np.nan,
            "signed_train_IC": sic,
            "train_sign": (1 if (sic or 0) >= 0 else -1),
            **{k: meta.get(k) for k in
               ("feedback_IC_raw", "feedback_IC_prompt", "feedback_AnnRet_prompt",
                "ast_similarity", "validity_pass", "invalid_reason",
                "mean_daily_coverage_ratio", "seed_idx", "round_id")},
            "method": METHOD_NAME, "compatibility_mode": compat,
            "constraint_mode": constraint_mode, "seed": seed,
        })
    _POOL_COLS = ["formula", "IC", "signed_train_IC", "train_sign",
                  "feedback_IC_raw", "feedback_IC_prompt", "feedback_AnnRet_prompt",
                  "ast_similarity", "validity_pass", "invalid_reason",
                  "mean_daily_coverage_ratio", "seed_idx", "round_id",
                  "method", "compatibility_mode", "constraint_mode", "seed"]
    pool_df = pd.DataFrame(pool_rows, columns=_POOL_COLS)
    pool_csv = os.path.join(out_root, "metrics", f"final_pool_{run_id}.csv")
    pool_df.to_csv(pool_csv, index=False)
    if len(pool_df):
        writer_out.write_table(pool_df, f"final_pool_{run_id}")

    rows_df = pd.DataFrame(summary["rows"])
    if len(rows_df):
        writer_out.write_table(rows_df, f"candidate_diagnostics_{run_id}")
        rs = rows_df.groupby("round_id").agg(
            n_candidates=("formula", "size"),
            n_accepted=("accepted", "sum"),
            n_llm_hq=("llm_verdict", lambda s: int(sum(bool(x) for x in s))),
            n_feedback_error=("feedback_error", lambda s: int(s.notna().sum())),
            mean_abs_feedback_IC=("raw_fitness", "mean"),
            mean_similarity=("ast_similarity", "mean"),
            mean_coverage=("mean_daily_coverage_ratio", "mean"),
            n_hard_invalid=("hard_invalid", lambda s: int(sum(bool(x) for x in s))),
        ).reset_index()
        writer_out.write_table(rs, f"round_stats_{run_id}")

    budget = llm.budget.to_dict()
    budget.update({"n_seed_formulas": summary["n_seeds"],
                   "n_candidate_rounds": summary["n_candidates"],
                   "n_seed_aborted": summary["n_seed_aborted"],
                   "mining_wall_seconds": t_mine})
    manifest = {
        "alphaagent_asb_version": __version__,
        "run_id": run_id, "method": METHOD_NAME,
        "compatibility_mode": compat, "constraint_mode": constraint_mode,
        "llm_mode": llm_mode,
        "llm": {"models": {r: cfg.get(f"llm.models.{r}") for r in ("idea", "factor", "eval")},
                "temperatures": {r: cfg.get(f"llm.temperatures.{r}") for r in ("idea", "factor", "eval")},
                "request_seed": cfg.get("llm.request_seed"),
                # D-10: 모델이 config 온도를 거부해 기본값으로 강등된 경우 기록
                "temperature_fallback_models":
                    sorted(getattr(llm, "temperature_fallback_models", []))},
        "seed": seed, "market": market, "search_window": [start, end],
        "universe_hash": mining_eval.universe_hash,
        "thresholds": thresholds,
        "trajectory_semantics": TRAJECTORY_SEMANTICS,
        "budget": budget,
        "pool_size": len(pool_df),
        "outputs": {"final_pool_csv": pool_csv, "trajectory": traj_path},
        "config_echo": cfg.to_dict(),
    }
    with open(writer_out.manifest_path(f"run_{run_id}.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    print(pool_df[["formula", "signed_train_IC", "feedback_IC_prompt"]]
          .to_string(index=False, max_colwidth=60) if len(pool_df) else "(pool 비어 있음)")
    print(f"[alphaagent_asb] mining {t_mine:.1f}s  budget={budget}")
    print(f"[alphaagent_asb] outputs → {out_root}")
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="alphaagent_asb")
    sub = ap.add_subparsers(dest="command")
    m = sub.add_parser("mine", help="LLM 알파 마이닝 실행")
    m.add_argument("--config", required=True)
    m.add_argument("--fake", action="store_true", help="FakeLLM (결정적, 개발/테스트)")
    m.add_argument("--replay", default=None, help="llm_calls.jsonl 재생 (결정적)")
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
