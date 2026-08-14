"""Backtest performance metrics.

정의 (manifest에 기록되는 확정 convention):
  * AnnRet_arith = mean(daily_net_return) × 252   — AlphaEval 논문(Eq.21) 비교용
  * CAGR         = (1 + cumulative_net_return)^(252/n) − 1
                   (provenance: Alphaagent/backtester.py 172행)
  * Sharpe       = mean(net)/std(net, ddof=1) × √252, risk-free 0 (인터페이스 개방)
  * MDD          = **positive magnitude** (내부 계산은 음수 낙폭의 최솟값)
  * turnover_l1  = Σ|w_t − w_{t−1}|,  turnover_oneway = 0.5 × l1
    (AlphaEval 논문 Eq.23은 l1 정의 — 0.5 계수 없음)
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

D_YEAR = 252


def sharpe_ratio(net: np.ndarray, rf_daily: float = 0.0) -> float:
    x = net[np.isfinite(net)] - rf_daily
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / sd * np.sqrt(D_YEAR)) if sd > 0 else float("nan")


def max_drawdown_magnitude(net: np.ndarray) -> float:
    x = np.where(np.isfinite(net), net, 0.0)
    cum = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(-dd.min())


def performance_metrics(daily: pd.DataFrame, rf_daily: float = 0.0) -> Dict[str, float]:
    """daily: gross_return / cost / net_return / turnover_l1 / turnover_oneway"""
    net = daily["net_return"].to_numpy(dtype=float)
    gross = daily["gross_return"].to_numpy(dtype=float)
    n = int(np.isfinite(net).sum())
    cum_net = float(np.prod(1.0 + net[np.isfinite(net)]) - 1.0) if n else float("nan")
    cum_gross = float(np.prod(1.0 + gross[np.isfinite(gross)]) - 1.0) if n else float("nan")
    t_l1 = daily["turnover_l1"].to_numpy(dtype=float)
    t_ow = daily["turnover_oneway"].to_numpy(dtype=float)
    out = {
        "AnnRet_arith": float(np.nanmean(net) * D_YEAR) if n else float("nan"),
        "CAGR": float((1.0 + cum_net) ** (D_YEAR / n) - 1.0) if n and cum_net > -1 else float("nan"),
        "Sharpe": sharpe_ratio(net, rf_daily),
        "MDD": max_drawdown_magnitude(net),
        "mean_daily_turnover_l1": float(np.nanmean(t_l1)),
        "mean_daily_turnover_oneway": float(np.nanmean(t_ow)),
        "annualized_turnover_l1": float(np.nanmean(t_l1) * D_YEAR),
        "annualized_turnover_oneway": float(np.nanmean(t_ow) * D_YEAR),
        "total_transaction_cost": float(np.nansum(daily["cost"].to_numpy(dtype=float))),
        "gross_cumulative_return": cum_gross,
        "net_cumulative_return": cum_net,
        "n_days": n,
    }
    return out
