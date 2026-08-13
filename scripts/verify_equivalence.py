#!/usr/bin/env python3
"""verify_equivalence.py — fast 경로가 원본과 동일한 결과를 내는지 검증.

검증 2단계:
  [1] 단위: 표현식별 IC — ICBacktester.calculate1(원본) vs FastICEvaluator(배치)
      * 정상 수식 + Qlib이 거절하는 수식($close 폴백 경로) 포함
  [2] 전체: 동일 seed 소형 진화 — 순정 _parallel_evolve vs fast 패치
      * 마지막 세대 전체 raw_fitness_, _best_programs의 수식·fitness_ 완전 일치

사용: (저장소 루트에서)  python scripts/verify_equivalence.py
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
qlib.init = lambda *a, **k: None    # ictester의 placeholder 재-init 차단

import numpy as np
from qlib.data import D

from fast_eval import FastICEvaluator, make_fast_parallel_evolve, ensure_backtest_importable
ensure_backtest_importable(REPO)   # backtest/backtester.py 누락 보완 (원본 무수정)
from backtest.ictester import ICBacktester

START, END = "2018-01-01", "2019-12-31"     # 검증은 짧은 기간으로 충분
MARKET = "csi300"

EXPRS = [
    "Div(Mean($close, 30), $volume)",
    "Sub(Std($high, 12), Mean($low, 5))",
    "Mul(Delta($vwap, 64), Sign($change))",
    "Add(WMA($close, 12), Skew($amount, 30))",
    "Abs(Slope($change, 5))",
    "Greater(Mean($close, 5), Mean($close, 30))",
    "Log(Div($amount, $volume))",
    "Resi($change, 64)",
    "ThisFunctionDoesNotExist($close, 5)",   # Qlib 거절 → $close 폴백 경로
    "Max($high, 12)",
]


def check(name, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return ok


def main():
    instruments = D.instruments(market=MARKET)
    all_ok = True

    # ---------- [1] 표현식별 IC 동등성 ----------
    print(f"[1] per-expression IC equivalence ({len(EXPRS)} exprs, {MARKET} {START}~{END})")
    ev = FastICEvaluator(instruments, START, END, chunk_size=4)  # 일부러 여러 chunk로 분할
    t0 = time.perf_counter()
    fast_ics = ev.evaluate(EXPRS)
    t_fast = time.perf_counter() - t0

    t0 = time.perf_counter()
    orig_ics = [ICBacktester(e, START, END, instruments, "day").calculate1() for e in EXPRS]
    t_orig = time.perf_counter() - t0

    for e, a, b in zip(EXPRS, orig_ics, fast_ics):
        ok = np.isclose(a, b, rtol=0, atol=1e-12) or (np.isnan(a) and np.isnan(b))
        all_ok &= check(f"IC {a:+.6f} vs {b:+.6f}  {e[:48]}", ok)
    print(f"  timing: original {t_orig:.1f}s  fast {t_fast:.1f}s  ({ev.stats()})")

    # ---------- [2] 동일 seed 소형 진화 ----------
    print(f"\n[2] full-evolution equivalence (pop=10, gens=2, seed=42, {MARKET})")
    import gplearn.genetic as G
    from gplearn.genetic import SymbolicTransformer
    from gplearn.config import functions_arity, FEATURE_LIST

    qlib_config = {"data_client": D, "instruments": instruments,
                   "start_time": START, "end_time": END, "freq": "day"}

    def run(patched):
        orig_pe = G._parallel_evolve
        if patched:
            ev2 = FastICEvaluator(instruments, START, END, chunk_size=6)
            G._parallel_evolve = make_fast_parallel_evolve(ev2)
        try:
            tr = SymbolicTransformer(
                population_size=10, hall_of_fame=6, n_components=3, generations=2,
                function_set=functions_arity.keys(), metric="pearson",
                parsimony_coefficient=0.0, qlib_config=qlib_config,
                feature_names=FEATURE_LIST, random_state=42, n_jobs=1)
            t0 = time.perf_counter()
            tr.fit()
            dt = time.perf_counter() - t0
        finally:
            G._parallel_evolve = orig_pe
        last_gen = [(str(p), p.raw_fitness_) for p in tr._programs[-1]]
        best = [(str(p), p.fitness_) for p in tr._best_programs]
        return last_gen, best, dt

    fast_last, fast_best, t_fastrun = run(patched=True)
    orig_last, orig_best, t_origrun = run(patched=False)

    ok = len(orig_last) == len(fast_last)
    for (es, fs_), (ef, ff) in zip(orig_last, fast_last):
        ok &= (es == ef) and np.isclose(fs_, ff, rtol=0, atol=1e-12)
    all_ok &= check(f"last generation: {len(orig_last)} programs identical (exprs + raw_fitness)", ok)

    ok = len(orig_best) == len(fast_best)
    for (es, fs_), (ef, ff) in zip(orig_best, fast_best):
        ok &= (es == ef) and np.isclose(fs_, ff, rtol=0, atol=1e-12)
    all_ok &= check(f"_best_programs: {len(orig_best)} identical (exprs + fitness_)", ok)
    print(f"  timing: original fit {t_origrun:.1f}s  fast fit {t_fastrun:.1f}s")

    print(f"\n{'ALL PASS — fast path is result-invariant' if all_ok else 'FAILURES PRESENT'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
