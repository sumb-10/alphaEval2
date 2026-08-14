"""Phase 7 smoke: simple backtester — 4종목×5일 손계산 대조 + full flip."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.backtest.simple import (            # noqa: E402
    daily_long_short_weights, run_simple_backtest)
from alphasearchbench.backtest.metrics import (           # noqa: E402
    performance_metrics, max_drawdown_magnitude, sharpe_ratio, D_YEAR)

DATES = pd.date_range("2020-01-01", periods=5, freq="B")
UNI4 = np.ones(4, dtype=bool)


def test_weights_hand_calc():
    w = daily_long_short_weights(np.array([4.0, 3.0, 2.0, 1.0]), UNI4, 0.25, 0.25)
    assert np.allclose(w, [0.5, 0, 0, -0.5])
    assert abs(w).sum() == pytest.approx(1.0)
    assert w.sum() == pytest.approx(0.0)
    # 2종목씩 (top/bottom 50%)
    w2 = daily_long_short_weights(np.array([4.0, 3.0, 2.0, 1.0]), UNI4, 0.5, 0.5)
    assert np.allclose(w2, [0.25, 0.25, -0.25, -0.25])
    # 구성 불가(유효 1종목) → 0
    only_one = np.array([1.0, np.nan, np.nan, np.nan])
    assert daily_long_short_weights(only_one, np.isfinite(only_one), 0.25, 0.25).sum() == 0


def test_backtest_hand_calc_and_full_flip():
    # 5일: 신호가 매일 뒤집힘 → full flip
    sig = np.array([[4, 3, 2, 1],
                    [1, 2, 3, 4],
                    [4, 3, 2, 1],
                    [1, 2, 3, 4],
                    [4, 3, 2, 1]], dtype=float)
    valid = np.ones_like(sig, dtype=bool)
    r = np.array([[0.02, 0.00, 0.00, -0.04],
                  [0.02, 0.00, 0.00, -0.04],
                  [0.02, 0.00, 0.00, -0.04],
                  [0.02, 0.00, 0.00, -0.04],
                  [0.02, 0.00, 0.00, -0.04]], dtype=float)
    m, d = run_simple_backtest(sig, valid, r, DATES,
                               top_fraction=0.25, bottom_fraction=0.25,
                               transaction_cost_rate=0.001,
                               cost_turnover_definition="oneway")
    # day0: w=[+.5,0,0,-.5] → gross = .5·.02 + (−.5)(−.04) = 0.03
    assert d.loc[0, "gross_return"] == pytest.approx(0.03)
    # day0 건립: l1=1, oneway=0.5, cost=0.0005
    assert d.loc[0, "turnover_l1"] == pytest.approx(1.0)
    assert d.loc[0, "cost"] == pytest.approx(0.0005)
    assert d.loc[0, "net_return"] == pytest.approx(0.0295)
    # day1: 신호 반전 → w=[−.5,0,0,+.5], gross = −.5·.02 + .5·(−.04) = −0.03
    assert d.loc[1, "gross_return"] == pytest.approx(-0.03)
    # **full flip: turnover_l1 = 2·Σ|w| = 2, oneway = 1** (gross-1 포트폴리오)
    assert d.loc[1, "turnover_l1"] == pytest.approx(2.0)
    assert d.loc[1, "turnover_oneway"] == pytest.approx(1.0)
    assert d.loc[1, "cost"] == pytest.approx(0.001)
    # exposure 불변량
    assert (d["gross_exposure"] == 1.0).all()
    assert np.allclose(d["net_exposure"], 0.0)

    # ---- aggregate 손계산 대조 ----
    net = d["net_return"].to_numpy()
    assert m["AnnRet_arith"] == pytest.approx(net.mean() * D_YEAR)
    cum = np.prod(1 + net) - 1
    assert m["CAGR"] == pytest.approx((1 + cum) ** (D_YEAR / 5) - 1)
    assert m["Sharpe"] == pytest.approx(net.mean() / net.std(ddof=1) * np.sqrt(D_YEAR))
    assert m["mean_daily_turnover_oneway"] == pytest.approx((0.5 + 1 + 1 + 1 + 1) / 5)
    assert m["total_transaction_cost"] == pytest.approx(0.0005 + 4 * 0.001)
    # MDD: 양수 크기 convention
    cumseq = np.cumprod(1 + net)
    peak = np.maximum.accumulate(cumseq)
    expected_mdd = -((cumseq - peak) / peak).min()
    assert m["MDD"] == pytest.approx(expected_mdd)
    assert m["MDD"] >= 0


def test_cost_definition_l1_doubles_oneway_cost():
    sig = np.tile(np.array([4.0, 3.0, 2.0, 1.0]), (3, 1))
    valid = np.ones_like(sig, dtype=bool)
    r = np.zeros_like(sig)
    _, d_ow = run_simple_backtest(sig, valid, r, DATES[:3], 0.25, 0.25,
                                  0.001, "oneway")
    _, d_l1 = run_simple_backtest(sig, valid, r, DATES[:3], 0.25, 0.25,
                                  0.001, "l1")
    assert d_l1["cost"].sum() == pytest.approx(2 * d_ow["cost"].sum())
    # 보유 유지(신호 동일) → day1부터 turnover 0
    assert d_ow.loc[1, "turnover_l1"] == 0.0


def test_missing_execution_return_contributes_zero():
    sig = np.array([[4.0, 3.0, 2.0, 1.0]])
    valid = np.ones_like(sig, dtype=bool)
    r = np.array([[np.nan, 0.0, 0.0, -0.04]])       # 롱 종목 정지
    m, d = run_simple_backtest(sig, valid, r, DATES[:1], 0.25, 0.25, 0.0, "oneway")
    assert d.loc[0, "gross_return"] == pytest.approx(0.02)   # 숏 기여만
    assert d.loc[0, "n_missing_returns"] == 1


def test_mdd_positive_magnitude():
    net = np.array([0.10, -0.20, 0.05])
    assert max_drawdown_magnitude(net) == pytest.approx(0.20)
    assert sharpe_ratio(np.array([0.01])) != sharpe_ratio(np.array([0.01, 0.02]))
