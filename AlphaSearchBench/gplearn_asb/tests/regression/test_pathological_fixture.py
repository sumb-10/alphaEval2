"""regression — 실제 pathological winner fixture (#23).

pilot에서 확인된 아티팩트 formula(gp_csi800 승자, csi800 universe)와 정상
formula(Log($volume))를 실데이터로 진단한다.
기대: 아티팩트는 raw IC가 기록되되 research_invalid → effective=worst;
정상은 validity pass → effective = |IC|.

실행 비용: market=all 패널 1회 적재(~1분) — Slurm 제출 가능(사용자 허용).
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

from gplearn_asb.config import load_config           # noqa: E402
from gplearn_asb.fitness import apply_constraint      # noqa: E402

# pilot 산출물(out/gplearn_tensor_csi800_seed42_883929.csv)의 실제 winner
PATHOLOGICAL = [
    "Rsquare(Std(Var($factor, 6), 30), 5)",
    "Div(Less(Power($high, $change), Less(Rsquare(Std(Var($factor, 6), 30), 5),"
    " Power($high, $change))), Rsquare(Std(Var($factor, 6), 30), 5))",
]
NORMAL = "Log($volume)"

TH = {"min_mean_daily_coverage_ratio": 0.05,
      "min_median_daily_n_valid": 30,
      "min_valid_day_ratio": 0.90}
WORST = -1.0


@pytest.fixture(scope="module")
def evaluator():
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    cfg = load_config(overrides={
        "market": "csi800",
        "search": {"start_date": "2010-01-01", "end_date": "2019-12-31"},
        "gp": {"population_size": 1, "generations": 1},
    })
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    from gplearn_asb.evaluator import MiningEvaluator
    return MiningEvaluator(cfg)


def test_pathological_high_raw_ic_but_worst_effective(evaluator):
    for i, f in enumerate(PATHOLOGICAL):
        diag = evaluator.diagnose(f)
        info = apply_constraint("strict_penalty", diag, TH, WORST,
                                evaluator.close_signed_ic)
        if i == 0:
            # Rsquare winner: raw IC 보존 (883929 마이닝 fitness 0.074825 재현)
            assert info["raw_fitness"] > 0.03, f
        else:
            # Div 변종: 중간노드 overflow의 inf/NaN 계보 차이로 raw가 0.0이
            # 될 수 있음 (IMPLEMENTATION_PLAN '구현 중 발견' #1·2 — 이 영역은
            # 원본 실행 간에도 값이 불안정했던 병리 케이스). 기록 자체는 유한.
            assert np.isfinite(info["raw_fitness"]), f
        # coverage는 극단적으로 낮다 (검증 V5: csi800 아티팩트 ≈0.011)
        assert diag["mean_daily_coverage_ratio"] < 0.05, f
        assert info["research_invalid"] and not info["validity_pass"]
        assert info["effective_fitness"] == WORST
        # hard_penalty에서는 (hard invalid가 아니므로) 통과 — 계층 확인
        info_h = apply_constraint("hard_penalty", diag, TH, WORST,
                                  evaluator.close_signed_ic)
        assert info_h["effective_fitness"] == info["raw_fitness"]


def test_normal_formula_passes(evaluator):
    diag = evaluator.diagnose(NORMAL)
    info = apply_constraint("strict_penalty", diag, TH, WORST,
                            evaluator.close_signed_ic)
    assert diag["mean_daily_coverage_ratio"] > 0.5
    assert info["validity_pass"]
    assert info["effective_fitness"] == info["raw_fitness"] == pytest.approx(
        abs(diag["signed_train_IC"]))
    assert info["effective_fitness"] > 0.0


def test_eval_failure_is_hard_invalid_in_penalty_modes(evaluator):
    # 주의: Mean($close, 0)은 qlib 의미론상 유효(N=0 → expanding)이므로
    # 진짜 실패 케이스인 미지 연산자를 쓴다.
    diag = evaluator.diagnose("Quantile($close, 5)")  # 미지 연산자 → eval 실패
    assert diag["eval_failed"] and diag["hard_invalid"]
    for mode in ("hard_penalty", "strict_penalty"):
        info = apply_constraint(mode, diag, TH, WORST, evaluator.close_signed_ic)
        assert info["effective_fitness"] == WORST
    # off에서는 원본 루프홀 재현: $close IC 상속
    info_off = apply_constraint("off", diag, TH, WORST, evaluator.close_signed_ic)
    assert info_off["fallback_used"]
    assert info_off["effective_fitness"] == abs(evaluator.close_signed_ic)
