"""regression — gen-0 동일성(#22) + population 안정성/invalid 보존(#25).

qlib 데이터는 쓰지 않는다 (placeholder init 무력화 후 프로그램 생성 로직만).
원본 gplearn 패키지는 **참조 비교 목적으로만** import (수정 없음).
"""
import os
import sys

import numpy as np
import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
_REPO_ROOT = os.path.dirname(_ASB_ROOT)
for p in (_PKG_ROOT, _ASB_ROOT, _REPO_ROOT):
    sys.path.insert(0, p)

# 원본 러너의 init 계약 재현: 실제 qlib bootstrap(가벼움 — 데이터 미적재) 후
# placeholder 재-init 무력화, backtest 모듈 사전 등록. 이 테스트는 D 데이터를
# 조회하지 않지만 vendored/원본 모듈이 import 시점에 D를 요구한다.
from gplearn_asb.config import load_config     # noqa: E402
from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib  # noqa: E402
_cfg = load_config()
bootstrap_qlib(_cfg["dataset.provider_uri"], _cfg["dataset.region"], 1)
import qlib                                    # noqa: E402
qlib.init = lambda *a, **k: None
from gplearn_asb.cli import ensure_backtest_importable  # noqa: E402
ensure_backtest_importable(_REPO_ROOT)

from gplearn_asb.vendored_gplearn._program import _Program as VProgram      # noqa: E402
from gplearn_asb.vendored_gplearn.fitness import _fitness_map as v_fmap     # noqa: E402
from gplearn_asb.vendored_gplearn.config import functions_arity, FEATURE_LIST  # noqa: E402
from gplearn_asb.vendored_gplearn.utils import check_random_state           # noqa: E402
from gplearn._program import _Program as OProgram   # noqa: E402 — 참조 비교 전용(원본 무수정)

MAX_INT = np.iinfo(np.int32).max


def _mk_arities():
    ar = {}
    for fn, a in functions_arity.items():
        ar.setdefault(a, []).append(fn)
    return ar


def _program_kwargs(metric):
    return dict(function_set=list(functions_arity.keys()), arities=_mk_arities(),
                init_depth=(1, 4), init_method="half and half",
                n_features=len(FEATURE_LIST), metric=metric, transformer=None,
                const_range=None, p_point_replace=0.05,
                parsimony_coefficient=0.0, feature_names=FEATURE_LIST,
                qlib_config={"unused": True})


def test_gen0_same_seed_identical_formulas():
    """같은 seed → 원본과 vendored의 초기 population 문자열 완전 동일 (#22)."""
    from gplearn.fitness import _fitness_map as o_fmap
    seeds = check_random_state(42).randint(MAX_INT, size=200)
    v_kwargs = _program_kwargs(v_fmap["pearson"])
    o_kwargs = _program_kwargs(o_fmap["pearson"])
    for s in seeds:
        vp = VProgram(random_state=check_random_state(s), program=None, **v_kwargs)
        op = OProgram(random_state=check_random_state(s), program=None, **o_kwargs)
        assert str(vp) == str(op)


class FakeEvaluator:
    """90% hard-invalid 합성 평가기 (#25) — 인터페이스: diagnose/cache/close_signed_ic."""
    def __init__(self, invalid_ratio=0.9):
        from gplearn_asb.cache import DiagnosticsCache
        self.cache = DiagnosticsCache({"synthetic": True})
        self.close_signed_ic = 0.03
        self.invalid_ratio = invalid_ratio

    def diagnose(self, formula):
        hit = self.cache.get(formula)
        if hit is not None:
            return hit
        import hashlib
        h = int(hashlib.md5(formula.encode()).hexdigest(), 16) % 100  # 결정적
        invalid = h < int(self.invalid_ratio * 100)
        d = {"formula": formula,
             "signed_train_IC": float("nan") if invalid else 0.001 + h / 1000.0,
             "abs_train_IC": float("nan") if invalid else 0.001 + h / 1000.0,
             "n_ic_obs": 0 if invalid else 100,
             "eval_failed": False, "hard_invalid": invalid,
             "invalid_reason": "no_correlatable_day" if invalid else None,
             "mean_daily_coverage_ratio": 0.0 if invalid else 0.9,
             "median_daily_n_valid": 0 if invalid else 3000,
             "valid_day_ratio": 0.0 if invalid else 1.0}
        self.cache.put(formula, d)
        return d


