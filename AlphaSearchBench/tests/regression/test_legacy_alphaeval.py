"""Legacy AlphaEval regression — ASB 구현이 legacy 의미론을 정확히 재현하는지.

reference import(AlphaEval 내부)는 **테스트에서만** 허용된다.
새 research metric(RRE_qd, PFS_paper_literal 등)이 legacy와 다른 것은
정상이며 여기서 비교하지 않는다.

비교 대상:
  * IC       — ICBacktester.calculate1 (실제 reference 실행) vs ASB daily IC 평균
  * RankIC   — ICBacktester.calculate2 vs ASB daily RankIC 평균
  * RRE_legacy — modeltester.py 313-324행 verbatim 스니펫 vs qd.rre.rre_legacy
  * DE_legacy  — modeltester.py 213-229행 verbatim 스니펫 vs qd.diversity.de_legacy
  * PFS_legacy — 동일 ε 주입 시 적용식(S·(1+ε))과 일별 Pearson 집계의 완전 일치
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHAEVAL_ROOT = os.path.dirname(ASB_ROOT)
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config                        # noqa: E402
from alphasearchbench.oos.metrics import (                        # noqa: E402
    daily_ic_series, daily_rank_ic_series, masked_daily_corr)
from alphasearchbench.qd.rre import rre_legacy                    # noqa: E402
from alphasearchbench.qd.diversity import de_legacy               # noqa: E402
from alphasearchbench.data.signal_context import daily_zscore     # noqa: E402

FORMULAS = ["Mean($close, 30)", "Std($high, 12)",
            "Sub(Std(Div($high, $low), 12), Mean($close, 5))"]


@pytest.fixture(scope="module")
def ctx():
    from alphasearchbench.data.signal_context import SignalContext
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    return SignalContext(cfg)


@pytest.fixture(scope="module")
def reference(ctx):
    """AlphaEval reference (테스트 전용 import)."""
    sys.path.insert(0, ALPHAEVAL_ROOT)
    sys.path.insert(0, os.path.join(ALPHAEVAL_ROOT, "scripts"))
    import qlib
    orig = qlib.init
    qlib.init = lambda *a, **k: None
    try:
        from fast_eval import ensure_backtest_importable
        ensure_backtest_importable(ALPHAEVAL_ROOT)
        from backtest.ictester import ICBacktester
    finally:
        qlib.init = orig
    return ICBacktester


def test_ic_and_rankic_match_ictester(ctx, reference):
    from qlib.data import D
    start, end = ctx.splits_cfg["test"]
    inst = D.instruments(market="csi300")
    for f in FORMULAS:
        ref = reference(f, start, end, inst, "day")
        ref_ic, ref_ric = ref.calculate2()
        values, valid = ctx.evaluate(f, "test")
        fwd = ctx.split["test"].forward[1]
        our_ic = np.nanmean(daily_ic_series(values, fwd, valid))
        our_ric = np.nanmean(daily_rank_ic_series(values, fwd, valid))
        # inf 없는 formula에서 legacy와 일치해야 함
        assert our_ic == pytest.approx(ref_ic, abs=1e-9), f
        assert our_ric == pytest.approx(ref_ric, abs=1e-9), f


def test_rre_legacy_matches_verbatim_snippet():
    rng = np.random.default_rng(5)
    mat = rng.normal(size=(60, 40))
    mat[rng.random(mat.shape) < 0.1] = np.nan
    # --- modeltester.py 313-324행 verbatim (provenance 스니펫) ---
    factor_mat = pd.DataFrame(mat)
    ranks = factor_mat.rank(axis=1)
    probs = ranks.div(ranks.sum(axis=1), axis=0)
    probs_prev = probs.shift(1)
    eps = 1e-8
    kl = (probs * np.log((probs + eps) / (probs_prev + eps))).sum(axis=1)
    rre_series = kl.dropna()
    rre_series = rre_series.iloc[1:] if len(rre_series) == 60 else rre_series
    ref = float((1 / (1 + kl.iloc[1:].dropna())).mean())
    # -----------------------------------------------------------
    assert rre_legacy(mat) == pytest.approx(ref, abs=1e-12)


def test_de_legacy_matches_verbatim_snippet():
    rng = np.random.default_rng(6)
    T, N, m = 40, 30, 5
    uni = np.ones((T, N), dtype=bool)
    zs = [daily_zscore(rng.normal(size=(T, N)), uni) for _ in range(m)]
    # --- modeltester.py 213-229행 verbatim ---
    mat = np.stack([z.reshape(-1) for z in zs], axis=1)
    C = np.cov(mat, rowvar=False)
    eigs = np.linalg.eigvalsh(C)
    eigs = np.clip(eigs, a_min=0, a_max=None)
    p = eigs / eigs.sum()
    p = p[p > 0]
    ref = float(-(p * np.log(p)).sum() / np.log(m))
    # ------------------------------------------
    assert de_legacy(zs) == pytest.approx(ref, abs=1e-12)


def test_pfs_legacy_same_epsilon_exact_match():
    """동일 ε을 주입하면 legacy 적용식·집계와 완전히 일치."""
    rng = np.random.default_rng(7)
    T, N = 30, 25
    uni = np.ones((T, N), dtype=bool)
    S = rng.normal(size=(T, N)).astype(np.float32)
    eps = rng.normal(0, 0.05, size=(T, N))
    # --- 레거시 방식 (noise_proc.py: df*(1+ε); modeltester: 일별 Pearson 평균) ---
    S2 = (S * (1.0 + eps)).astype(np.float32)
    ref_daily = []
    for t in range(T):
        ref_daily.append(np.corrcoef(S[t].astype(np.float64),
                                     S2[t].astype(np.float64))[0, 1])
    ref = float(np.nanmean(ref_daily))
    # --- ASB 집계 함수 ---
    ours = float(np.nanmean(masked_daily_corr(S, S2, uni)))
    assert ours == pytest.approx(ref, abs=1e-10)
