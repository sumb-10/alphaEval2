"""[WS-A / E3] 프로토콜 4-arm 백테스트 스윕 — 같은 pool을 여러 평가 프로토콜로.

full `evaluate`(validity+oos+qd+backtest; allcand 시 4~7h) 대신 **validity 게이트
+ backtest만** 반복한다. 게이트·train_sign·pool 가중·비용 회계는 공식 경로인
`EvaluationRun.run_validity/run_backtest`를 그대로 호출하므로 재구현이 없다.
arm(=config)당 `SignalContext`를 1회만 만들고 `ctx=`로 주입해 패널·신호 캐시를
모든 pool이 공유한다.

산출:
  out/protocol_sweep/<tag>/metrics/protocol_sweep_pool.parquet
  out/protocol_sweep/<tag>/metrics/protocol_sweep_factor.parquet  (--also-factors)
  out/protocol_sweep/<tag>/manifests/sweep_<tag>.json

사용:
  python scripts/protocol_sweep.py --tag ws_a_e3 \
      --arms A1=configs/examples/csi800_ref.yaml \
             A2=configs/examples/csi800_ref_lowturn.yaml \
             A3=configs/examples/csi800_ref_qlib.yaml \
             A4=configs/examples/csi800_ref_legacy.yaml \
      --pools "gplearn_asb/out/pilot_csi800_*/metrics/final_pool_pilot_csi800_*.csv" \
              "AlphaAgent_asb/out/*/metrics/final_pool_*.csv"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from glob import glob
from typing import Dict, List

import pandas as pd

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ASB_ROOT not in sys.path:
    sys.path.insert(0, _ASB_ROOT)


def _abs(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(_ASB_ROOT, p)


def discover_pools(patterns: List[str]) -> List[Dict[str, str]]:
    """pool CSV 목록 → [{run_id, path, method}]. run_id는 파일명에서 유도."""
    found: Dict[str, str] = {}
    for pat in patterns:
        for p in sorted(glob(_abs(pat))):
            base = os.path.basename(p)
            if not (base.startswith("final_pool_") and base.endswith(".csv")):
                continue
            found.setdefault(base[len("final_pool_"):-len(".csv")], p)
    return [{"run_id": r, "path": found[r]} for r in sorted(found)]


def _method_label(run_id: str) -> str:
    """run_id → method 라벨 (마이닝 프레임워크 구분 — 보고서 3-A용)."""
    if run_id.startswith("alphaagent"):
        return "alphaagent_asb"
    return "gplearn_asb"


def _seed_of(run_id: str) -> str:
    import re
    m = re.findall(r"_(\d+)(?:_|$)", run_id)
    return m[-1] if m else "0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--arms", nargs="+", required=True, help="NAME=config.yaml")
    ap.add_argument("--pools", nargs="+", required=True, help="glob 패턴들")
    ap.add_argument("--split", default="test")
    ap.add_argument("--also-factors", action="store_true",
                    help="pool 외 개별 factor도 평가(느림, 진단용)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from alphasearchbench.config import Config
    from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
    from alphasearchbench.data.signal_context import SignalContext
    from alphasearchbench.outputs.writer import OutputWriter
    from alphasearchbench.runner import EvaluationRun

    arms = []
    for spec in args.arms:
        assert "=" in spec, f"--arms는 NAME=config.yaml[#key=val,...] 형식: {spec!r}"
        name, rest = spec.split("=", 1)
        overrides = {}
        if "#" in rest:
            rest, ov = rest.split("#", 1)
            for kv in ov.split(","):
                k, v = kv.split("=", 1)
                cur = overrides
                keys = k.split(".")
                for kk in keys[:-1]:
                    cur = cur.setdefault(kk, {})
                try:
                    cur[keys[-1]] = float(v) if "." in v or v.isdigit() else v
                except ValueError:
                    cur[keys[-1]] = v
        arms.append((name, _abs(rest), overrides))
    pools = discover_pools(args.pools)
    assert pools, f"pool CSV를 찾지 못했습니다: {args.pools}"
    print(f"[sweep] arms={[a[0] for a in arms]} pools={len(pools)} split={args.split}")

    out_root = args.out or os.path.join(_ASB_ROOT, "out", "protocol_sweep", args.tag)
    writer = OutputWriter(out_root)
    pool_rows, factor_rows, arm_meta = [], [], []
    t_all = time.perf_counter()
    qlib_ready = False

    for arm_name, cfg_path, overrides in arms:
        cfg = Config.load(cfg_path)
        if overrides:
            cfg = Config(Config._deep_merge(cfg.to_dict()
                         if hasattr(cfg, "to_dict") else cfg._data, overrides))
        if not qlib_ready:
            bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                           cfg["dataset.qlib_kernels"])
            qlib_ready = True
        t0 = time.perf_counter()
        ctx = SignalContext(cfg)                     # arm당 1회 — 모든 pool이 공유
        print(f"[sweep][{arm_name}] context {time.perf_counter()-t0:.1f}s "
              f"mode={cfg.get('backtest.mode')} splits={cfg.get('splits')}")

        for i, pool in enumerate(pools, 1):
            rid, path = pool["run_id"], pool["path"]
            base = {"arm": arm_name, "run_id": rid,
                    "mining_framework": _method_label(rid)}
            try:
                run = EvaluationRun(cfg, path, method=_method_label(rid),
                                    seed_id=_seed_of(rid),
                                    out_root=os.path.join(out_root, "_scratch"),
                                    ctx=ctx)
                if not run.unique_formulas:
                    pool_rows.append({**base, "status": "empty_pool", "n_factors": 0})
                    continue
                _vdf, reports = run.run_validity(split=args.split)
                f_df, p_df, _daily = run.run_backtest(reports, split=args.split)
            except Exception as exc:                              # noqa: BLE001
                pool_rows.append({**base,
                                  "status": f"error:{type(exc).__name__}:{exc}"[:220]})
                continue

            n_gated = int(sum(1 for f in run.unique_formulas
                              if reports[f].passes_gate))
            if p_df.empty:
                pool_rows.append({**base, "status": "no_pool_row",
                                  "n_factors": len(run.unique_formulas),
                                  "n_gated": n_gated})
            else:
                row = dict(p_df.iloc[0])
                row.update({**base, "status": "ok",
                            "n_factors_input": len(run.unique_formulas),
                            "n_gated": n_gated,
                            "n_gated_out": len(run.unique_formulas) - n_gated})
                pool_rows.append(row)
            if args.also_factors and not f_df.empty:
                fd = f_df.copy()
                for k, v in base.items():
                    fd[k] = v
                factor_rows.append(fd)
            if i % 5 == 0 or i == len(pools):
                print(f"[sweep][{arm_name}] {i}/{len(pools)} "
                      f"({time.perf_counter()-t0:.0f}s)")

        arm_meta.append({"arm": arm_name, "config": cfg_path,
                         "overrides": overrides,
                         "protocol_version": cfg.get("protocol.version"),
                         "combiner": cfg.get("backtest.combiner", "raw_equal"),
                         "backtest": cfg.get("backtest"),
                         "splits": cfg.get("splits"), "market": cfg.get("market"),
                         "validity_thresholds": {
                             k: cfg.get(f"validity.{k}") for k in
                             ("min_valid_day_ratio", "min_mean_daily_coverage_ratio",
                              "min_median_daily_n_valid")},
                         "seconds": time.perf_counter() - t0})

    pool_df = pd.DataFrame(pool_rows)
    writer.write_table(pool_df, "protocol_sweep_pool")
    if factor_rows:
        writer.write_table(pd.concat(factor_rows, ignore_index=True),
                           "protocol_sweep_factor")
    manifest = {"tag": args.tag, "split": args.split,
                "protocol_version": (arm_meta[0].get("protocol_version")
                                     if arm_meta else None),
                "arms": arm_meta,
                "pools": pools, "n_rows": int(len(pool_df)),
                "wall_seconds": time.perf_counter() - t_all}
    with open(writer.manifest_path(f"sweep_{args.tag}.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    cols = [c for c in ("arm", "run_id", "status", "Sharpe", "AnnRet_arith",
                        "AnnRet_excess", "IR", "MDD",
                        "annualized_turnover_oneway", "n_gated") if c in pool_df.columns]
    pd.set_option("display.width", 250)
    print(pool_df[cols].to_string(index=False))
    print(f"[sweep] {len(pool_df)} rows → {out_root} ({time.perf_counter()-t_all:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
