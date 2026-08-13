#!/usr/bin/env python3
"""verify_tensor_eval.py — tensor_eval이 qlib과 얼마나 일치하는지 측정.

  [1] 연산자별 값 비교: 29개 연산자 + 합성식 — D.features(qlib) vs TensorEvaluator.frame
      (float32 비트 단위 일치율, 최대 절대 오차, NaN 불일치 수)
  [2] IC 비교: ICBacktester.calculate1(원본) vs TensorEvaluator.ic
  [3] 속도 비교

사용: (저장소 루트에서)  python scripts/verify_tensor_eval.py
"""

import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PROVIDER = "/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data"

import qlib
qlib.init(provider_uri=DEFAULT_PROVIDER, region="cn", kernels=8,
          expression_cache=None, dataset_cache=None)
qlib.init = lambda *a, **k: None

import numpy as np
import pandas as pd
from qlib.data import D

from fast_eval import ensure_backtest_importable
ensure_backtest_importable(REPO)
from backtest.ictester import ICBacktester
from tensor_eval import TensorEvaluator

S, E = "2016-01-01", "2019-12-31"
MARKET = "csi300"

# 29개 연산자 전수 + 실제 GP 산출물 스타일 합성식
OP_EXPRS = [
    "Abs($change)", "Sign($change)", "Log($volume)",
    "Add($high, $low)", "Sub($close, $open)", "Mul($close, $volume)",
    "Div($amount, $volume)", "Power(Abs($change), 2)",
    "Greater($open, $close)", "Less($open, $close)",
    "Ref($close, 5)", "Mean($close, 30)", "Sum($volume, 12)",
    "Std($high, 12)", "Var($low, 5)", "Skew($amount, 30)", "Kurt($close, 64)",
    "Min($low, 30)", "Max($high, 64)",
    "IdxMin($low, 12)", "IdxMax($high, 30)", "Med($close, 12)", "Mad($close, 30)",
    "Delta($vwap, 64)", "Slope($close, 12)", "Rsquare($close, 30)", "Resi($change, 64)",
    "WMA($close, 12)", "EMA($close, 30)",
]
COMPOSITE_EXPRS = [
    "Min(Abs($change), 12)",
    "Power(Resi($high, 30), Slope($close, 12))",
    "Div(Mean($close, 30), $volume)",
    "Add(WMA($close, 12), Skew($amount, 30))",
    "Sub(Std(Div($high, $low), 12), Mean($close, 5))",
    "EMA(Delta(Mad($close, 5), 12), 30)",
    "IdxMax(Greater($open, Mean($close, 5)), 12)",
    "Mean(Slope(Log($volume), 12), 5)",
]
IC_EXPRS = COMPOSITE_EXPRS + ["Mean($close, 30)", "WMA($close, 120)", "Kurt($close, 64)"]


def compare_values(qdf, tframe, dump=0):
    """qlib 결과(MultiIndex Series)와 tensor frame을 정렬해 비교."""
    q = qdf.iloc[:, 0]
    t = tframe.stack(dropna=False)                 # (datetime, instrument)
    t.index = t.index.swaplevel(0, 1)              # → (instrument, datetime)
    t = t.reindex(q.index)
    qv, tv = q.to_numpy(), t.to_numpy(dtype=np.float32)
    both_nan = np.isnan(qv) & np.isnan(tv)
    eq = (qv == tv) | both_nan
    n = len(qv)
    nan_mismatch = int((np.isnan(qv) ^ np.isnan(tv)).sum())
    both = ~np.isnan(qv) & ~np.isnan(tv)
    diffs = np.abs(np.where(both, qv, 0).astype(np.float64) - np.where(both, tv, 0).astype(np.float64))
    maxdiff = float(diffs.max()) if both.any() else 0.0
    if dump and not eq.all():
        bad = np.where(~eq)[0]
        order = bad[np.argsort(-diffs[bad])][:dump]
        for i in order:
            print(f"        diff@ {q.index[i]}  qlib={qv[i]!r} tensor={tv[i]!r}")
    return n, float(eq.mean()), maxdiff, nan_mismatch


def main():
    inst = D.instruments(market=MARKET)

    t0 = time.perf_counter()
    ev = TensorEvaluator(S, E, market=MARKET)
    t_init = time.perf_counter() - t0
    print(f"panel preload: {t_init:.1f}s  (grid {len(ev.sel_dates)}d x {len(ev.columns)} stocks)\n")

    print(f"[1] operator-level value comparison ({MARKET} {S}~{E})")
    print(f"    {'expression':44} {'rows':>9} {'bit-equal':>9} {'max|diff|':>12} {'nanΔ':>6} {'q(s)':>6} {'t(s)':>6}")
    worst = []
    tq_tot = tt_tot = 0.0
    for expr in OP_EXPRS + COMPOSITE_EXPRS:
        t0 = time.perf_counter()
        qdf = D.features(inst, [expr], start_time=S, end_time=E, freq="day")
        tq = time.perf_counter() - t0
        t0 = time.perf_counter()
        tframe = ev.frame(expr)
        tt = time.perf_counter() - t0
        n, pct, maxdiff, nanmm = compare_values(qdf, tframe, dump=3)
        tq_tot += tq; tt_tot += tt
        flag = "" if (pct == 1.0) else "  <-- CHECK"
        print(f"    {expr:44} {n:>9,} {pct:>9.2%} {maxdiff:>12.3e} {nanmm:>6} {tq:>6.1f} {tt:>6.1f}{flag}")
        if pct < 1.0:
            worst.append((expr, pct, maxdiff, nanmm))
    print(f"    qlib total {tq_tot:.1f}s vs tensor total {tt_tot:.1f}s (x{tq_tot/max(tt_tot,1e-9):.1f})\n")

    print(f"[2] IC comparison (ICBacktester.calculate1 vs TensorEvaluator.ic)")
    max_ic_diff = 0.0
    for expr in IC_EXPRS:
        t0 = time.perf_counter()
        a = ICBacktester(expr, S, E, inst, "day").calculate1()
        tq = time.perf_counter() - t0
        t0 = time.perf_counter()
        b = ev.ic(expr)
        tt = time.perf_counter() - t0
        d = abs(a - b)
        max_ic_diff = max(max_ic_diff, d)
        print(f"    {expr:44} orig={a:+.8f} tensor={b:+.8f} |d|={d:.2e}  ({tq:.1f}s vs {tt:.2f}s)")

    print(f"\n[3] summary")
    print(f"    value-level: {len(OP_EXPRS)+len(COMPOSITE_EXPRS)-len(worst)}/{len(OP_EXPRS)+len(COMPOSITE_EXPRS)} "
          f"expressions bit-identical (float32)")
    for expr, pct, maxdiff, nanmm in worst:
        print(f"      not exact: {expr}  eq={pct:.4%} max|d|={maxdiff:.3e} nanΔ={nanmm}")
    print(f"    max IC diff: {max_ic_diff:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
