"""Phase 8 smoke [Optional]: Qlib native backtest — timestamp audit.

증명 대상:
  1. 신호 t → 주문/체결이 **t+1**에 발생 (next-open 의미론)
  2. deal_price="open" → 체결가 == 그날 $open (수치 일치)
  3. naked short는 미체결 (long-only 제약) — 지원 범위 문서화 근거
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config                    # noqa: E402
from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib  # noqa: E402

STOCKS = ["SH600000", "SH600016", "SH600019", "SH600028", "SH600030"]
SPIKE_STOCK = "SH600036"          # 특정 날짜에만 신호가 튀는 종목
SPIKE_DATE = pd.Timestamp("2019-06-11")


@pytest.fixture(scope="module", autouse=True)
def _qlib():
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"], 4)


def _make_signal():
    from qlib.data import D
    cal = D.calendar(start_time="2019-06-03", end_time="2019-06-21", freq="day")
    rows = []
    for dt in cal:
        for j, s in enumerate(STOCKS):
            rows.append({"datetime": dt, "instrument": s, "score": float(j)})
        # spike: 오직 SPIKE_DATE 신호에서만 최고점
        rows.append({"datetime": dt, "instrument": SPIKE_STOCK,
                     "score": 100.0 if dt == SPIKE_DATE else -100.0})
    return pd.DataFrame(rows).set_index(["datetime", "instrument"])["score"]


def test_timestamp_audit_next_open_and_deal_price():
    import qlib.backtest.exchange as exch_mod
    from qlib.backtest import backtest
    from qlib.contrib.strategy import TopkDropoutStrategy
    from qlib.data import D

    audit = []
    orig = exch_mod.Exchange.deal_order

    def logged(self, order, trade_account=None, position=None, dealt_order_amount=None):
        res = orig(self, order, trade_account=trade_account, position=position,
                   dealt_order_amount=dealt_order_amount)
        try:
            px = self.get_deal_price(order.stock_id, order.start_time,
                                     order.end_time, direction=order.direction)
        except Exception:
            px = None
        audit.append({"stock": order.stock_id, "dir": int(order.direction),
                      "date": pd.Timestamp(order.start_time).normalize(),
                      "deal_px": px})
        return res

    exch_mod.Exchange.deal_order = logged
    try:
        strategy = TopkDropoutStrategy(signal=_make_signal(), topk=3, n_drop=1)
        executor_cfg = {"class": "SimulatorExecutor",
                        "module_path": "qlib.backtest.executor",
                        "kwargs": {"time_per_step": "day",
                                   "generate_portfolio_metrics": True}}
        backtest(start_time="2019-06-05", end_time="2019-06-20",
                 strategy=strategy, executor=executor_cfg, benchmark="SH000300",
                 account=1e8,
                 exchange_kwargs={"deal_price": "open", "open_cost": 0.0005,
                                  "close_cost": 0.0015, "min_cost": 5,
                                  "limit_threshold": 0.095})
    finally:
        exch_mod.Exchange.deal_order = orig

    assert audit, "체결 로그가 없습니다"
    # (2) 체결가 == 그날 시가
    a0 = audit[0]
    o = D.features([a0["stock"]], ["$open"], str(a0["date"].date()),
                   str(a0["date"].date()), freq="day")
    assert float(o.iloc[0, 0]) == pytest.approx(a0["deal_px"], rel=1e-6)

    # (1) spike 신호(t=06-11) → 매수 체결이 정확히 t+1(06-12)에 발생
    buys = [a for a in audit if a["stock"] == SPIKE_STOCK and a["dir"] == 1]
    assert buys, f"{SPIKE_STOCK} 매수가 없습니다: {audit}"
    next_day = pd.Timestamp("2019-06-12")
    assert buys[0]["date"] == next_day, (
        f"신호 {SPIKE_DATE.date()} → 체결 {buys[0]['date'].date()} "
        f"(기대: {next_day.date()} = t+1 open)")


def test_naked_short_is_rejected():
    from qlib.backtest.position import Position
    from qlib.backtest.exchange import Exchange
    from qlib.backtest.decision import Order, OrderDir

    ex = Exchange(freq="day", start_time="2019-06-05", end_time="2019-06-20",
                  deal_price="open")
    pos = Position(cash=1e6)
    order = Order(stock_id="SH600000", amount=1000, direction=OrderDir.SELL,
                  start_time=pd.Timestamp("2019-06-06"),
                  end_time=pd.Timestamp("2019-06-06"))
    trade_val, trade_cost, trade_price = ex.deal_order(order, position=pos)
    assert trade_val == 0.0                      # 보유 없는 SELL → 미체결
    assert pos.get_stock_list() == []            # 음수 포지션 미생성 → long-only
