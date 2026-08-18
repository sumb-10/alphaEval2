"""[A-소급] 완주 run에 fixed-HOF를 오프라인 적용 — 재마이닝 없이 pool 재생성.

근거: trajectory의 마지막 세대 행 = 최종 population (formula +
effective_fitness 완비) → HOF는 fit 이후 선택 단계이므로 소급 가능.

산출 (원본 pool CSV 보존):
  <run>/metrics/final_pool_<rid>_fixedhof.csv
  <run>/manifest/repool_<rid>.json  (hof 진단 + 재구성 파라미터)
  out/<rid>_fixedhof/  파생 run 디렉토리 (trajectory 심링크 + pool +
    manifest 사본, run_id=<rid>_fixedhof) — ASB evaluate 하네스 호환용.

사용:
  python scripts/repool_fixed_hof.py --runs out/pilot_csi800_strict_0 [...]
  python scripts/repool_fixed_hof.py --glob "out/pilot_csi800_strict_*"
"""
import argparse
import json
import os
import shutil
import sys
import time
from glob import glob

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
_REPO_ROOT = os.path.dirname(_ASB_ROOT)
for p in (_ASB_ROOT, _REPO_ROOT, _PKG_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

_EVALUATOR_CACHE = {}


_QLIB_READY = False


def _get_evaluator(cfg):
    """무거운 패널 로드를 (market, window, horizon, metric) 단위로 재사용."""
    global _QLIB_READY
    if not _QLIB_READY:
        from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
        bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                       cfg["dataset.qlib_kernels"])
        _QLIB_READY = True
    from gplearn_asb.evaluator import MiningEvaluator
    key = (cfg.require("market"), str(cfg.require("search.start_date")),
           str(cfg.require("search.end_date")), int(cfg.get("label.horizon", 1)),
           str(cfg.get("gp.fitness_metric", "abs_ic")))
    if key not in _EVALUATOR_CACHE:
        t0 = time.perf_counter()
        _EVALUATOR_CACHE[key] = MiningEvaluator(cfg)
        print(f"  evaluator ready ({time.perf_counter()-t0:.1f}s) key={key}")
    return _EVALUATOR_CACHE[key]


def repool_run(run_dir: str) -> dict:
    import pandas as pd
    from alphasearchbench.config import Config
    from alphasearchbench.inputs.trajectory import load_trajectory
    from gplearn_asb.config import normalize_mode
    from gplearn_asb.hof import select_pool_fixed, build_pool_rows

    run_dir = run_dir.rstrip("/")
    manifests = glob(os.path.join(run_dir, "manifests", "run_*.json"))
    assert len(manifests) == 1, f"manifest 1개 기대: {run_dir} → {manifests}"
    with open(manifests[0]) as fh:
        man = json.load(fh)
    rid = man["run_id"]
    mode = normalize_mode(man["constraint_mode"])
    seed = int(man["seed"])
    worst = float(man["worst_fitness"])
    thresholds = {k: (None if v is None else float(v))
                  for k, v in man["thresholds"].items()}
    fitness_opts = man.get("fitness_opts") or {}
    cfg = Config(man["config_echo"])
    print(f"[repool] {rid} mode={mode} seed={seed} metric={man.get('fitness_metric')}")

    traj_path = os.path.join(run_dir, "trajectory", f"{rid}.jsonl")
    traj = load_trajectory(traj_path)
    last_gen = int(traj["generation"].max())
    pop = traj[traj["generation"] == last_gen]
    print(f"  final population: gen={last_gen} n={len(pop)} "
          f"unique={pop['formula'].nunique()}")

    ev = _get_evaluator(cfg)
    selected, hof_diag = select_pool_fixed(
        pop[["formula", "effective_fitness"]].to_dict("records"),
        signal_fn=lambda f: ev.engine.compute(f, ev.search_start, ev.search_end),
        universe_mask=ev.universe_mask,
        hall_of_fame=int(cfg.get("gp.hall_of_fame", 25)),
        n_components=int(cfg.get("gp.n_components", 10)))
    print(f"  hof: {hof_diag}")

    rows = build_pool_rows(selected, ev, mode, thresholds, worst, seed,
                           man["method"], fitness_opts=fitness_opts,
                           hof_diag=hof_diag)
    pool_df = pd.DataFrame(rows)
    fixed_rid = f"{rid}_fixedhof"
    pool_csv = os.path.join(run_dir, "metrics", f"final_pool_{fixed_rid}.csv")
    pool_df.to_csv(pool_csv, index=False)

    repool_man = {"source_run_id": rid, "run_id": fixed_rid,
                  "hof_mode": "fixed", "hof_diag": hof_diag,
                  "final_generation": last_gen,
                  "population_rows": int(len(pop)),
                  "selected": selected, "pool_csv": pool_csv}
    with open(os.path.join(run_dir, "manifests", f"repool_{rid}.json"), "w") as fh:
        json.dump(repool_man, fh, indent=2, default=str)

    # 파생 run 디렉토리 (ASB evaluate 하네스가 기대하는 배치)
    droot = os.path.join(os.path.dirname(run_dir), fixed_rid)
    for sub in ("metrics", "trajectory", "manifests"):
        os.makedirs(os.path.join(droot, sub), exist_ok=True)
    shutil.copyfile(pool_csv,
                    os.path.join(droot, "metrics", f"final_pool_{fixed_rid}.csv"))
    tlink = os.path.join(droot, "trajectory", f"{fixed_rid}.jsonl")
    if not os.path.exists(tlink):
        os.symlink(os.path.abspath(traj_path), tlink)
    dman = dict(man)
    dman.update({"run_id": fixed_rid, "hof_mode": "fixed",
                 "repool_source": rid, "hof_diag": hof_diag})
    with open(os.path.join(droot, "manifests", f"run_{fixed_rid}.json"), "w") as fh:
        json.dump(dman, fh, indent=2, default=str)
    # candidate_diagnostics도 파생 rid로 노출 (evaluate가 참조할 수 있음)
    src_diag = os.path.join(run_dir, "metrics",
                            f"candidate_diagnostics_{rid}.parquet")
    dst_diag = os.path.join(droot, "metrics",
                            f"candidate_diagnostics_{fixed_rid}.parquet")
    if os.path.exists(src_diag) and not os.path.exists(dst_diag):
        os.symlink(os.path.abspath(src_diag), dst_diag)
    print(f"  → {pool_csv}\n  → {droot}/")
    return {"run": rid, "pool_unique": int(pool_df['formula'].nunique()),
            "pool_valid": int(pool_df["validity_pass"].sum()), **hof_diag}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--glob", dest="pattern", default=None)
    args = ap.parse_args()
    runs = list(args.runs)
    if args.pattern:
        runs += sorted(glob(args.pattern))
    runs = [r for r in runs if os.path.isdir(r) and not r.endswith("_fixedhof")]
    assert runs, "대상 run 없음"

    import pandas as pd
    summaries = [repool_run(r) for r in runs]
    df = pd.DataFrame(summaries)
    pd.set_option("display.width", 220)
    print("\n=== repool summary ===")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
