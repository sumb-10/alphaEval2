"""[ASB-P1.0 §4] 배치 프로파일 집계 — family 내부에서만.

protocol_sweep 산출물(pool 단위 셀 성과)을 읽어 pool별 프로파일을 계산한다.
서로 다른 성과량(LS Sharpe vs LO 초과 AR)은 절대 하나의 분포로 합치지 않는다.

Common-LS family (mode=simple 구성들):
  median_sharpe, sharpe_iqr, pdr(Sharpe>0 비율 — 기술 진단),
  worst_sharpe(tail 진단), median_annret, median_mdd,
  gross_to_net_drop(0bps 구성 median Sharpe − 유비용 구성 median Sharpe),
  median_ann_turnover
Anchor family (mode=qlib): excess_ar, ir, mdd_excess (구성이 1개면 그대로)

사용:
  python scripts/deployment_profile.py --sweep out/protocol_sweep/<tag> [...]
  (복수 sweep 디렉토리를 주면 arm 축이 합쳐진다 — 예: Track A 8구성)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from glob import glob
from typing import List

import numpy as np
import pandas as pd

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _abs(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(_ASB_ROOT, p)


def load_sweeps(dirs: List[str]) -> pd.DataFrame:
    frames, meta = [], {}
    for d in dirs:
        d = _abs(d)
        f = os.path.join(d, "metrics", "protocol_sweep_pool.parquet")
        df = pd.read_parquet(f)
        man = json.load(open(sorted(glob(os.path.join(d, "manifests", "sweep_*.json")))[-1]))
        arm_mode = {a["arm"]: (a.get("backtest") or {}).get("mode", "simple")
                    for a in man.get("arms", [])}
        arm_cost = {a["arm"]: (a.get("backtest") or {}).get("transaction_cost_rate")
                    for a in man.get("arms", [])}
        arm_comb = {a["arm"]: a.get("combiner", "raw_equal") for a in man.get("arms", [])}
        df["engine_mode"] = df["arm"].map(arm_mode)
        df["cost_rate"] = df["arm"].map(arm_cost)
        df["combiner_cfg"] = df["arm"].map(arm_comb)
        df["sweep_tag"] = man.get("tag")
        meta[man.get("tag")] = man.get("protocol_version")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.attrs["protocol_versions"] = meta
    return out


def ls_profile(g: pd.DataFrame) -> dict:
    ok = g[g["status"] == "ok"]
    sh = ok["Sharpe"].astype(float)
    row = {
        "n_configs": int(len(g)), "n_ok": int(len(ok)),
        "median_sharpe": float(sh.median()) if len(ok) else np.nan,
        "sharpe_iqr": float(sh.quantile(0.75) - sh.quantile(0.25)) if len(ok) > 1 else np.nan,
        "pdr": float((sh > 0).mean()) if len(ok) else np.nan,
        "worst_sharpe": float(sh.min()) if len(ok) else np.nan,
        "median_annret": float(ok["AnnRet_arith"].median()) if len(ok) else np.nan,
        "median_mdd": float(ok["MDD"].median()) if len(ok) else np.nan,
        "median_ann_turnover": (float(ok["annualized_turnover_oneway"].median())
                                if len(ok) else np.nan),
    }
    zero = ok[ok["cost_rate"] == 0.0]["Sharpe"].astype(float)
    paid = ok[ok["cost_rate"] > 0.0]["Sharpe"].astype(float)
    row["gross_to_net_sharpe_drop"] = (float(zero.median() - paid.median())
                                       if len(zero) and len(paid) else np.nan)
    return row


def anchor_profile(g: pd.DataFrame) -> dict:
    ok = g[g["status"] == "ok"]
    def med(c):
        return float(ok[c].astype(float).median()) if len(ok) and c in ok else np.nan
    return {"n_configs": int(len(g)), "n_ok": int(len(ok)),
            "excess_ar": med("AnnRet_excess"), "ir": med("IR"),
            "mdd_excess": med("MDD_excess"), "annret": med("AnnRet_arith"),
            "ann_turnover": med("annualized_turnover_oneway")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    df = load_sweeps(args.sweep)

    rows = []
    for (rid, fam), g in df.groupby(
            ["run_id", df["engine_mode"].map({"simple": "common_ls", "qlib": "anchor"})]):
        prof = ls_profile(g) if fam == "common_ls" else anchor_profile(g)
        prof.update({"run_id": rid, "family": fam,
                     "mining_framework": g["mining_framework"].iloc[0]
                     if "mining_framework" in g else None})
        rows.append(prof)
    prof_df = pd.DataFrame(rows)

    out_dir = _abs(args.out) if args.out else _abs(args.sweep[0])
    os.makedirs(os.path.join(out_dir, "metrics"), exist_ok=True)
    dest = os.path.join(out_dir, "metrics", "deployment_profiles.parquet")
    prof_df.to_parquet(dest, index=False)

    pd.set_option("display.width", 240)
    for fam in ("common_ls", "anchor"):
        sub = prof_df[prof_df["family"] == fam]
        if sub.empty:
            continue
        cols = [c for c in ("run_id", "n_ok", "median_sharpe", "sharpe_iqr", "pdr",
                            "worst_sharpe", "median_mdd", "gross_to_net_sharpe_drop",
                            "median_ann_turnover", "excess_ar", "ir", "mdd_excess")
                if c in sub.columns and sub[c].notna().any()]
        print(f"\n=== {fam} profile ===")
        print(sub[cols].sort_values(cols[2] if len(cols) > 2 else cols[0],
                                    ascending=False)
              .to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
    print(f"\n→ {dest}  (protocol_versions: {df.attrs.get('protocol_versions')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
