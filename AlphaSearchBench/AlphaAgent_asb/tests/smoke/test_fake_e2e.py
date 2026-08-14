"""smoke — FakeLLM E2E: 산출물 완결성 + ASB 스키마 호환 (지도 원칙 2·4 검증)."""
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
from alphasearchbench.inputs.loaders import load_result          # noqa: E402

SMOKE = os.path.join(_PKG_ROOT, "configs", "smoke.yaml")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    from alphaagent_asb.cli import main
    root = str(tmp_path_factory.mktemp("aa_smoke"))
    rc = main(["mine", "--config", SMOKE, "--fake", "--run-id", "aa_smoke",
               "--out", root])
    assert rc == 0
    return root


def test_trajectory_schema_and_axes(run):
    t = load_trajectory(os.path.join(run, "trajectory", "aa_smoke.jsonl"))
    need = {"run_id", "method", "seed", "generation", "idx_in_population",
            "formula", "raw_fitness", "seed_idx", "seed_formula", "round_id",
            "candidate_idx", "feedback_IC_raw", "feedback_IC_prompt",
            "feedback_AnnRet_raw", "feedback_AnnRet_prompt", "ast_similarity",
            "llm_verdict", "accepted", "signed_train_IC", "hard_invalid",
            "idea_text", "eval_feedback_text", "previous_formula",
            "constraint_mode", "compatibility_mode", "diagnostics_source"}
    assert need.issubset(set(t.columns))
    # AlphaAgent 문법(infix)은 qlib_fallback으로 진단되어야 함
    src = set(t["diagnostics_source"].dropna())
    assert src <= {"formula_engine", "qlib_fallback", "eval_failed"}
    # 지도 원칙 2: generation == round_id, idx_in_population == seed_idx
    assert (t["generation"] == t["round_id"]).all()
    assert (t["idx_in_population"] == t["seed_idx"]).all()
    # rejected 후보 포함 전량 보존: seed 3 × rounds ≤2
    assert len(t) >= 3


def test_natural_language_feedback_present(run):
    t = load_trajectory(os.path.join(run, "trajectory", "aa_smoke.jsonl"))
    r1 = t[t.round_id > 0]
    if len(r1):
        assert r1["previous_formula"].notna().all()
        assert (r1["idea_text"].str.len() > 0).all()


def test_llm_calls_logged_and_budget(run):
    calls = [json.loads(l) for l in
             open(os.path.join(run, "trajectory", "llm_calls.jsonl"))]
    assert all({"call_id", "role", "model", "messages", "response"} <= set(c)
               for c in calls)
    man = json.load(open(glob.glob(os.path.join(run, "manifests", "run_*.json"))[0]))
    b = man["budget"]
    for k in ("n_seed_formulas", "n_candidate_rounds", "n_idea_calls",
              "n_factor_calls", "n_eval_calls", "n_retry_calls",
              "n_total_llm_calls", "prompt_tokens", "completion_tokens"):
        assert k in b, k
    assert b["n_total_llm_calls"] == len(calls)
    assert b["n_candidate_rounds"] != b["n_total_llm_calls"]   # 후보 수 ≠ 콜 수
    assert "trajectory_semantics" in man
    assert "independent refinement trajectories" in man["trajectory_semantics"]


def test_final_pool_asb_loadable_and_accept_path(tmp_path_factory):
    """accept_rule=always로 pool 경로까지 검증 + ASB load_result 호환."""
    from alphaagent_asb.cli import main
    from alphaagent_asb.config import load_config
    import yaml
    root = str(tmp_path_factory.mktemp("aa_accept"))
    cfg_path = os.path.join(root, "cfg.yaml")
    base = yaml.safe_load(open(SMOKE))
    base.setdefault("llm", {})["fake_accept_rule"] = "always"
    yaml.safe_dump(base, open(cfg_path, "w"), allow_unicode=True)
    rc = main(["mine", "--config", cfg_path, "--fake", "--run-id", "aa_acc",
               "--out", root])
    assert rc == 0
    csvs = glob.glob(os.path.join(root, "metrics", "final_pool_*.csv"))
    df = load_result(csvs[0], method="alphaagent_asb", seed_id="42")
    # accept=always → feedback 성공 후보는 합격 → pool 비어있지 않음
    assert len(df) >= 1
    assert "signed_train_IC" in df.columns
    t = load_trajectory(os.path.join(root, "trajectory", "aa_acc.jsonl"))
    assert bool(t["accepted"].any())
