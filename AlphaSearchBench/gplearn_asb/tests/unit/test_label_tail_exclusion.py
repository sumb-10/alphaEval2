"""unit — [v2] label tail exclusion: train 마지막 k일 label 마스크 (§6 caveat 4)."""
import os
import sys

import numpy as np

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gplearn_asb.evaluator import apply_label_tail_exclusion  # noqa: E402


def _label(T=10, N=4):
    return np.arange(T * N, dtype=np.float32).reshape(T, N) / 100.0


def test_masks_exactly_last_k_rows():
    L = _label()
    orig = L.copy()
    assert apply_label_tail_exclusion(L, 1) == 1
    assert np.isnan(L[-1]).all()
    assert np.array_equal(L[:-1], orig[:-1])        # 앞 행은 불변

    L2 = _label()
    assert apply_label_tail_exclusion(L2, 3) == 3
    assert np.isnan(L2[-3:]).all() and np.isfinite(L2[:-3]).all()


def test_noop_guards():
    L = _label()
    orig = L.copy()
    assert apply_label_tail_exclusion(L, 0) == 0    # k=0
    assert apply_label_tail_exclusion(L, -2) == 0   # 음수
    assert np.array_equal(L, orig)
    small = _label(T=2)
    assert apply_label_tail_exclusion(small, 2) == 0   # 창 ≤ k → no-op
    assert apply_label_tail_exclusion(small, 5) == 0


def test_dtype_preserved():
    L = _label()
    apply_label_tail_exclusion(L, 1)
    assert L.dtype == np.float32