def test_population_size_preserved_with_90pct_invalid(tmp_path):
    """pop=100, invalid≈90% → 다음 세대도 정확히 100 + invalid가 population에 잔존."""
    from alphasearchbench.inputs.trajectory import TrajectoryWriter, load_trajectory
    from gplearn_asb.genetic import make_asb_parallel_evolve
    from gplearn_asb.trajectory import GenStatsCollector
    from gplearn_asb.vendored_gplearn.fitness import _fitness_map

    metric = _fitness_map["pearson"]
    ev = FakeEvaluator(0.9)
    gs = GenStatsCollector()
    traj_path = str(tmp_path / "traj.jsonl")
    params = {"tournament_size": 20, "function_set": list(functions_arity.keys()),
              "arities": _mk_arities(), "init_depth": (1, 4),
              "init_method": "half and half", "const_range": None,
              "_metric": metric, "_transformer": None,
              "parsimony_coefficient": 0.0,
              "method_probs": np.cumsum([0.9, 0.01, 0.01, 0.01]),
              "p_point_replace": 0.05, "max_samples": 1.0,
              "feature_names": FEATURE_LIST, "qlib_config": {"unused": True}}
    X_shape = (1000, len(FEATURE_LIST))

    with TrajectoryWriter(traj_path, run_id="syn", method="gplearn_asb",
                          seed=7) as tw:
        evolve = make_asb_parallel_evolve(
            ev, "hard_penalty", {}, -1.0, tw, gs, "hard_penalty",
            VProgram, check_random_state)
        rs = check_random_state(7)
        seeds0 = rs.randint(MAX_INT, size=100)
        gen0 = evolve(100, None, X_shape, None, None, seeds0, params)
        assert len(gen0) == 100
        # fitness_는 원본 genetic.fit(495-496)이 하듯 raw_fitness_에서 파생
        for p in gen0:
            p.fitness_ = p.fitness(parsimony_coefficient=0.0)
        n_invalid0 = sum(1 for p in gen0 if p.raw_fitness_ == -1.0)
        assert n_invalid0 >= 60                       # 대부분 invalid인 상황
        seeds1 = rs.randint(MAX_INT, size=100)
        gen1 = evolve(100, gen0, X_shape, None, None, seeds1, params)
        assert len(gen1) == 100                       # population size 불변 (#25)

    traj = load_trajectory(traj_path)
    assert len(traj) == 200
    g1 = traj[traj.generation == 1]
    # invalid candidate가 population 데이터에 그대로 남아 있고 worst fitness를 가짐
    inv = g1[g1.hard_invalid == True]                 # noqa: E712
    assert len(inv) > 0
    assert (inv.effective_fitness == -1.0).all()
    # 부모 선택은 effective 기준 → valid(=raw_fitness_>0) 부모가 지배적이어야 함
    valid_idx = {i for i, p in enumerate(gen0) if p.raw_fitness_ > -1.0}
    picks = [int(x) for x in g1.parent_idx.dropna()] + \
            [int(x) for x in g1.donor_idx.dropna()]
    frac_valid_parent = sum(1 for i in picks if i in valid_idx) / len(picks)
    # 이론: invalid 비율 p≈0.9, tournament 20 → all-invalid 확률 p^20≈12%
    # → valid 부모 기대 비율 ≈88%. population 내 valid 비중(≈10%) 대비
    # 압도적 과대표집이면 selection이 effective fitness를 쓰는 것.
    frac_valid_population = len(valid_idx) / len(gen0)
    assert frac_valid_parent >= 0.75
    assert frac_valid_parent > 5 * frac_valid_population
