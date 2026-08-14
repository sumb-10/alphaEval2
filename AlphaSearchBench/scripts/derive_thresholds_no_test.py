"""[V5] validity research threshold를 test 데이터 없이 재도출.

pilot 보고서의 threshold(0.05/30/0.90)는 test(2021–2024) 분포를 근거로 제시
되어 leakage 소지가 있었다. 이 스크립트는 **train(2010–2016)·valid(2017–2019)
분포만으로** coverage/n_valid 통계를 재계산해 동일한 이봉 구조·동일 권장값이
나오는지 확인한다 (asb_pilot_verification.md V5).

실행: AlphaEval38 env, AlphaSearchBench/ 에서
  python scripts/derive_thresholds_no_test.py
출력: out/verification/validity_stats_train_valid.csv + stdout 요약.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASB = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ASB)
sys.path.insert(0, _ASB)

from alphasearchbench.config import Config                       # noqa: E402
from alphasearchbench.data.signal_context import SignalContext   # noqa: E402
from alphasearchbench.data.qlib_provider import FormulaEvalError # noqa: E402
from alphasearchbench.validity.metrics import compute_validity_stats  # noqa: E402

POOLS = {
    "all": [
        ("gp_smoke", "out/gplearn_fast_all_seed42_883881.csv"),
        ("random", "out/gplearn_fast_all_seed42_883883.csv"),
        ("gp_main", "out/gplearn_fast_all_seed42_883882.csv"),
    ],
    "csi800": [
        ("gp_csi800", "out/gplearn_tensor_csi800_seed42_883929.csv"),
    ],
}
CFG = {"all": "configs/examples/csi_example.yaml",
       "csi800": "configs/examples/csi800_example.yaml"}

rows = []
for market, pools in POOLS.items():
    ctx = SignalContext(Config.load(os.path.join(_ASB, CFG[market])))
    for split in ("train", "valid"):
        uni = ctx.split[split].universe_mask
        for method, csv in pools:
            for f in dict.fromkeys(pd.read_csv(os.path.join(_REPO, csv))["formula"]):
                rec = {"method": method, "split": split, "formula": f}
                try:
                    values, _ = ctx.evaluate(f, split)
                    rec.update(compute_validity_stats(values, uni))
                except FormulaEvalError as e:
                    rec["eval_error"] = e.reason
                rows.append(rec)

df = pd.DataFrame(rows)
out = os.path.join(_ASB, "out", "verification")
os.makedirs(out, exist_ok=True)
df.to_csv(os.path.join(out, "validity_stats_train_valid.csv"), index=False)

cols = ["method", "split", "mean_daily_coverage_ratio",
        "median_daily_n_valid", "valid_day_ratio"]
show = df[[c for c in cols if c in df.columns]].copy()
show["formula"] = df["formula"].str[:38]
print(show.to_string(index=False))

# threshold 재도출: train+valid 합산 분포의 이봉 경계
d = df.dropna(subset=["mean_daily_coverage_ratio"]) if "mean_daily_coverage_ratio" in df else df
cov = d["mean_daily_coverage_ratio"]
lo = cov[cov < 0.1]
hi = cov[cov >= 0.1]
print("\n[train+valid만] coverage 하위군 max =", f"{lo.max():.4f}" if len(lo) else "없음",
      "/ 상위군 min =", f"{hi.min():.4f}" if len(hi) else "없음")
print("[train+valid만] median_daily_n_valid 하위군 max =",
      int(d.loc[cov < 0.1, "median_daily_n_valid"].max()) if len(lo) else "없음",
      "/ 상위군 min =",
      int(d.loc[cov >= 0.1, "median_daily_n_valid"].min()) if len(hi) else "없음")
print("[train+valid만] valid_day_ratio 하위군 =",
      sorted(round(x, 3) for x in d.loc[cov < 0.1, "valid_day_ratio"]))
