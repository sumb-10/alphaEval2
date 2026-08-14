"""smoke — 3개 constraint mode 미니 run (실데이터, csi300 짧은 창).

검증: population size 전 세대 불변, trajectory가 ASB load_trajectory 통과,
generation stats 산출, strict에서 invalid의 effective==worst, 세 모드의
gen-0 formula 집합 동일(같은 seed → 같은 초기 population).
"""
import glob
import json
import os
import sys

import pandas as pd
import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for p in (_PKG_ROOT, _ASB_ROOT):
    sys.path.insert(0, p)

from alphasearchbench.inputs.trajectory import load_trajectory   # noqa: E402

SMOKE = os.path.join(_PKG_ROOT, "configs", "smoke.yaml")
POP, GENS = 30, 2


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    from gplearn_asb.cli import main
    out = {}
    for mode in ("off", "hard_penalty", "strict_penalty"):
        root = str(tmp_path_factory.mktemp(f"smoke_{mode}"))
        rc = main(["mine", "--config", SMOKE, "--mode", mode,
                   "--run-id", f"smoke_{mode}", "--out", root])
        assert rc == 0
        traj = load_trajectory(os.path.join(root, "trajectory",
                                            f"smoke_{mode}.jsonl"))
        gs_files = glob.glob(os.path.join(root, "metrics", "generation_stats_*"))
        man = json.load(open(glob.glob(os.path.join(root, "manifests",
                                                    "run_*.json"))[0]))
        out[mode] = {"root": root, "traj": traj,
                     "gen_stats": pd.read_parquet(gs_files[0])
                     if gs_files[0].endswith("parquet") else pd.read_csv(gs_files[0]),
                     "manifest": man}
    return out


def test_population_size_constant_all_modes(runs):
    for mode, r in runs.items():
        per_gen = r["traj"].groupby("generation").size()
        assert list(per_gen.index) == list(range(GENS))
        assert (per_gen == POP).all(), f"{mode}: population size 변동 {dict(per_gen)}"


def test_trajectory_schema_and_fields(runs):
    need = {"run_id", "method", "seed", "generation", "idx_in_population",
            "formula", "raw_fitness", "effective_fitness", "signed_train_IC",
            "abs_train_IC", "constraint_mode", "hard_invalid", "research_invalid",
            "validity_pass", "invalid_reason", "mean_daily_coverage_ratio",
            "median_daily_n_valid", "valid_day_ratio", "program_length",
            "program_depth", "memo_hit", "operation"}
    for mode, r in runs.items():
        assert need.issubset(set(r["traj"].columns)), mode
        assert (r["traj"]["constraint_mode"] == mode).all()


def test_gen0_identical_across_modes(runs):
    """penalty는 selection에만 작용 — 같은 seed의 gen 0은 세 모드 동일."""
    f0 = {m: list(r["traj"][r["traj"].generation == 0]["formula"])
          for m, r in runs.items()}
    assert f0["off"] == f0["hard_penalty"] == f0["strict_penalty"]


def test_invalid_kept_with_worst_fitness(runs):
    for mode in ("hard_penalty", "strict_penalty"):
        t = runs[mode]["traj"]
        worst = runs[mode]["manifest"]["worst_fitness"]
        gated = t[(t.hard_invalid == True) |                     # noqa: E712
                  ((t.research_invalid == True) if mode == "strict_penalty"  # noqa: E712
                   else (t.hard_invalid == True))]               # noqa: E712
        if len(gated):
            assert (gated.effective_fitness == worst).all()
        # off에서는 게이트 없음
    t_off = runs["off"]["traj"]
    ok = t_off[t_off.raw_fitness.notna()]
    assert (ok.effective_fitness == ok.raw_fitness).all()


def test_generation_stats_complete(runs):
    need = {"generation", "population_size", "n_unique", "n_unique_valid",
            "hard_invalid_rate", "research_invalid_rate", "valid_candidate_rate",
            "mean_signal_coverage", "median_n_valid", "mean_raw_train_IC",
            "best_raw_train_IC", "best_valid_train_IC", "mean_effective_fitness",
            "best_effective_fitness", "n_unique_parents_selected",
            "parent_selection_entropy", "top_parent_selection_share"}
    for mode, r in runs.items():
        gs = r["gen_stats"]
        assert need.issubset(set(gs.columns)), mode
        assert len(gs) == GENS
        assert (gs.population_size == POP).all()
        # gen>0에는 부모 선택 기록이 있어야 함
        assert (gs[gs.generation > 0].n_unique_parents_selected > 0).all()


def test_final_pool_asb_loadable(runs):
    """최종 CSV가 ASB 표준 input 스키마로 로드되고 signed IC를 보존."""
    from alphasearchbench.inputs.loaders import load_result
    for mode, r in runs.items():
        csvs = glob.glob(os.path.join(r["root"], "metrics", "final_pool_*.csv"))
        df = load_result(csvs[0], method="gplearn_asb", seed_id="42")
        assert "signed_train_IC" in df.columns and "train_sign" in df.columns
        assert df["formula"].notna().all()
