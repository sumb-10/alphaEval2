"""unit — [WS-A] 프로토콜 arm 옵션: topk 선택 / rebalance_days / 초과수익 지표."""
import math
import os
import sys

import numpy as np
import pandas as pd

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ASB_ROOT not in sys.path:
    sys.path.insert(0, _ASB_ROOT)

from alphasearchbench.backtest.metrics import (benchmark_relative_metrics,   # noqa: E402
                                               performance_metrics)
from alphasearchbench.backtest.simple import (daily_long_short_weights,      # noqa: E402
                                              run_simple_backtest)


# ------------------------------------------------------------ topk 선택
def test_topk_selects_k_each_side_and_equal_weights():
    sig = np.array([5.0, 4.0, 3.0, 2.0, 1.0, 0.0])
    valid = np.ones(6, dtype=bool)
    w = daily_long_short_weights(sig, valid, 0.2, 0.2, selection="topk", topk=2)
    assert np.isclose(w[[0, 1]], 0.25).all()      # long 2종목 × 0.5/2
    assert np.isclose(w[[4, 5]], -0.25).all()     # short 2종목
    assert np.isclose(w[[2, 3]], 0.0).all()
    assert np.isclose(w.sum(), 0.0) and np.isclose(np.abs(w).sum(), 1.0)


def test_topk_shrinks_when_universe_too_small():
    sig = np.array([3.0, 2.0, 1.0])
    valid = np.ones(3, dtype=bool)
    w = daily_long_short_weights(sig, valid, 0.2, 0.2, selection="topk", topk=50)
    assert int((w > 0).sum()) == 1 and int((w < 0).sum()) == 1   # k=floor(3/2)=1
    w0 = daily_long_short_weights(np.array([1.0]), np.array([True]), 0.2, 0.2,
                                  selection="topk", topk=50)
    assert np.isclose(w0, 0.0).all()              # 구성 불가 → 무포지션


def test_topk_ignores_invalid_and_is_tie_deterministic():
    sig = np.array([9.0, 1.0, 1.0, 1.0, 0.0])
    valid = np.array([False, True, True, True, True])
    w1 = daily_long_short_weights(sig, valid, 0.2, 0.2, selection="topk", topk=1)
    w2 = daily_long_short_weights(sig, valid, 0.2, 0.2, selection="topk", topk=1)
    assert np.isclose(w1[0], 0.0)                 # invalid는 절대 편입 안 됨
    assert np.allclose(w1, w2)                    # 동수 처리 결정적(안정 정렬)


def test_selection_validation():
    try:
        daily_long_short_weights(np.array([1.0, 2.0]), np.ones(2, dtype=bool),
                                 0.2, 0.2, selection="bogus")
    except ValueError:
        return
    raise AssertionError("selection 검증이 동작하지 않음")


# ------------------------------------------------------------ rebalance_days
def _bt(**kw):
    T, N = 6, 6
    rng = np.random.RandomState(0)
    sig = rng.randn(T, N)
    valid = np.ones((T, N), dtype=bool)
    ret = np.full((T, N), 0.001)
    dates = pd.date_range("2021-01-04", periods=T, freq="B")
    return run_simple_backtest(sig, valid, ret, dates, **kw)


def test_rebalance_days_zero_turnover_on_hold_days():
    m5, d5 = _bt(rebalance_days=3, selection="topk", topk=2)
    # 리밸런스일(0,3)만 회전 발생, 나머지는 0
    assert d5.loc[[1, 2, 4, 5], "turnover_l1"].abs().max() == 0.0
    assert d5.loc[0, "turnover_l1"] > 0 and d5.loc[3, "turnover_l1"] > 0
    m1, d1 = _bt(rebalance_days=1, selection="topk", topk=2)
    assert m5["mean_daily_turnover_l1"] < m1["mean_daily_turnover_l1"]
    assert m5["total_transaction_cost"] < m1["total_transaction_cost"]


def test_rebalance_days_holds_same_weights():
    _m, d = _bt(rebalance_days=2, selection="topk", topk=2)
    assert d.loc[0, "long_count"] == d.loc[1, "long_count"]
    assert d.loc[0, "gross_exposure"] == d.loc[1, "gross_exposure"]


