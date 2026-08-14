"""[Optional integration] Qlib native backtest adapter — **long-only 지원**.

Phase 8 timestamp/제약 audit 실측 결과 (tests/smoke/test_phase8_qlib_timestamp.py):
  * deal_price="open"일 때 주문은 해당 거래 스텝 날짜의 **시가**로 체결된다
    (deal_px == 그날 $open, 소수점까지 일치 확인).
  * 신호 t → **t+1 시가 체결** (TopkDropoutStrategy가 직전 거래일 신호 사용 —
    next-open 의미론, 테스트로 실증).
  * **naked short는 조용히 미체결**된다 (Exchange가 보유 없는 SELL을 거절,
    trade_val=0) — 즉 qlib native로 long-short 연구 백테스트는 불가.
    → long-short는 simple 모드(backtest/simple.py) 전용이며,
      qlib 모드는 long-only(top-k) 지원으로 문서화한다
      (docs/IMPLEMENTATION_NOTES.md, docs/BACKTEST.md).

suspension / limit-up-down / 거래비용은 qlib Exchange가 처리한다
(limit_threshold, open_cost/close_cost/min_cost — config).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .metrics import performance_metrics


def run_qlib_long_only(signal_df: pd.Series, start_time: str, end_time: str,
                       benchmark: str, topk: int = 30, n_drop: int = 3,
                       deal_price: str = "open", open_cost: float = 0.0005,
                       close_cost: float = 0.0015, min_cost: float = 5.0,
                       limit_threshold: float = 0.095,
                       account: float = 1e8) -> Tuple[Dict, pd.DataFrame]:
    """signal_df: MultiIndex (datetime, instrument) score Series.

    반환: (metrics dict — mode='qlib_long_only', daily report DataFrame)
    """
    from qlib.backtest import backtest
    from qlib.contrib.strategy import TopkDropoutStrategy

    strategy = TopkDropoutStrategy(signal=signal_df, topk=topk, n_drop=n_drop)
    executor_cfg = {"class": "SimulatorExecutor",
                    "module_path": "qlib.backtest.executor",
                    "kwargs": {"time_per_step": "day",
                               "generate_portfolio_metrics": True}}
    portfolio_dict, indicators = backtest(
        start_time=start_time, end_time=end_time,
        strategy=strategy, executor=executor_cfg, benchmark=benchmark,
        account=account,
        exchange_kwargs={"deal_price": deal_price, "open_cost": open_cost,
                         "close_cost": close_cost, "min_cost": min_cost,
                         "limit_threshold": limit_threshold})
    report, _positions = portfolio_dict["1day"]
    # report 컬럼: account, return(비용 차감 전), turnover, cost, bench ...
    daily = pd.DataFrame({
        "date": report.index,
        "gross_return": report["return"].to_numpy(dtype=float),
        "cost": report["cost"].to_numpy(dtype=float),
        "net_return": (report["return"] - report["cost"]).to_numpy(dtype=float),
        "turnover_l1": report["turnover"].to_numpy(dtype=float),
        "turnover_oneway": report["turnover"].to_numpy(dtype=float) * 0.5,
        "bench_return": report["bench"].to_numpy(dtype=float),
    }).reset_index(drop=True)
    metrics = performance_metrics(daily)
    metrics.update({
        "mode": "qlib_long_only",
        "execution": f"qlib_deal_price_{deal_price}",
        "topk": topk, "n_drop": n_drop,
        "benchmark": benchmark,
        "note": "long-only — qlib Exchange가 naked short를 거절함 (Phase 8 audit)",
    })
    return metrics, daily


class QlibBacktestEvaluator:
    """SignalContext 연동 — oriented 신호를 qlib signal Series로 변환해 실행."""

    def __init__(self, ctx, cfg):
        self.ctx = ctx
        self.cfg = cfg
        q = cfg.get("backtest.qlib", {}) or {}
        self.kw = {
            "deal_price": q.get("deal_price", "open"),
            "open_cost": float(q.get("open_cost", 0.0005)),
            "close_cost": float(q.get("close_cost", 0.0015)),
            "min_cost": float(q.get("min_cost", 5)),
            "limit_threshold": float(q.get("limit_threshold", 0.095)),
            "topk": int(q.get("topk", 30)),
            "n_drop": int(q.get("n_drop", 3)),
        }

    def _to_signal_series(self, values: np.ndarray, valid: np.ndarray,
                          split: str) -> pd.Series:
        sc = self.ctx.split[split]
        df = pd.DataFrame(np.where(valid, values, np.nan),
                          index=sc.dates, columns=self.ctx.engine.columns)
        s = df.stack(dropna=True)
        s.index.names = ["datetime", "instrument"]
        return s

    def evaluate_factor(self, formula: str, train_sign: int,
                        split: str = "test") -> Tuple[Dict, pd.DataFrame]:
        values, valid = self.ctx.evaluate(formula, split)
        oriented = self.ctx.oriented(values, train_sign)
        sig = self._to_signal_series(oriented, valid, split)
        start, end = self.ctx.splits_cfg[split]
        m, d = run_qlib_long_only(sig, start, end,
                                  benchmark=self.ctx.benchmark_ticker, **self.kw)
        m.update({"formula": formula, "split": split, "kind": "individual",
                  "train_sign": train_sign})
        d.insert(1, "formula_id", formula)
        return m, d
