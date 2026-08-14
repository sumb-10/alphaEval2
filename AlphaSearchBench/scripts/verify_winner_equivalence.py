"""Pilot 신뢰성 검증 스크립트 (asb_pilot_verification.md V2·V3·V7).

A. [V2] winner formula 신호 동등성: qlib D.features(마이닝 원본 의미론) vs
   ASB FormulaEngine — 공통 finite 셀 max|diff|, NaN 패턴 XOR, 일별 n_valid.
   + 마이닝 fitness 재현: |mean(daily Pearson IC)| vs CSV 기록값.
B. [V3] coverage denominator PIT 감사: 샘플 날짜의 n_universe vs 정적 컬럼 수
   vs finite $close 종목 수.
C. [V7] 헤드라인 수치 독립 재계산: ASB 지표 코드를 쓰지 않고 qlib+pandas만으로
   Log($volume)·gp_main sibling의 test IC/RankIC 재계산 → parquet 값과 대조.

실행: AlphaEval38 env, AlphaSearchBench/ 에서
  python scripts/verify_winner_equivalence.py [--section A|B|C|all]
출력: out/verification/ 아래 csv + stdout 요약.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASB = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ASB)
sys.path.insert(0, _ASB)

from alphasearchbench.config import Config                    # noqa: E402
from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib  # noqa: E402

MINING_START, MINING_END = "2010-01-01", "2019-12-31"
TEST_START, TEST_END = "2021-01-01", "2024-12-31"
LABEL_EXPR = "Ref($close, -1)/$close - 1"

# (method, market, csv) — pilot 입력 그대로
POOLS = [
    ("gp_smoke", "all", "out/gplearn_fast_all_seed42_883881.csv"),
    ("random", "all", "out/gplearn_fast_all_seed42_883883.csv"),
    ("gp_main", "all", "out/gplearn_fast_all_seed42_883882.csv"),
    ("gp_csi800", "csi800", "out/gplearn_tensor_csi800_seed42_883929.csv"),
]

OUT_DIR = os.path.join(_ASB, "out", "verification")


def qlib_panel(market: str, exprs, start: str, end: str) -> pd.DataFrame:
    """qlib 원본 의미론 그대로: D.features(막 instruments config) → MultiIndex."""
    from qlib.data import D
    df = D.features(D.instruments(market=market), exprs,
                    start_time=start, end_time=end, freq="day")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df


def daily_pearson_ic(factor: pd.Series, label: pd.Series) -> pd.Series:
    """fast_eval._ic_pair와 동일: 쌍별 dropna 후 일별 Pearson."""
    both = pd.concat({"factor": factor, "label": label}, axis=1).dropna()
    return both.groupby(level="datetime").apply(
        lambda x: x["factor"].corr(x["label"]))


def section_a():
    print("=" * 72)
    print("A. [V2] winner 신호 동등성 + 마이닝 fitness 재현")
    print("=" * 72)
    from alphasearchbench.data.qlib_provider import FormulaEngine, FormulaEvalError

    engine = FormulaEngine(panel_start=MINING_START, panel_end=MINING_END)
    rows = []
    for method, market, csv in POOLS:
        pool = pd.read_csv(os.path.join(_REPO, csv))
        uniq = list(dict.fromkeys(pool["formula"]))
        fit = {f: g["IC"].iloc[0] for f, g in pool.groupby("formula")}
        label = qlib_panel(market, [LABEL_EXPR], MINING_START, MINING_END)
        label.columns = ["label"]
        for f in uniq:
            rec = {"method": method, "formula": f, "csv_fitness": fit[f]}
            try:
                old = qlib_panel(market, [f], MINING_START, MINING_END).iloc[:, 0]
            except Exception as e:
                rec["qlib_error"] = f"{type(e).__name__}: {e}"
                rows.append(rec)
                continue
            try:
                new_df = engine.frame(f, MINING_START, MINING_END)
            except FormulaEvalError as e:
                rec["asb_error"] = e.reason if hasattr(e, "reason") else str(e)
                rows.append(rec)
                continue
            # long-form 정렬: qlib MultiIndex (instrument, datetime) ← ASB wide
            new_long = new_df.stack(dropna=False)
            new_long.index = new_long.index.swaplevel(0, 1)
            new_long = new_long.reindex(old.index)  # qlib 쿼리 (inst,date) 격자
            of, nf = np.isfinite(old.values), np.isfinite(new_long.values)
            both = of & nf
            diff = np.abs(old.values[both] - new_long.values[both])
            rec.update({
                "n_grid_cells": len(old),
                "n_finite_qlib": int(of.sum()),
                "n_finite_asb": int(nf.sum()),
                "nan_pattern_xor": int((of ^ nf).sum()),
                "max_abs_diff": float(diff.max()) if both.any() else np.nan,
            })
            # fitness 재현 (qlib 신호·ASB 신호 각각, fast_eval 집계 그대로)
            ics_old = daily_pearson_ic(old, label["label"])
            ics_new = daily_pearson_ic(new_long, label["label"])
            rec.update({
                "ic_days": int(ics_old.notna().sum()),
                "refit_qlib_absIC": float(abs(ics_old.mean())),
                "refit_asb_absIC": float(abs(ics_new.mean())),
                "refit_qlib_signedIC": float(ics_old.mean()),
            })
            rec["fitness_abs_err"] = abs(rec["refit_qlib_absIC"] - fit[f])
            rows.append(rec)
            print(f"[{method}] {f[:60]}")
            print(f"   XOR={rec.get('nan_pattern_xor')} maxdiff={rec.get('max_abs_diff'):.3g}"
                  f" csv={fit[f]:.6f} refit(qlib)={rec['refit_qlib_absIC']:.6f}"
                  f" refit(ASB)={rec['refit_asb_absIC']:.6f} ic_days={rec['ic_days']}")
    df = pd.DataFrame(rows)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(OUT_DIR, "winner_equivalence.csv"), index=False)
    print("→ 저장:", os.path.join(OUT_DIR, "winner_equivalence.csv"))
    return df


def section_b():
    print("=" * 72)
    print("B. [V3] coverage denominator PIT 감사")
    print("=" * 72)
    from alphasearchbench.data.universe import build_universe_mask
    from qlib.data import D

    rows = []
    for market in ["all", "csi800"]:
        close = qlib_panel(market, ["$close"], TEST_START, TEST_END).iloc[:, 0]
        wide = close.unstack(level="instrument") if close.index.nlevels == 2 else close
        # ASB 의미론: 전체 컬럼 격자 + PIT mask
        all_close = qlib_panel("all", ["$close"], TEST_START, TEST_END).iloc[:, 0]
        grid = all_close.unstack(level="instrument")
        mask, uh = build_universe_mask(market, grid.index, grid.columns)
        static_n = mask.any(axis=0).sum()
        for probe in ["2021-06-01", "2023-06-01", "2024-06-03"]:
            t = grid.index.searchsorted(pd.Timestamp(probe))
            date = grid.index[t]
            n_uni = int(mask[t].sum())
            n_close_qlib = int(wide.loc[date].notna().sum()) if date in wide.index else -1
            rows.append({"market": market, "date": str(date.date()),
                         "n_universe(mask)": n_uni,
                         "n_static_columns": int(static_n),
                         "n_finite_close(D.features)": n_close_qlib})
            print(f"[{market}] {date.date()}: PIT분모={n_uni}, 정적컬럼={static_n}, "
                  f"finite $close={n_close_qlib}")
    df = pd.DataFrame(rows)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(OUT_DIR, "coverage_denominator_audit.csv"), index=False)
    print("→ 저장:", os.path.join(OUT_DIR, "coverage_denominator_audit.csv"))
    return df


def section_c():
    print("=" * 72)
    print("C. [V7] 헤드라인 수치 독립 재계산 (qlib+pandas만)")
    print("=" * 72)
    targets = [
        ("gp_smoke", "all", "Log($volume)"),
        ("gp_main", "all",
         "WMA(Rsquare(Div(WMA(Rsquare(Div(Power($volume, $open), "
         "Mean(Sign($change), 12)), 64), 30), EMA($volume, 30)), 12), 30)"),
    ]
    rows = []
    label_all = qlib_panel("all", [LABEL_EXPR], TEST_START, TEST_END)
    label_all.columns = ["label"]
    label_tr = qlib_panel("all", [LABEL_EXPR], MINING_START, MINING_END)
    label_tr.columns = ["label"]
    for method, market, f in targets:
        # train sign (마이닝 창)
        ftr = qlib_panel(market, [f], MINING_START, MINING_END).iloc[:, 0]
        sic_tr = daily_pearson_ic(ftr, label_tr["label"]).mean()
        sign = 1 if sic_tr >= 0 else -1
        # test oriented IC / RankIC
        fte = qlib_panel(market, [f], TEST_START, TEST_END).iloc[:, 0] * sign
        both = pd.concat({"factor": fte, "label": label_all["label"]}, axis=1).dropna()
        ic = both.groupby(level="datetime").apply(
            lambda x: x["factor"].corr(x["label"]))
        ric = both.groupby(level="datetime").apply(
            lambda x: x["factor"].rank().corr(x["label"].rank()))
        rec = {"method": method, "formula": f[:60],
               "signed_train_IC(2010-2019)": float(sic_tr), "sign": sign,
               "test_IC_indep": float(ic.mean()), "test_RankIC_indep": float(ric.mean()),
               "test_ic_days": int(ic.notna().sum())}
        rows.append(rec)
        print(f"[{method}] {f[:50]}…" if len(f) > 50 else f"[{method}] {f}")
        print(f"   sign={sign} (train {sic_tr:+.4f})  test IC={rec['test_IC_indep']:+.5f}"
              f"  RankIC={rec['test_RankIC_indep']:+.5f}  ic_days={rec['test_ic_days']}")
    df = pd.DataFrame(rows)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(OUT_DIR, "independent_recompute.csv"), index=False)
    print("→ 저장:", os.path.join(OUT_DIR, "independent_recompute.csv"))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="all", choices=["A", "B", "C", "all"])
    args = ap.parse_args()
    _cfg = Config.load(os.path.join(_ASB, "configs", "examples", "csi_example.yaml"))
    bootstrap_qlib(_cfg["dataset.provider_uri"], _cfg["dataset.region"],
                   _cfg["dataset.qlib_kernels"])
    if args.section in ("A", "all"):
        section_a()
    if args.section in ("B", "all"):
        section_b()
    if args.section in ("C", "all"):
        section_c()
