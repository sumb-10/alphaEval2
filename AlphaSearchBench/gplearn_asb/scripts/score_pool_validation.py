#!/usr/bin/env python
"""[C-1] GP-side validation scorer 실행기.

사용:
  python scripts/score_pool_validation.py \
      --pool out/<run>/metrics/final_pool_<run>.csv \
      --start 2022-01-01 --end 2023-12-31 \
      --market csi800 --out out/<run>/metrics/c1_valscore.json

계약: docs/experiments/2026-08-19_C1_runbook_draft.md (동결).
ASB evaluation policy 불사용 — GP 내부 semantics (validation_scorer.py).
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="final_pool CSV")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--market", default="csi800")
    ap.add_argument("--pool-size", type=int, default=10)
    ap.add_argument("--out", required=True, help="결과 JSON 경로")
    args = ap.parse_args()

    import yaml
    from gplearn_asb.config import Config, DEFAULT_CONFIG_PATH

    with open(DEFAULT_CONFIG_PATH) as fh:
        base = yaml.safe_load(fh) or {}
    cfg = Config({
        "dataset": base.get("dataset", {}),
        "market": args.market,
        "search": {"start_date": args.start, "end_date": args.end},
        # tail exclusion ON: validation 창 밖 데이터를 1일도 쓰지 않음
        "label": {"horizon": 1, "tail_exclusion": True},
        "gp": {"fitness_metric": "fb_fitness", "static_gate": True},
        "constraint": {"mode": "strict_penalty"},
        "backtest": {"transaction_cost_rate": 0.0015,
                     "long_short_quantile": 0.2},
    })

    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    import qlib
    qlib.init = lambda *a, **k: None

    import pandas as pd
    from gplearn_asb.evaluator import MiningEvaluator
    from gplearn_asb.validation_scorer import score_pool

    pool = pd.read_csv(args.pool)
    evaluator = MiningEvaluator(cfg)
    res = score_pool(evaluator,
                     list(pool["formula"]),
                     list(pool.get("signed_train_IC", [float("nan")] * len(pool))),
                     pool_size=args.pool_size)
    res["pool_csv_path"] = os.path.abspath(args.pool)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "signs"},
                     indent=2, default=str))
    return 0 if res["integrity_pass"] and res["failure_reason"] is None else 1


if __name__ == "__main__":
    sys.exit(main())