def test_rebalance_days_validation():
    try:
        _bt(rebalance_days=0)
    except ValueError:
        return
    raise AssertionError("rebalance_days 검증이 동작하지 않음")


# ------------------------------------------------------------ 초과수익 지표
def test_benchmark_relative_metrics_handcalc():
    daily = pd.DataFrame({
        "net_return":   [0.010, -0.005, 0.020],
        "bench_return": [0.004, -0.002, 0.006],
        "gross_return": [0.011, -0.004, 0.021],
        "cost":         [0.001, 0.001, 0.001],
        "turnover_l1":  [1.0, 0.2, 0.2],
        "turnover_oneway": [0.5, 0.1, 0.1],
    })
    ex = np.array([0.006, -0.003, 0.014])
    r = benchmark_relative_metrics(daily)
    assert abs(r["AnnRet_excess"] - ex.mean() * 252) < 1e-12
    assert abs(r["IR"] - ex.mean() / ex.std(ddof=1) * math.sqrt(252)) < 1e-12
    assert r["n_days_excess"] == 3 and r["MDD_excess"] >= 0
    # performance_metrics는 bench_return이 있을 때만 초과 필드를 붙인다
    full = performance_metrics(daily)
    assert "IR" in full and "AnnRet_excess" in full
    assert "IR" not in performance_metrics(daily.drop(columns=["bench_return"]))


def test_benchmark_relative_metrics_insufficient_data():
    daily = pd.DataFrame({"net_return": [0.01], "bench_return": [0.005],
                          "gross_return": [0.01], "cost": [0.0],
                          "turnover_l1": [1.0], "turnover_oneway": [0.5]})
    r = benchmark_relative_metrics(daily)
    assert math.isnan(r["IR"]) and r["n_days_excess"] == 1


# ------------------------------------------------------------ 기본값 불변(A1 회귀)
def test_defaults_unchanged_vs_quantile_daily():
    """새 옵션 기본값(quantile, rebalance_days=1)은 v0.1 계약과 동일해야 한다."""
    T, N = 8, 10
    rng = np.random.RandomState(1)
    sig = rng.randn(T, N)
    valid = np.ones((T, N), dtype=bool)
    ret = rng.randn(T, N) * 0.01
    dates = pd.date_range("2021-01-04", periods=T, freq="B")
    m_new, _ = run_simple_backtest(sig, valid, ret, dates)
    m_expl, _ = run_simple_backtest(sig, valid, ret, dates,
                                    selection="quantile", rebalance_days=1)
    for k in ("Sharpe", "AnnRet_arith", "MDD", "mean_daily_turnover_l1"):
        a, b = m_new[k], m_expl[k]
        assert (math.isnan(a) and math.isnan(b)) or abs(a - b) < 1e-15


# ------------------------------------------------------------ mode dispatch
def test_backtest_mode_dispatch_selects_evaluator():
    """`backtest.mode`가 실제 실행 경로를 바꿔야 한다 (이전엔 manifest에만 기록되고
    항상 simple이 돌던 조용한 no-op 버그)."""
    import types

    from alphasearchbench.config import Config
    from alphasearchbench.backtest.simple import SimpleBacktestEvaluator
    from alphasearchbench.backtest.qlib_native import QlibBacktestEvaluator
    from alphasearchbench.runner import EvaluationRun

    stub = types.SimpleNamespace(cfg=None, ctx=object())

    def make(mode):
        stub.cfg = Config({"backtest": {"mode": mode, "qlib": {"topk": 50, "n_drop": 5}}})
        return EvaluationRun._make_backtest_evaluator(stub)

    assert isinstance(make("simple"), SimpleBacktestEvaluator)
    q = make("qlib")
    assert isinstance(q, QlibBacktestEvaluator)
    assert q.kw["topk"] == 50 and q.kw["n_drop"] == 5
    assert hasattr(q, "evaluate_pool")          # pool 경로 존재 (WS-A 추가)
    try:
        make("bogus")
    except ValueError:
        return
    raise AssertionError("backtest.mode 검증이 동작하지 않음")
