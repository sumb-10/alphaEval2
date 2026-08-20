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
    # [v2 dispatch] 실험 파일에 profile: vanilla_v2 가 있으면 v2 경로로.
    import yaml as _yaml
    with open(args.config) as _fh:
        _raw = _yaml.safe_load(_fh) or {}
    _prof = _raw.get("profile")
    if _prof == "vanilla_v2":
        raise SystemExit("[vanilla_v2] spec은 아직 freeze 전입니다 — "
                         "profile: vanilla_v2-draft 를 사용하세요 "
                         "(승격은 C-3 freeze에서: Vanilla_GP_v2.md §0)")
    if _prof == "vanilla_v2-draft":
        if args.mode:
            raise SystemExit("[vanilla_v2] --mode는 legacy 전용입니다 (v2는 "
                             "admissibility 상시 — constraint 개념 없음)")
        return run_mine_v2(args.config, raw=_raw, seed=args.seed,
                           run_id=args.run_id, out=args.out)
    if _prof in ("v2_bloat_lexi", "v2_bloat_cap", "v2_bloat_lexi_cap"):
        # [C-2a.3] bloat-control 실험 profile — canonical v2와 동일 기계장치,
        # 차이는 ε-lexicographic parent selection(lexi 계열)과 config의
        # loose safety cap(L/D)뿐. canonical/legacy 동작 불변.
        if args.mode:
            raise SystemExit("[bloat-exp] --mode는 legacy 전용입니다")
        return run_mine_v2(args.config, raw=_raw, seed=args.seed,
                           run_id=args.run_id, out=args.out,
                           experimental_profile=_prof)
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
    fitness_metric = str(cfg.get("gp.fitness_metric", "abs_ic"))
    from gplearn_asb.fitness import FITNESS_METRICS
    if fitness_metric not in FITNESS_METRICS:
        raise SystemExit(f"gp.fitness_metric은 {FITNESS_METRICS} 중 하나여야 "
                         f"합니다 (현재 {fitness_metric!r})")
    if fitness_metric in ("net_sharpe", "fb_fitness"):
        # Sharpe 스케일 가드: valid도 크게 음수 가능 + 원본 stopping 1.0은 오발
        if worst > -100:
            raise SystemExit(f"{fitness_metric} 모드에는 constraint.worst_fitness를 "
                             f"충분히 낮게 설정하세요 (현재 {worst}, 권장 -1e6)")
        if float(cfg.get("gp.stopping_criteria", 1.0)) < 100:
            raise SystemExit(f"{fitness_metric} 모드에는 gp.stopping_criteria를 크게 "
                             "설정하세요 (예: 1e9 — 원본 1.0은 Sharpe≥1에서 조기 종료)")
    if fitness_metric == "ic_tstat":
        # t=1은 사소하게 도달 — 원본 stopping 1.0이면 gen-0 조기 종료 오발.
        # sentinel은 t≥0이므로 −1.0으로 충분 (가드 불필요).
        if float(cfg.get("gp.stopping_criteria", 1.0)) < 100:
            raise SystemExit("ic_tstat 모드에는 gp.stopping_criteria를 크게 "
                             "설정하세요 (예: 1e9 — t-stat은 1.0을 사소하게 넘음)")
    # [B2/P2-3] fitness 부가 조건 (기본 전부 null=off — 기존 run 의미 불변)
    fitness_opts = {
        "net_sharpe_min_traded_days": cfg.get("gp.net_sharpe_min_traded_days"),
        "net_sharpe_min_abs_ic": cfg.get("gp.net_sharpe_min_abs_ic"),
        "max_program_length": cfg.get("gp.max_program_length"),
    }
    hof_mode = str(cfg.get("gp.hof_mode", "original"))
    if hof_mode not in ("original", "fixed"):
        raise SystemExit(f"gp.hof_mode는 original|fixed 중 하나 (현재 {hof_mode!r})")

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
            vendored_check_random_state=check_random_state,
            fitness_opts=fitness_opts)

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

    traj_df = load_trajectory(traj_path)

    # 최종 pool
    if hof_mode == "fixed":
        # [A] fixed HOF: 최종 population(=trajectory 마지막 세대)에서 dedup +
        # NaN-safe decorrelation으로 재선택 — _best_programs(원본 버그) 무시.
        from gplearn_asb.hof import select_pool_fixed, build_pool_rows
        last_gen = traj_df[traj_df["generation"] == traj_df["generation"].max()]
        selected, hof_diag = select_pool_fixed(
            last_gen[["formula", "effective_fitness"]].to_dict("records"),
            signal_fn=lambda f: evaluator.engine.compute(
                f, evaluator.search_start, evaluator.search_end),
            universe_mask=evaluator.universe_mask,
            hall_of_fame=int(cfg.get("gp.hall_of_fame", 25)),
            n_components=int(cfg.get("gp.n_components", 10)))
        print(f"[gplearn_asb] hof_mode=fixed: {hof_diag}")
        pool_rows = build_pool_rows(selected, evaluator, mode, thresholds, worst,
                                    seed, METHOD_NAME, fitness_opts=fitness_opts,
                                    hof_diag=hof_diag)
    else:
        # 원본 러너와 동일한 _best_programs (IC=fitness_ 컬럼 유지 + 확장)
        pool_rows = []
        for p in transformer._best_programs:
            f = str(p)
            diag = evaluator.diagnose(f)   # 캐시 히트
            info = apply_constraint(mode, diag, thresholds, worst, evaluator.close_signed_ic,
                                    fitness_metric=evaluator.fitness_metric,
                                    close_net_sharpe=getattr(evaluator, "close_net_sharpe", float("nan")),
                                    fitness_opts=fitness_opts,
                                    close_raw_fitness=getattr(evaluator, "close_raw_fitness", None))
            pool_rows.append({
                "formula": f,
                "IC": float(p.fitness_),                   # 원본 CSV 호환(=effective 기반)
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
    first_seen = (traj_df.sort_values(["generation", "idx_in_population"])
                  .drop_duplicates("formula")[["formula", "generation",
                                               "idx_in_population"]]
                  .rename(columns={"generation": "first_seen_generation",
                                   "idx_in_population": "first_seen_candidate_id"}))
    diag_rows = []
    for f, d in evaluator.cache.all_items():
        info = apply_constraint(mode, d, thresholds, worst, evaluator.close_signed_ic,
                                fitness_metric=evaluator.fitness_metric,
                                close_net_sharpe=getattr(evaluator, "close_net_sharpe", float("nan")),
                                fitness_opts=fitness_opts,
                                close_raw_fitness=getattr(evaluator, "close_raw_fitness", None))
        row = dict(d)
        row.update({k: info[k] for k in
                    ("raw_fitness", "effective_fitness", "hard_invalid",
                     "research_invalid", "validity_pass", "invalid_reason",
                     "fallback_used", "fitness_condition_failed")})
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
        "fitness_metric": fitness_metric,
        "fitness_opts": fitness_opts,
        "hof_mode": hof_mode,
        "static_gate": evaluator.static_gate,
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




# ============================================================ Clean Vanilla GP v2
V2_CANONICAL = {
    # Vanilla_GP_v2.md §3 — 내부 canonical profile (public config에서 변경 불가)
    "init_method": "half and half",
    "init_depth": (1, 4),
    "tournament_size": 20,
    "p_crossover": 0.90,
    "p_subtree_mutation": 0.01,
    "p_hoist_mutation": 0.01,
    "p_point_mutation": 0.01,
    "p_point_replace": 0.05,
    "parsimony_coefficient": 0.0,
    "max_samples": 1.0,
    "metric": "pearson",
    "hall_of_fame": 50,
}
V2_WORST_BY_METRIC = {"abs_ic": -1.0, "ic_tstat": -1.0,
                      "net_sharpe": -1e6, "fb_fitness": -1e6}
# [canonical v2 contract] fb pathological 가드: turnover→0⁺ 폭발 차단 하한.
# legacy 경로는 이 값을 주입하지 않으므로(기본 0.0) v1 재현 불변.
V2_FB_MIN_ANNUAL_TURNOVER = 0.01
V2_PROFILE_STAMP = "vanilla_v2-draft"   # freeze(C-3) 시 "vanilla_v2"로 승격
# [C-2a.3] ε-lexicographic tolerance — C-2a control의 tournament gap p10.
# 사전등록: out/c2a3/prereg_FINAL_4c_plus_s2partial.json (mc_seed 20260819,
# 4 완주 run + s2 partial gens 0-14; s2 완주 취소는 사용자 개정 2026-08-20).
# 4-run 민감도값 2.878e-4 (prereg_SMOKE_4runs.json). 판독 전 변경 금지.
BLOAT_LEXI_EPSILON = 0.0004764455216271779


def run_mine_v2(config_path: str, raw: Optional[dict] = None,
                seed: Optional[int] = None, run_id: Optional[str] = None,
                out: Optional[str] = None,
                _disable_execute_patch: bool = False,
                experimental_profile: Optional[str] = None) -> int:
    """Clean Vanilla GP v2 마이닝 (Vanilla_GP_v2.md 명세).

    v1과의 차이: 스키마 화이트리스트, budget→generations 파생, admissibility
    상시(모드 없음), typed point mutation, fixed HOF 유일 경로, vendored HOF
    블록의 qlib 재조회 차단(execute 더미 패치), early stopping 없음.
    _disable_execute_patch는 패치 무해성 regression 테스트 전용.
    """
    import math
    import yaml
    from gplearn_asb.config import (Config, ConfigError, DEFAULT_CONFIG_PATH,
                                    derive_v2_generations, validate_v2_schema)

    if raw is None:
        with open(config_path) as fh:
            raw = yaml.safe_load(fh) or {}
    validate_v2_schema(raw, source=config_path)

    # dataset 블록만 default.yaml에서 상속 (legacy gp/constraint 블록은 미상속)
    with open(DEFAULT_CONFIG_PATH) as fh:
        base = yaml.safe_load(fh) or {}
    data = {"dataset": base.get("dataset", {})}
    data = Config._deep_merge(data, raw)

    v2_seed = int(seed if seed is not None else data.get("seed", 42))
    population = int((data.get("gp") or {}).get("population_size") or 0)
    candidates = int((data.get("budget") or {}).get("candidates") or 0)
    generations = derive_v2_generations(candidates, population)
    pool_size = int((data.get("pool") or {}).get("size") or 10)
    fit_blk = data.get("fitness") or {}
    fitness_metric = str(fit_blk.get("metric", "fb_fitness"))
    worst = V2_WORST_BY_METRIC[fitness_metric]
    max_len = (data.get("gp") or {}).get("max_program_length")
    max_depth = (data.get("gp") or {}).get("max_program_depth")

    thresholds = {
        "min_mean_daily_coverage_ratio": (data.get("validity") or {}).get("min_mean_daily_coverage_ratio"),
        "min_median_daily_n_valid": (data.get("validity") or {}).get("min_median_daily_n_valid"),
        "min_valid_day_ratio": (data.get("validity") or {}).get("min_valid_day_ratio"),
    }
    if all(v is None for v in thresholds.values()):
        raise ConfigError("[vanilla_v2] validity threshold는 고정 benchmark spec입니다 "
                          "— 최소 1개 필수 (Vanilla_GP_v2.md §2.5)")

    # 내부 cfg 구성: MiningEvaluator·genetic이 읽는 키로 매핑 (admissibility 상시)
    internal = dict(data)
    internal["gp"] = dict(data.get("gp") or {})
    internal["gp"].update({
        "fitness_metric": fitness_metric,
        "static_gate": True,
        "generations": generations,
        "n_components": pool_size,
        **{k: v for k, v in V2_CANONICAL.items() if k != "init_depth"},
        "init_depth": list(V2_CANONICAL["init_depth"]),
    })
    internal["constraint"] = {"mode": "strict_penalty", "worst_fitness": worst}
    internal["label"] = dict(data.get("label") or {})
    internal["label"]["tail_exclusion"] = True   # [v2] train-only 계약 (§6 caveat 4)
    internal["backtest"] = {
        "transaction_cost_rate": float(fit_blk.get("transaction_cost_rate", 0.0015)),
        "long_short_quantile": float(fit_blk.get("long_short_quantile", 0.2)),
    }
    internal["seed"] = v2_seed
    cfg = Config(internal)

    market = cfg.require("market")
    start = str(cfg.require("search.start_date"))
    end = str(cfg.require("search.end_date"))
    rid = run_id or data.get("run_id") or f"v2_{market}_{fitness_metric}_{v2_seed}"
    out_root = out or (data.get("output") or {}).get("root") \
        or os.path.join(_PKG_ROOT, "out", rid)

    hof_width = min(V2_CANONICAL["hall_of_fame"], population)

    # [C-2a.3] 실험 profile: lexi 계열이면 사전 등록된 ε 필수
    lexi_epsilon = None
    if experimental_profile and "lexi" in experimental_profile:
        if BLOAT_LEXI_EPSILON is None:
            raise SystemExit("[bloat-exp] BLOAT_LEXI_EPSILON 미등록 — "
                             "C-2a 5-run control로 사전 등록 후 실행하세요")
        lexi_epsilon = float(BLOAT_LEXI_EPSILON)
    profile_stamp = experimental_profile or V2_PROFILE_STAMP

    fitness_opts = {
        "net_sharpe_min_traded_days": fit_blk.get("net_sharpe_min_traded_days"),
        "net_sharpe_min_abs_ic": fit_blk.get("net_sharpe_min_abs_ic"),
        "max_program_length": max_len,
        "max_program_depth": max_depth,
        "fb_min_annual_turnover": (V2_FB_MIN_ANNUAL_TURNOVER
                                   if fitness_metric == "fb_fitness" else None),
    }

    # ---------------- qlib / import 순서 계약 (v1과 동일) ----------------
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    import qlib
    qlib.init = lambda *a, **k: None
    ensure_backtest_importable(_REPO_ROOT)

    import numpy as np
    from qlib.data import D
    from gplearn_asb.vendored_gplearn import genetic as VG
    from gplearn_asb.vendored_gplearn.genetic import SymbolicTransformer
    from gplearn_asb.vendored_gplearn.config import functions_arity, FEATURE_LIST
    from gplearn_asb.vendored_gplearn._program import _Program
    from gplearn_asb.vendored_gplearn.utils import check_random_state

    from alphasearchbench.outputs.writer import OutputWriter
    from alphasearchbench.inputs.trajectory import TrajectoryWriter, load_trajectory
    from gplearn_asb.evaluator import MiningEvaluator
    from gplearn_asb.genetic import make_asb_parallel_evolve
    from gplearn_asb.mutation import typed_point_mutation
    from gplearn_asb.trajectory import GenStatsCollector
    from gplearn_asb.hof import select_pool_fixed, build_pool_rows

    print(f"[vanilla_v2] market={market} window={start}..{end} "
          f"budget={candidates} pop={population} gens={generations} "
          f"fitness={fitness_metric} seed={v2_seed}")

    t0 = time.perf_counter()
    evaluator = MiningEvaluator(cfg)
    t_panel = time.perf_counter() - t0
    print(f"[vanilla_v2] panel ready {t_panel:.1f}s "
          f"(universe_hash={evaluator.universe_hash})")

    writer_out = OutputWriter(out_root)
    traj_path = os.path.join(out_root, "trajectory", f"{rid}.jsonl")
    gen_stats = GenStatsCollector()
    instruments = D.instruments(market=market)
    qlib_config = {"data_client": D, "instruments": instruments,
                   "start_time": start, "end_time": end, "freq": "day"}

    t1 = time.perf_counter()
    # vendored fit() 내부 HOF 블록의 qlib 재조회·$close fallback 무력화.
    # 진화(phase-A/B)는 execute를 쓰지 않으므로 탐색에 영향 없음 — 무해성은
    # regression(패치 on/off 대조)으로 보장. 패치는 fit 직전 최소 구간에만
    # 적용하고, try/finally가 이 블록의 **어떤 예외에서도** 전역
    # (_Program.execute, VG._parallel_evolve) 복원을 보장한다 — 같은
    # 프로세스의 후속 run(legacy 경로·테스트)을 오염시키지 않는다.
    _orig_execute = _Program.execute
    _orig_evolve = VG._parallel_evolve
    try:
        with TrajectoryWriter(traj_path, run_id=rid, method=f"{METHOD_NAME}_v2",
                              seed=v2_seed) as traj:
            VG._parallel_evolve = make_asb_parallel_evolve(
                evaluator, "strict_penalty", thresholds, worst, traj, gen_stats,
                constraint_mode_field="v2_admissibility",
                vendored_program_cls=_Program,
                vendored_check_random_state=check_random_state,
                fitness_opts=fitness_opts,
                point_mutation_fn=typed_point_mutation,
                lexi_epsilon=lexi_epsilon)
            transformer = SymbolicTransformer(
                population_size=population,
                hall_of_fame=hof_width,
                n_components=pool_size,
                generations=generations,
                tournament_size=V2_CANONICAL["tournament_size"],
                stopping_criteria=math.inf,            # early stopping 금지
                p_crossover=V2_CANONICAL["p_crossover"],
                p_subtree_mutation=V2_CANONICAL["p_subtree_mutation"],
                p_hoist_mutation=V2_CANONICAL["p_hoist_mutation"],
                p_point_mutation=V2_CANONICAL["p_point_mutation"],
                p_point_replace=V2_CANONICAL["p_point_replace"],
                max_samples=V2_CANONICAL["max_samples"],
                init_depth=V2_CANONICAL["init_depth"],
                init_method=V2_CANONICAL["init_method"],
                function_set=functions_arity.keys(),
                metric=V2_CANONICAL["metric"],
                parsimony_coefficient=V2_CANONICAL["parsimony_coefficient"],
                qlib_config=qlib_config,
                feature_names=FEATURE_LIST,
                random_state=v2_seed,
                n_jobs=1)
            if not _disable_execute_patch:
                _Program.execute = lambda self, X_shape: np.zeros(
                    X_shape[0], dtype=float)
            transformer.fit()
    finally:
        _Program.execute = _orig_execute
        VG._parallel_evolve = _orig_evolve
    t_fit = time.perf_counter() - t1

    # ---------------- pool: fixed HOF가 유일한 source ----------------
    import pandas as pd
    traj_df = load_trajectory(traj_path)
    last_gen = traj_df[traj_df["generation"] == traj_df["generation"].max()]
    selected, hof_diag = select_pool_fixed(
        last_gen[["formula", "effective_fitness"]].to_dict("records"),
        signal_fn=lambda f: evaluator.engine.compute(
            f, evaluator.search_start, evaluator.search_end),
        universe_mask=evaluator.universe_mask,
        hall_of_fame=hof_width,
        n_components=pool_size)
    print(f"[vanilla_v2] fixed HOF: {hof_diag}")
    pool_rows = build_pool_rows(selected, evaluator, "strict_penalty",
                                thresholds, worst, v2_seed, f"{METHOD_NAME}_v2",
                                fitness_opts=fitness_opts, hof_diag=hof_diag)
    pool_df = pd.DataFrame(pool_rows)
    pool_csv = os.path.join(out_root, "metrics", f"final_pool_{rid}.csv")
    pool_df.to_csv(pool_csv, index=False)
    writer_out.write_table(pool_df, f"final_pool_{rid}")

    # 후보 진단·세대 통계 (v1 스키마 동일)
    from gplearn_asb.fitness import apply_constraint
    first_seen = (traj_df.sort_values(["generation", "idx_in_population"])
                  .drop_duplicates("formula")[["formula", "generation",
                                               "idx_in_population"]]
                  .rename(columns={"generation": "first_seen_generation",
                                   "idx_in_population": "first_seen_candidate_id"}))
    diag_rows = []
    for f, d in evaluator.cache.all_items():
        info = apply_constraint("strict_penalty", d, thresholds, worst,
                                evaluator.close_signed_ic,
                                fitness_metric=fitness_metric,
                                close_net_sharpe=getattr(evaluator, "close_net_sharpe", float("nan")),
                                fitness_opts=fitness_opts,
                                close_raw_fitness=getattr(evaluator, "close_raw_fitness", None))
        row = dict(d)
        row.update({k: info[k] for k in
                    ("raw_fitness", "effective_fitness", "hard_invalid",
                     "research_invalid", "validity_pass", "invalid_reason",
                     "fallback_used", "fitness_condition_failed")})
        row.update({"method": f"{METHOD_NAME}_v2", "seed": v2_seed})
        diag_rows.append(row)
    diag_df = pd.DataFrame(diag_rows).merge(first_seen, on="formula", how="left")
    writer_out.write_table(diag_df, f"candidate_diagnostics_{rid}")
    writer_out.write_table(gen_stats.to_frame(), f"generation_stats_{rid}")

    budget = {
        "candidates_budget": candidates,
        "total_evaluations": int(len(traj_df)),
        "unique_evaluations": int(traj_df["formula"].nunique()),
        "memo_hits": int(traj_df["memo_hit"].sum()),
        "wall_clock_seconds": t_fit,
        "panel_setup_seconds": t_panel,
    }
    manifest = {
        "gplearn_asb_version": __version__,
        "semantics_version": SEMANTICS_VERSION,
        "gp_profile": profile_stamp,
        "bloat_experiment": ({"treatment": experimental_profile,
                              "lexi_epsilon": lexi_epsilon}
                             if experimental_profile else None),
        "run_id": rid, "method": f"{METHOD_NAME}_v2",
        "fitness_metric": fitness_metric,
        "fitness_opts": fitness_opts,
        "canonical_profile": {**V2_CANONICAL,
                              "fb_min_annual_turnover": V2_FB_MIN_ANNUAL_TURNOVER,
                              "stopping_criteria": "inf (early stop 금지)",
                              "worst_fitness": worst,
                              "admissibility": "always-on (hard+threshold→worst)",
                              "hof": "select_pool_fixed (유일 경로)",
                              "point_mutation": "typed"},
        "generations_derived_from_budget": True,
        "seed": v2_seed, "thresholds": thresholds,
        "market": market, "search_window": [start, end],
        "label_horizon": int(cfg.get("label.horizon", 1)),
        "label_tail_exclusion": evaluator.label_tail_excluded,
        "universe_hash": evaluator.universe_hash,
        "gp_params": {"population_size": population, "generations": generations,
                      "hall_of_fame": hof_width,
                      "n_components": pool_size,
                      "max_program_length": max_len,
                      "max_program_depth": max_depth},
        "budget": budget,
        "cache_context": evaluator.cache.context,
        "outputs": {"final_pool_csv": pool_csv, "trajectory": traj_path},
        "config_echo": data,
    }
    mpath = writer_out.manifest_path(f"run_{rid}.json")
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    print(pool_df[["formula", "raw_fitness", "validity_pass"]]
          .to_string(index=False, max_colwidth=60))
    print(f"[vanilla_v2] fit {t_fit:.1f}s budget={budget}")
    print(f"[vanilla_v2] outputs → {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
