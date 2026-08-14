"""Phase 9 smoke: end-to-end 통합 — 1커맨드 실행 + 산출물 + 결정론.

smoke config(csi300, 2018~2019H2) + formula 5개(정상 4 + 고의 실패 1).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pandas as pd
import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

PY = sys.executable
FORMULAS = [
    "Mean($close, 30)",
    "Std($high, 12)",
    "Div(Mean($close, 30), $volume)",
    "Sub(Std(Div($high, $low), 12), Mean($close, 5))",
    "Bogus($close, 5)",                      # 고의 hard invalid
]

METRIC_FILES = ["validity_factor_metrics", "oos_factor_metrics", "oos_pool_metrics",
                "qd_factor_descriptors", "qd_pool_metrics",
                "backtest_factor_metrics", "backtest_pool_metrics"]


def _run_e2e(out_dir: str, input_csv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "alphasearchbench", "evaluate",
         "--config", os.path.join(ASB_ROOT, "configs", "smoke.yaml"),
         "--input", input_csv, "--method", "smoketest", "--seed-id", "42",
         "--out", out_dir],
        cwd=ASB_ROOT, capture_output=True, text=True, timeout=1800)


@pytest.fixture(scope="module")
def e2e():
    td = tempfile.mkdtemp(prefix="asb_e2e_")
    input_csv = os.path.join(td, "miner_result.csv")
    pd.DataFrame({"formula": FORMULAS}).to_csv(input_csv, index=False)
    out1 = os.path.join(td, "run1")
    out2 = os.path.join(td, "run2")
    r1 = _run_e2e(out1, input_csv)
    r2 = _run_e2e(out2, input_csv)
    return {"td": td, "out1": out1, "out2": out2, "r1": r1, "r2": r2}


def test_e2e_completes(e2e):
    assert e2e["r1"].returncode == 0, e2e["r1"].stderr[-3000:]
    assert e2e["r2"].returncode == 0, e2e["r2"].stderr[-3000:]


def test_all_metric_parquets_created(e2e):
    for name in METRIC_FILES:
        p = os.path.join(e2e["out1"], "metrics", name + ".parquet")
        assert os.path.exists(p), f"missing: {name}"
        df = pd.read_parquet(p)
        assert len(df) > 0, f"empty: {name}"


def test_validity_gate_and_no_silent_fallback(e2e):
    v = pd.read_parquet(os.path.join(e2e["out1"], "metrics",
                                     "validity_factor_metrics.parquet"))
    bogus = v[v["formula"] == "Bogus($close, 5)"].iloc[0]
    assert not bogus["valid"]
    assert str(bogus["invalid_reason"]).startswith("formula_eval_failed:")
    # invalid formula는 OOS에서 지표 없이 사유만
    o = pd.read_parquet(os.path.join(e2e["out1"], "metrics",
                                     "oos_factor_metrics.parquet"))
    bad = o[o["formula"] == "Bogus($close, 5)"].iloc[0]
    assert not bad["valid"] and pd.isna(bad.get("IC"))
    good = o[o["valid"] == True]                                 # noqa: E712
    assert len(good) == 4
    assert good["IC"].notna().all()
    assert set(good["train_sign"]).issubset({-1, 1})


def test_qd_outputs_complete(e2e):
    d = pd.read_parquet(os.path.join(e2e["out1"], "metrics",
                                     "qd_factor_descriptors.parquet"))
    assert len(d) == 4
    for col in ("IC_1d", "IC_5d", "IC_10d", "IC_20d", "horizon",
                "volatility_response", "market_direction_response",
                "liquidity_response", "activation_breadth", "rre_qd",
                "signal_coverage", "signal_weight_turnover", "liquidity_footprint",
                "PCA1", "PCA2", "valid_PCA1", "descriptor_drift_pca",
                "PFS_Gaussian", "PFS_t", "PFS_min"):
        assert col in d.columns, f"missing col: {col}"
    p = pd.read_parquet(os.path.join(e2e["out1"], "metrics",
                                     "qd_pool_metrics.parquet"))
    row = p.iloc[0]
    assert 0 <= row["coverage"] <= 1
    assert row["n_gated_factors"] == 4
    assert "AlphaEval_DE_legacy" in p.columns and "de_common_valid" in p.columns
    assert row["n_common_cells"] > 0


def test_backtest_outputs(e2e):
    b = pd.read_parquet(os.path.join(e2e["out1"], "metrics",
                                     "backtest_factor_metrics.parquet"))
    good = b[b["valid"] == True]                                  # noqa: E712
    assert len(good) == 4
    assert (good["execution"] == "next_open_oo").all()
    assert (good["MDD"] >= 0).all()
    daily = pd.read_parquet(os.path.join(e2e["out1"], "daily",
                                         "backtest_daily.parquet"))
    for col in ("gross_return", "cost", "net_return", "turnover_l1",
                "turnover_oneway", "long_count", "short_count",
                "gross_exposure", "net_exposure", "cumulative_return"):
        assert col in daily.columns


def test_manifest_provenance(e2e):
    mpath = os.path.join(e2e["out1"], "manifests", "run_smoketest_42.json")
    with open(mpath) as f:
        m = json.load(f)
    assert m["market"] == "csi300"
    assert m["benchmark"] == "SH000300"
    assert m["label"]["label_uses_post_end_price"] is True
    assert m["execution"]["execution"] == "next_open_oo"
    assert m["qd"]["regime_thresholds"]["vol_low_threshold"] < \
           m["qd"]["regime_thresholds"]["vol_high_threshold"]
    assert m["run"]["formula_count"] == 5
    assert m["versions"]["qlib"] == "0.9.0"
    # projection artifacts
    pdir = os.path.join(e2e["out1"], "manifests", "qd_projection")
    assert os.path.exists(os.path.join(pdir, "scaler.pkl"))
    assert os.path.exists(os.path.join(pdir, "qd_manifest.json"))


def test_deterministic_rerun(e2e):
    for name in METRIC_FILES:
        a = pd.read_parquet(os.path.join(e2e["out1"], "metrics", name + ".parquet"))
        b = pd.read_parquet(os.path.join(e2e["out2"], "metrics", name + ".parquet"))
        pd.testing.assert_frame_equal(
            a.drop(columns=["grid_bounds"], errors="ignore"),
            b.drop(columns=["grid_bounds"], errors="ignore"),
            check_exact=True)
        if "grid_bounds" in a.columns:
            assert a["grid_bounds"].equals(b["grid_bounds"])
