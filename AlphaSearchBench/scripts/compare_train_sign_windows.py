"""[V1] train_sign 복원 창 비교: pilot(2010–2016) vs 마이닝 창(2010–2019).

pilot의 oriented test IC가 잘못된 부호 기준으로 계산됐는지 판정한다.
전제: out/pilot/(csi_example, train 2010–2016)과
      out/pilot_signfix/(csi_mining_window, train 2010–2019)가 존재.

실행: python scripts/compare_train_sign_windows.py
출력: out/verification/train_sign_window_comparison.csv + stdout 요약.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASB = os.path.dirname(_HERE)

RUNS = ["gp_smoke", "random", "gp_main", "gp_csi800"]
rows = []
for run in RUNS:
    a = pd.read_parquet(os.path.join(_ASB, "out", "pilot", run,
                                     "metrics", "oos_factor_metrics.parquet"))
    b = pd.read_parquet(os.path.join(_ASB, "out", "pilot_signfix", run,
                                     "metrics", "oos_factor_metrics.parquet"))
    a = a[a["kind"] == "individual"].set_index("formula")
    b = b[b["kind"] == "individual"].set_index("formula")
    for f in a.index:
        ra, rb = a.loc[f], b.loc[f]
        rec = {"run": run, "formula": f,
               "valid_pilot": bool(ra["valid"]), "valid_signfix": bool(rb["valid"])}
        if ra["valid"] and rb["valid"]:
            s16, s19 = ra["signed_train_IC"], rb["signed_train_IC"]
            rec.update({
                "signed_IC_2010_2016": s16, "signed_IC_2010_2019": s19,
                "sign_2016": int(np.sign(s16)) or 1, "sign_2019": int(np.sign(s19)) or 1,
                "sign_flip": bool(np.sign(s16) != np.sign(s19)),
                "test_IC_pilot": ra["IC"], "test_IC_signfix": rb["IC"],
                "test_RankIC_pilot": ra["RankIC"], "test_RankIC_signfix": rb["RankIC"],
            })
        else:
            rec["invalid_reason"] = rb.get("invalid_reason") or ra.get("invalid_reason")
        rows.append(rec)

df = pd.DataFrame(rows)
out = os.path.join(_ASB, "out", "verification")
os.makedirs(out, exist_ok=True)
df.to_csv(os.path.join(out, "train_sign_window_comparison.csv"), index=False)

ok = df.dropna(subset=["sign_flip"]) if "sign_flip" in df else pd.DataFrame()
n_flip = int(ok["sign_flip"].sum()) if len(ok) else 0
print(f"비교 가능 {len(ok)}개 중 sign flip = {n_flip}개")
if n_flip:
    cols = ["run", "formula", "signed_IC_2010_2016", "signed_IC_2010_2019",
            "test_IC_pilot", "test_IC_signfix"]
    fl = ok[ok["sign_flip"]][cols].copy()
    fl["formula"] = fl["formula"].str[:45]
    print(fl.to_string(index=False))
print("\n[전수 요약]")
show = df.copy()
show["formula"] = show["formula"].str[:42]
cols = [c for c in ["run", "formula", "signed_IC_2010_2016", "signed_IC_2010_2019",
                    "sign_flip", "test_IC_pilot", "test_IC_signfix",
                    "invalid_reason"] if c in show.columns]
print(show[cols].to_string(index=False))
