"""Backtest performance metrics.

정의 (manifest에 기록되는 확정 convention):
  * AnnRet_arith = mean(daily_net_return) × 252   — AlphaEval 논문(Eq.21) 비교용
  * CAGR         = (1 + cumulative_net_return)^(252/n) − 1
                   (provenance: Alphaagent/backtester.py 172행)
  * Sharpe       = mean(net)/std(net, ddof=1) × √252, risk-free 0 (인터페이스 개방)
  * MDD          = **positive magnitude** (내부 계산은 음수 낙폭의 최솟값)
  * turnover_l1  = Σ|w_t − w_{t−1}|,  turnover_oneway = 0.5 × l1
    (AlphaEval 논문 Eq.23은 l1 정의 — 0.5 계수 없음)

벤치마크 상대 지표 (daily에 `bench_return` 컬럼이 있을 때만 추가):
  * AnnRet_excess = mean(net − bench) × 252   — AlphaAgent(KDD'25) Table 2의 AR
    (논문의 AR은 **지수 대비 초과** 연수익)
  * IR            = mean(excess)/std(excess, ddof=1) × √252  — 논문의 IR
  * MDD_excess    = 초과수익 시계열의 MDD (positive magnitude)
  long-short(시장중립) 모드에서는 bench_return이 없으므로 이 필드도 없다 —
  즉 IR은 long-only 벤치마크 상대 프로토콜(A3)에서만 정의된다.
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
    if "bench_return" in daily.columns:
        out.update(benchmark_relative_metrics(daily))
    return out


def benchmark_relative_metrics(daily: pd.DataFrame) -> Dict[str, float]:
    """지수 대비 초과수익 지표 (AlphaAgent KDD'25 Table 2의 AR·IR 정의).

    excess_t = net_t − bench_t (일별 산술 차 — 논문도 일별 초과수익 기준 IR).
    """
    net = daily["net_return"].to_numpy(dtype=float)
    bench = daily["bench_return"].to_numpy(dtype=float)
    ok = np.isfinite(net) & np.isfinite(bench)
    if ok.sum() < 2:
        return {"AnnRet_excess": float("nan"), "IR": float("nan"),
                "MDD_excess": float("nan"), "AnnRet_bench": float("nan"),
                "n_days_excess": int(ok.sum())}
    ex = net[ok] - bench[ok]
    sd = ex.std(ddof=1)
    return {
        "AnnRet_excess": float(ex.mean() * D_YEAR),
        "IR": float(ex.mean() / sd * np.sqrt(D_YEAR)) if sd > 0 else float("nan"),
        "MDD_excess": max_drawdown_magnitude(ex),
        "AnnRet_bench": float(bench[ok].mean() * D_YEAR),
        "n_days_excess": int(ok.sum()),
    }
