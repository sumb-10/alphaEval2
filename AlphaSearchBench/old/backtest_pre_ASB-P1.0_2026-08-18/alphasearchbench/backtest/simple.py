"""Simple research backtester.

포트폴리오 (v0.1 확정 contract):
  * top X% long / bottom X% short (기본 20/20, config)
  * equal weight — long gross 0.5 / short gross 0.5 → Σ|w|=1, Σw=0
  * daily rebalance

WS-A 확장 (기본값은 v0.1 계약 그대로 — config로만 활성):
  * `backtest.selection: quantile(기본) | topk` + `backtest.topk`
    분위 대신 **상·하위 K종목 카운트** 선택 (참고연구의 top-k 관행:
    AlphaAgent KDD'25 top-50, AlphaGen top-50/30, AlphaEval 벤치마크 top-K)
  * `backtest.rebalance_days: 1(기본) | n`
    리밸런스일이 아니면 **전일 가중을 그대로 유지**(회전 0) — 회전율 상한을
    구조적으로 만드는 레버. 참고연구의 TopkDropout(n_drop) 버퍼와 목적은 같고
    수단이 다르다(우리는 보유기간, 논문은 교체 종목 수 제한).

execution (labels.py):
  * 기본 next_open_oo — t 종가 신호 → t+1 시가 진입 → t+2 시가 리밸런스
  * same_close는 **legacy/optimistic** (t 종가 정보로 t 종가 체결 가정)

turnover:
  * turnover_l1 = Σ|w_t − w_{t−1}|, turnover_oneway = 0.5·l1
  * 첫날은 무포지션→건립이므로 l1 = Σ|w| = 1 (비용에 포함 — 문서화)
  * cost = transaction_cost_rate × turnover(config: oneway|l1)

결측 처리 (문서화된 가정):
  * 가중치는 signal-valid 종목으로 구성
  * execution return이 NaN인 보유 종목(정지 등)은 그날 손익 기여 0
    (포지션 유지·무손익 가정) — n_missing_returns로 기록

provenance: 포트폴리오 수학은 Alphaagent/backtester.py 104-133행과 동치
(gross 1, (long+short)/2)를 weight 명시형으로 재구성; 첫날 NaN cost 버그는
수정(건립 비용 명시 부과).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .metrics import performance_metrics


def daily_long_short_weights(signal_row: np.ndarray, valid_row: np.ndarray,
                             top_fraction: float, bottom_fraction: float,
                             selection: str = "quantile",
                             topk: int = 50) -> np.ndarray:
    """하루의 long/short equal weight 벡터 (Σ|w|=1, Σw=0). 구성 불가면 0.

    selection="quantile": 상위 top_fraction / 하위 bottom_fraction (v0.1 계약)
    selection="topk":     신호 상위 K / 하위 K 종목 (동수는 index 순으로 결정 —
                          mergesort 안정 정렬로 재현 가능). valid 수가 2K 미만이면
                          K를 floor(n/2)로 축소하고, 그래도 0이면 무포지션.
    """
    w = np.zeros(len(signal_row))
    vals = signal_row[valid_row]
    if len(vals) < 2:
        return w
    if selection == "topk":
        idx = np.where(valid_row)[0]
        k = min(int(topk), len(idx) // 2)
        if k < 1:
            return w
        order = np.argsort(vals, kind="mergesort")       # 안정 정렬(동수 결정적)
        longs_i = idx[order[-k:]]
        shorts_i = idx[order[:k]]
        w[longs_i] = 0.5 / k
        w[shorts_i] = -0.5 / k
        return w
    if selection != "quantile":
        raise ValueError("backtest.selection must be quantile|topk")
    top_cut = np.quantile(vals, 1.0 - top_fraction)
    bot_cut = np.quantile(vals, bottom_fraction)
    longs = valid_row & (signal_row >= top_cut)
    shorts = valid_row & (signal_row <= bot_cut)
    overlap = longs & shorts                      # 퇴화(분산 극소) 시 중복 제거
    longs &= ~overlap
    shorts &= ~overlap
    nl, ns = int(longs.sum()), int(shorts.sum())
    if nl == 0 or ns == 0:
        return np.zeros(len(signal_row))
    w[longs] = 0.5 / nl
    w[shorts] = -0.5 / ns
    return w


def run_simple_backtest(signal: np.ndarray, valid: np.ndarray,
                        exec_returns: np.ndarray, dates,
                        top_fraction: float = 0.2, bottom_fraction: float = 0.2,
                        transaction_cost_rate: float = 0.0015,
                        cost_turnover_definition: str = "oneway",
                        rf_daily: float = 0.0,
                        selection: str = "quantile", topk: int = 50,
                        rebalance_days: int = 1) -> Tuple[Dict, pd.DataFrame]:
    """순수 함수 백테스트. 반환: (metrics dict, daily DataFrame)."""
    if cost_turnover_definition not in ("oneway", "l1"):
        raise ValueError("cost_turnover_definition must be oneway|l1")
    if int(rebalance_days) < 1:
        raise ValueError("backtest.rebalance_days must be >= 1")
    rebalance_days = int(rebalance_days)
    T, N = signal.shape
    prev_w = np.zeros(N)
    rows = []
    cum = 1.0
    for t in range(T):
        if t % rebalance_days == 0:
            w = daily_long_short_weights(signal[t], valid[t],
                                         top_fraction, bottom_fraction,
                                         selection=selection, topk=topk)
        else:
            w = prev_w                    # 보유 유지 → 이 날의 회전은 0
        r = exec_returns[t]
        finite_r = np.isfinite(r)
        gross = float(np.dot(w[finite_r], r[finite_r]))
        n_missing = int(((w != 0) & ~finite_r).sum())
        l1 = float(np.abs(w - prev_w).sum())
        oneway = 0.5 * l1
        cost_turn = oneway if cost_turnover_definition == "oneway" else l1
        cost = transaction_cost_rate * cost_turn
        net = gross - cost
        cum *= (1.0 + net)
        rows.append({
            "date": dates[t], "gross_return": gross, "cost": cost,
            "net_return": net, "turnover_l1": l1, "turnover_oneway": oneway,
            "long_count": int((w > 0).sum()), "short_count": int((w < 0).sum()),
            "gross_exposure": float(np.abs(w).sum()),
            "net_exposure": float(w.sum()),
            "n_missing_returns": n_missing,
            "cumulative_return": cum - 1.0,
        })
        prev_w = w
    daily = pd.DataFrame(rows)
    metrics = performance_metrics(daily, rf_daily=rf_daily)
    metrics["n_skipped_days"] = int((daily["gross_exposure"] == 0).sum())
    return metrics, daily


class SimpleBacktestEvaluator:
    """SignalContext 연동 래퍼 — 개별 alpha(oriented)와 pool(combined) 공용."""

    def __init__(self, ctx, cfg):
        self.ctx = ctx
        self.cfg = cfg
        self.execution = cfg.get("backtest.execution", "next_open_oo")
        self.top = float(cfg.get("backtest.top_fraction", 0.2))
        self.bottom = float(cfg.get("backtest.bottom_fraction", 0.2))
        self.cost_rate = float(cfg.get("backtest.transaction_cost_rate", 0.0015))
        self.cost_def = cfg.get("backtest.cost_turnover_definition", "oneway")
        self.selection = str(cfg.get("backtest.selection", "quantile"))
        self.topk = int(cfg.get("backtest.topk", 50))
        self.rebalance_days = int(cfg.get("backtest.rebalance_days", 1))
        self.rf_daily = float(cfg.get("backtest.rf_daily", 0.0))

    def _run(self, signal, valid, split, ident: str) -> Tuple[Dict, pd.DataFrame]:
        sc = self.ctx.split[split]
        exec_ret = sc.execution_return(self.execution)
        metrics, daily = run_simple_backtest(
            signal, valid, exec_ret, sc.dates,
            top_fraction=self.top, bottom_fraction=self.bottom,
            transaction_cost_rate=self.cost_rate,
            cost_turnover_definition=self.cost_def,
            rf_daily=self.rf_daily,
            selection=self.selection, topk=self.topk,
            rebalance_days=self.rebalance_days)
        metrics.update({"formula": ident, "split": split, "mode": "simple",
                        "execution": self.execution,
                        "transaction_cost_rate": self.cost_rate,
                        "cost_turnover_definition": self.cost_def,
                        "selection": self.selection,
                        "topk": self.topk if self.selection == "topk" else None,
                        "rebalance_days": self.rebalance_days})
        daily.insert(1, "formula_id", ident)
        return metrics, daily

    def evaluate_factor(self, formula: str, train_sign: int,
                        split: str = "test") -> Tuple[Dict, pd.DataFrame]:
        values, valid = self.ctx.evaluate(formula, split)
        oriented = self.ctx.oriented(values, train_sign)
        m, d = self._run(oriented, valid, split, formula)
        m["kind"] = "individual"
        m["train_sign"] = train_sign
        return m, d

    def evaluate_pool(self, formulas, weights, split: str = "test",
                      pool_id: str = "pool") -> Tuple[Dict, pd.DataFrame]:
        combo, mask = self.ctx.combined_signal(list(formulas), list(weights), split)
        valid = mask & np.isfinite(combo) & (np.abs(combo) > 0)   # z=0(결측)은 신호 없음
        m, d = self._run(combo, valid, split, pool_id)
        m["kind"] = "pool"
        m["n_factors"] = len(formulas)
        return m, d
