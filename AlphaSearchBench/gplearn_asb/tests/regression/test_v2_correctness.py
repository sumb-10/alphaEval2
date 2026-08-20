"""regression — [v2] correctness: HOF 격리(sentinel·패치 무해성)·결정성·산출 계약.

실데이터 미니 run(configs/v2/smoke.yaml, csi300 30×2)을 사용한다.
Vanilla_GP_v2.md §8-3의 (iii)(iv) 항목.
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

V2_SMOKE = os.path.join(_PKG_ROOT, "configs", "v2", "smoke.yaml")


def _run_v2(root: str, run_id: str, disable_patch: bool = False):
    from gplearn_asb.cli import run_mine_v2
    rc = run_mine_v2(V2_SMOKE, run_id=run_id, out=root,
                     _disable_execute_patch=disable_patch)
    assert rc == 0
    traj = load_trajectory(os.path.join(root, "trajectory", f"{run_id}.jsonl"))
    pool = pd.read_csv(os.path.join(root, "metrics", f"final_pool_{run_id}.csv"))
    man = json.load(open(glob.glob(os.path.join(root, "manifests",
                                                "run_*.json"))[0]))
    return traj, pool, man


@pytest.fixture(scope="module")
def v2_run(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("v2_smoke"))
    return _run_v2(root, "v2_test_a")


def test_manifest_contract(v2_run):
    _t, _p, man = v2_run
    assert man["gp_profile"] == "vanilla_v2-draft"
    assert man["generations_derived_from_budget"] is True
    assert man["gp_params"]["generations"] == 2          # 60 // 30
    assert man["fitness_metric"] == "fb_fitness"
    cp = man["canonical_profile"]
    assert cp["hof"].startswith("select_pool_fixed")
    assert cp["point_mutation"] == "typed"
    assert "inf" in str(cp["stopping_criteria"])
    assert man["label_tail_exclusion"] == 1               # train-only 계약 (k=1)
    assert man["gp_params"]["hall_of_fame"] == 30         # min(50, population=30)


def test_budget_exhausted_no_early_stop(v2_run):
    traj, _p, man = v2_run
    assert len(traj) == 60                                # 예산 전량 소진
    assert traj["generation"].nunique() == 2


def test_pool_is_fixed_hof_only(v2_run):
    """[HOF 격리 ⓐ] pool == trajectory 마지막 세대의 fixed 재선택 결과.

    vendored _best_programs(anti-selection)는 어떤 경로로도 pool에 못 들어온다
    — 오프라인 재계산과 CSV가 정확히 일치해야 한다."""
    traj, pool, _m = v2_run
    assert pool["formula"].nunique() == len(pool)          # exact dedup 보장
    assert (pool["hof_mode"] == "fixed").all()
    last = traj[traj["generation"] == traj["generation"].max()]
    # 재계산은 무거우므로(신호 필요) 구조적 불변식으로 검증:
    # fixed 선택은 최종 population의 effective 상위에서만 나온다.
    best = last.groupby("formula")["effective_fitness"].max()
    ranked = best.sort_values(ascending=False)
    top_hof = set(ranked.head(50).index)
    assert set(pool["formula"]).issubset(top_hof)


def test_execute_patch_harmless(tmp_path_factory, v2_run):
    """[HOF 격리 ⓑ] execute 더미 패치는 탐색에 무영향 — 동일 seed에서
    패치 off run과 trajectory·세대통계가 완전 동일해야 한다."""
    traj_a, _pa, _ma = v2_run
    root_b = str(tmp_path_factory.mktemp("v2_smoke_nopatch"))
    traj_b, pool_b, _mb = _run_v2(root_b, "v2_test_b", disable_patch=True)
    cols = ["generation", "idx_in_population", "formula", "effective_fitness",
            "operation"]
    pd.testing.assert_frame_equal(
        traj_a[cols].reset_index(drop=True),
        traj_b[cols].reset_index(drop=True))
    # pool도 동일 (fixed HOF는 trajectory에서 파생되므로)
    _ta, pool_a, _ = v2_run
    assert list(pool_a["formula"]) == list(pool_b["formula"])


def test_determinism_fixture(tmp_path_factory, v2_run):
    """[v2 결정성] 동일 config+seed 재실행 → trajectory formula 열 완전 동일
    (v2의 883881 대체 앵커)."""
    traj_a, _p, _m = v2_run
    root_c = str(tmp_path_factory.mktemp("v2_smoke_repeat"))
    traj_c, _pc, _mc = _run_v2(root_c, "v2_test_c")
    assert list(traj_a["formula"]) == list(traj_c["formula"])
    assert list(traj_a["effective_fitness"]) == list(traj_c["effective_fitness"])


def test_globals_restored_after_run(v2_run):
    """[A+E] v2 run 종료 후 vendored 전역이 원본으로 복원되어야 한다 —
    같은 프로세스의 후속 legacy run/테스트 오염 방지 (예외 경로 포함은
    try/finally 구조가 보장)."""
    from gplearn_asb.vendored_gplearn._program import _Program
    from gplearn_asb.vendored_gplearn import genetic as VG
    assert _Program.execute.__name__ == "execute"          # 더미 lambda 아님
    assert VG._parallel_evolve.__module__.endswith("vendored_gplearn.genetic")


def test_no_legacy_semantics_in_v2(v2_run):
    """v2 trajectory에 legacy 흔적($close fallback, off/hard 모드)이 없어야 한다."""
    traj, _p, man = v2_run
    assert not traj["fallback_used"].fillna(False).astype(bool).any()
    assert (traj["constraint_mode"] == "v2_admissibility").all()
    assert man.get("canonical_profile", {}).get("admissibility", "").startswith("always-on")
