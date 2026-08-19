"""Provenance manifest — 실험 재현에 필요한 모든 정의/버전/설정 기록."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, Optional


def _git_commit(repo_dir: str) -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir,
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() or None
    except Exception:
        return None


def _versions() -> Dict[str, str]:
    out = {"python": sys.version.split()[0]}
    for m in ("qlib", "numpy", "pandas", "scipy", "sklearn", "pyarrow", "joblib"):
        try:
            mod = __import__(m)
            out[m] = getattr(mod, "__version__", "?")
        except ImportError:
            out[m] = "missing"
    return out


def build_manifest(cfg, ctx, run_info: Dict) -> Dict:
    """cfg: Config, ctx: SignalContext, run_info: method/seed/counts 등."""
    eng = ctx.engine
    dataset_version = (f"{cfg.get('dataset.provider_uri')}"
                       f"|days={len(eng.dates)}|insts={len(eng.columns)}"
                       f"|{eng.dates[0].date()}..{eng.dates[-1].date()}")
    manifest = {
        "alphasearchbench_version": __import__("alphasearchbench").__version__,
        # [ASB-P1.0 §13] 배치 프로토콜 버전 — 구성 변경은 버전 증가를 동반한다
        "protocol_version": cfg.get("protocol.version", "unversioned"),
        "git_commit": _git_commit(os.path.dirname(os.path.abspath(__file__))),
        "versions": _versions(),
        "dataset": {
            "provider_uri": cfg.get("dataset.provider_uri"),
            "dataset_version": dataset_version,
            "warmup_start": eng.warmup_start,
        },
        "market": ctx.market,
        "benchmark": ctx.benchmark_ticker,
        "splits": ctx.splits_cfg,
        "label": {
            "definition": "close_t -> close_(t+1)  (Ref($close,-1)/$close - 1)",
            "horizon": cfg.get("label.horizon", 1),
            "label_uses_post_end_price": bool(cfg.get("label.uses_post_end_price", True)),
        },
        "execution": {
            "backtest_mode": cfg.get("backtest.mode"),
            "execution": cfg.get("backtest.execution"),
            "same_close_is_legacy_optimistic": True,
            "top_fraction": cfg.get("backtest.top_fraction"),
            "bottom_fraction": cfg.get("backtest.bottom_fraction"),
            "transaction_cost_rate": cfg.get("backtest.transaction_cost_rate"),
            "cost_turnover_definition": cfg.get("backtest.cost_turnover_definition"),
            "mdd_convention": "positive_magnitude",
            "annualization": {"AnnRet_arith": "mean*252", "CAGR": "(1+cum)^(252/n)-1"},
        },
        "train_sign_rule": cfg.get("signal.train_sign_rule"),
        "validity": {
            "mode": cfg.get("validity.mode"),
            "thresholds": {
                "min_valid_day_ratio": cfg.get("validity.min_valid_day_ratio"),
                "min_mean_daily_coverage_ratio": cfg.get("validity.min_mean_daily_coverage_ratio"),
                "min_median_daily_n_valid": cfg.get("validity.min_median_daily_n_valid"),
            },
            "hard_invalid_rules": ["formula_eval_failed", "all_nonfinite",
                                   "no_correlatable_day", "zero_ic_observations"],
        },
        "qd": {
            "descriptor_set": cfg.get("qd.descriptor_set"),
            "horizons": cfg.get("qd.horizons"),
            "contrast_eps": cfg.get("qd.contrast_eps"),
            "contrast_denom_threshold": cfg.get("qd.contrast_denom_threshold"),
            "horizon_reducer": cfg.get("qd.horizon_reducer"),
            "regime_thresholds": ctx.regime,
            "liquidity": cfg.get("qd.liquidity"),
            "projection": cfg.get("qd.projection"),
            "grid": cfg.get("qd.grid"),
            "quality": cfg.get("qd.quality"),
            "dedup": cfg.get("qd.dedup"),
        },
        "pfs": {
            "enabled": cfg.get("pfs.enabled"),
            "mode": cfg.get("pfs.mode"),
            "sigma_def": cfg.get("pfs.sigma_def"),
            "k_draws": cfg.get("pfs.k_draws"),
            "seed": cfg.get("pfs.seed"),
            "student_t_dof": cfg.get("pfs.student_t_dof"),
        },
        "seed": cfg.get("seed"),
        "run": run_info,
        "created_at": datetime.now().isoformat(),
    }
    return manifest


def save_manifest(manifest: Dict, path: str) -> str:
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return path
