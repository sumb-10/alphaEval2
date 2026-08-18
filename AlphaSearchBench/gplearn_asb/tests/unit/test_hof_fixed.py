"""unit — [A] fixed HOF 선택기: dedup·decorrelation·퇴화 쌍 처리 (qlib 불필요)."""
import os
import sys

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    sys.path.insert(0, _p)

from gplearn_asb.hof import select_pool_fixed, _daily_zscore, _pair_corr  # noqa: E402

T, N = 30, 20
MASK = np.ones((T, N), dtype=bool)
RNG = np.random.RandomState(0)


def _mk_signals():
    a = RNG.randn(T, N).astype(np.float32)
    b = (a + 0.01 * RNG.randn(T, N)).astype(np.float32)   # a와 상관 ~1
    c = RNG.randn(T, N).astype(np.float32)
    d = RNG.randn(T, N).astype(np.float32)
    return {"fA": a, "fB": b, "fC": c, "fD": d}


def _signal_fn(sigs):
    def fn(f):
        if f not in sigs:
            raise ValueError("no signal")
        return sigs[f]
    return fn


def test_dedup_and_correlated_removal():
    sigs = _mk_signals()
    cands = [
        {"formula": "fA", "effective_fitness": 0.9},
        {"formula": "fA", "effective_fitness": 0.8},   # exact dup — 제거 대상
        {"formula": "fB", "effective_fitness": 0.8},   # fA와 상관 ~1 — decorr 제거
        {"formula": "fC", "effective_fitness": 0.7},
        {"formula": "fD", "effective_fitness": 0.6},
    ]
    sel, diag = select_pool_fixed(cands, _signal_fn(sigs), MASK,
                                  hall_of_fame=4, n_components=3,
                                  min_common_cells=10)
    assert diag["n_dedup_removed"] == 1
    assert len(sel) == 3 == len(set(sel))
    assert "fA" in sel                 # 최고 eff는 상관쌍에서 생존
    assert "fB" not in sel             # 상관쌍의 낮은 eff가 제거
    assert diag["n_decorr_removed"] == 1
    assert diag["decorr_max_abs_corr_final"] < 0.9


def test_degenerate_pairs_counted_and_lowest_eff_dropped():
    # 신호 계산 전부 실패 → 모든 쌍 퇴화(0) → eff 최하위부터 제거
    cands = [{"formula": f, "effective_fitness": e}
             for f, e in [("x1", 0.5), ("x2", 0.4), ("x3", 0.3), ("x4", 0.2)]]
    sel, diag = select_pool_fixed(cands, _signal_fn({}), MASK,
                                  hall_of_fame=4, n_components=2,
                                  min_common_cells=10)
    assert sel == ["x1", "x2"]
    assert diag["n_signal_failed"] == 4
    assert diag["decorr_degenerate_pairs"] == 6        # C(4,2)
    assert diag["n_decorr_removed"] == 2


def test_min_common_cells_degenerates():
    sigs = _mk_signals()
    za = _daily_zscore(sigs["fA"], MASK)
    zb = _daily_zscore(sigs["fB"], MASK)
    corr, degen = _pair_corr(za, zb, min_common_cells=10**9)
    assert degen and corr == 0.0
    corr2, degen2 = _pair_corr(za, zb, min_common_cells=10)
    assert not degen2 and corr2 > 0.99


def test_daily_zscore_constant_day_nan():
    v = np.ones((3, 5), dtype=np.float32)              # 분산 0인 날 → NaN
    z = _daily_zscore(v, np.ones((3, 5), dtype=bool))
    assert np.isnan(z).all()


def test_pool_smaller_than_ncomp_kept():
    sigs = _mk_signals()
    cands = [{"formula": "fA", "effective_fitness": 0.9},
             {"formula": "fC", "effective_fitness": 0.7}]
    sel, diag = select_pool_fixed(cands, _signal_fn(sigs), MASK,
                                  hall_of_fame=25, n_components=10,
                                  min_common_cells=10)
    assert sel == ["fA", "fC"] and diag["n_decorr_removed"] == 0
