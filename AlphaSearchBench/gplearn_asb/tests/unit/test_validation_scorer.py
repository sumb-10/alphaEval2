"""unit — [C-1] GP-side validation scorer: combiner·orientation·integrity 계약.

qlib 불필요(순수 함수부). production path 대조(n=1 equivalence)는
tests/regression/test_c1_scorer_equivalence.py (qlib 필요, Slurm 검증).
"""
import math
import os
import sys

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gplearn_asb.validation_scorer import (combine_pool_signals,   # noqa: E402
                                           pool_integrity_check,
                                           train_signs)


def test_combiner_handcalc_two_factors():
    """z-score(ddof=0, std<1e-8→1)·sign·동일가중·union mask 손계산 대조."""
    a = np.array([[1.0, 2.0, 3.0],
                  [np.nan, 5.0, 7.0]], dtype=np.float64)
    b = np.array([[2.0, 2.0, 2.0],          # 상수 행 → std<1e-8 → 1 치환
                  [1.0, np.nan, 3.0]], dtype=np.float64)
    va = np.isfinite(a); vb = np.isfinite(b)
    combined, union = combine_pool_signals([a, b], [va, vb], [1, -1])

    # union mask: 두 factor 중 하나라도 유효
    assert union.all()                       # 이 예제는 전 셀 커버
    # 행0 factor a: z = (x-2)/std([1,2,3],ddof=0)=~0.8165
    za0 = (np.array([1., 2., 3.]) - 2.0) / np.std([1., 2., 3.])
    # 행0 factor b: 상수 → (x-2)/1 = 0
    exp0 = 0.5 * za0 + (-0.5) * np.zeros(3)
    assert np.allclose(combined[0], exp0)
    # 행1: a는 [nan,5,7] → z over [5,7]: mean 6, std 1 → [-1, 1] (결측 셀 0)
    #      b는 [1,nan,3] → z over [1,3]: mean 2, std 1 → [-1, 1] (결측 셀 0)
    exp1 = 0.5 * np.array([0.0, -1.0, 1.0]) + (-0.5) * np.array([-1.0, 0.0, 1.0])
    assert np.allclose(combined[1], exp1)


def test_combiner_union_mask_blocks_zero_leak():
    """모든 factor가 결측인 셀은 NaN — daily_zscore의 결측→0이 새지 않음."""
    a = np.array([[1.0, np.nan], [2.0, np.nan]])
    va = np.isfinite(a)
    combined, union = combine_pool_signals([a], [va], [1])
    assert not union[:, 1].any()
    assert np.isnan(combined[:, 1]).all()    # 0이 아니라 NaN
    assert np.isfinite(combined[:, 0]).all()


def test_combiner_n1_rank_preserving():
    """n=1: combined의 일별 rank == oriented raw 신호의 rank (equivalence 근거)."""
    rng = np.random.RandomState(0)
    sig = rng.randn(6, 20)
    sig[sig < -1.2] = np.nan
    valid = np.isfinite(sig)
    for sgn in (1, -1):
        combined, union = combine_pool_signals([sig], [valid], [sgn])
        for t in range(sig.shape[0]):
            m = valid[t]
            if m.sum() < 2:
                continue
            r_raw = np.argsort(np.argsort(sgn * sig[t, m]))
            r_cmb = np.argsort(np.argsort(combined[t, m]))
            assert (r_raw == r_cmb).all()


def test_orientation_sign_rule():
    assert train_signs([0.02, -0.001, 0.0]) == [1, -1, 1]   # runner 규약 동일


def test_integrity_gate_cases():
    ok, r = pool_integrity_check(["a", "b"], [0.1, 0.2], pool_size=2)
    assert ok and r is None
    ok, r = pool_integrity_check(["a"], [0.1], pool_size=2)
    assert not ok and "n_factors" in r
    ok, r = pool_integrity_check(["a", "a"], [0.1, 0.2], pool_size=2)
    assert not ok and "duplicate" in r
    ok, r = pool_integrity_check(["a", "b"], [0.1, float("nan")], pool_size=2)
    assert not ok and "orientation_missing" in r
    ok, r = pool_integrity_check(["a", "b"], [0.1, None], pool_size=2)
    assert not ok and "orientation_missing" in r
