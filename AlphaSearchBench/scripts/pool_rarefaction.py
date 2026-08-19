"""[ASB-P1.0 §5] pool 크기 정규화 — rarefaction (무작위 부분표본).

pool마다 크기 k의 무작위 부분집합을 R회 추출해 Performance@k의 평균·분산
곡선을 얻는다. 품질 기반 선택이 개입하지 않는 순수 크기 통제이며, QD
coverage의 rarefaction(qd/grid.py)과 동일한 방법론의 backtest 확장이다.

부분표본 backtest는 arm config 1개(기본: Track A LS-Q, 유비용)에서 수행한다 —
크기 효과 측정이 목적이므로 구성 격자 전체를 돌릴 필요가 없다.

사용:
  python scripts/pool_rarefaction.py --config configs/examples/csi800_trackA_lsq_c15.yaml \
      --pools "gplearn_asb/out/pilot_csi800_*/metrics/final_pool_pilot_csi800_*.csv" \
      --k 5 10 20 --repeats 100 --seed 20260818 --tag rare_v1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

import numpy as np
import pandas as pd

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ASB_ROOT not in sys.path:
    sys.path.insert(0, _ASB_ROOT)

from scripts.protocol_sweep import discover_pools, _abs, _method_label, _seed_of  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--pools", nargs="+", required=True)
    ap.add_argument("--k", nargs="+", type=int, default=[10])
    ap.add_argument("--repeats", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--split", default="test")
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()

    from alphasearchbench.config import Config
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    from alphasearchbench.data.signal_context import SignalContext
    from alphasearchbench.outputs.writer import OutputWriter
    from alphasearchbench.runner import EvaluationRun
    from alphasearchbench.backtest.simple import SimpleBacktestEvaluator

    cfg = Config.load(_abs(args.config))
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    ctx = SignalContext(cfg)
    pools = discover_pools(args.pools)
    assert pools, "pool 없음"
    out_root = os.path.join(_ASB_ROOT, "out", "rarefaction", args.tag)
    writer = OutputWriter(out_root)
    rows: List[dict] = []
    t0 = time.perf_counter()

    for pool in pools:
        rid, path = pool["run_id"], pool["path"]
        run = EvaluationRun(cfg, path, method=_method_label(rid),
                            seed_id=_seed_of(rid),
                            out_root=os.path.join(out_root, "_scratch"), ctx=ctx)
        if not run.unique_formulas:
            continue
        _v, reports = run.run_validity(split=args.split)
        gated = [f for f in run.unique_formulas if reports[f].passes_gate]
        bt = SimpleBacktestEvaluator(ctx, cfg)
        rng = np.random.default_rng(args.seed)
        for k in args.k:
            if len(gated) < k:
                rows.append({"run_id": rid, "k": k, "status": "pool_smaller_than_k",
                             "n_gated": len(gated)})
                continue
            sharpes, annrets = [], []
            for _ in range(args.repeats):
                sub = list(rng.choice(gated, size=k, replace=False))
                # combiner 정책 준수: 부분집합에도 동일 가중 규칙 적용
                run_sub_f, run_sub_w, _src = run.pool_weights(sub)
                if not run_sub_f:
                    continue
                m, _d = bt.evaluate_pool(run_sub_f, run_sub_w, split=args.split,
                                         pool_id=f"{rid}@k{k}")
                sharpes.append(m["Sharpe"])
                annrets.append(m["AnnRet_arith"])
            sh = np.array(sharpes, dtype=float)
            rows.append({"run_id": rid, "k": k, "status": "ok",
                         "repeats_done": int(len(sh)), "n_gated": len(gated),
                         "sharpe_mean": float(np.nanmean(sh)),
                         "sharpe_std": float(np.nanstd(sh, ddof=1)) if len(sh) > 1 else np.nan,
                         "sharpe_q25": float(np.nanquantile(sh, 0.25)),
                         "sharpe_q75": float(np.nanquantile(sh, 0.75)),
                         "pdr_at_k": float(np.nanmean(sh > 0)),
                         "annret_mean": float(np.nanmean(annrets))})
        print(f"[rarefaction] {rid} done ({time.perf_counter()-t0:.0f}s)")

    df = pd.DataFrame(rows)
    writer.write_table(df, "rarefaction_curves")
    with open(writer.manifest_path(f"rarefaction_{args.tag}.json"), "w") as fh:
        json.dump({"tag": args.tag, "config": args.config, "k": args.k,
                   "repeats": args.repeats, "seed": args.seed,
                   "split": args.split,
                   "protocol_version": cfg.get("protocol.version"),
                   "combiner": cfg.get("backtest.combiner", "raw_equal"),
                   "pools": pools}, fh, indent=2, default=str)
    pd.set_option("display.width", 220)
    ok = df[df["status"] == "ok"]
    if len(ok):
        print(ok[["run_id", "k", "sharpe_mean", "sharpe_std", "pdr_at_k",
                  "n_gated"]].to_string(index=False,
                                        float_format=lambda x: f"{x:+.3f}"))
    print(f"→ {out_root} ({time.perf_counter()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
