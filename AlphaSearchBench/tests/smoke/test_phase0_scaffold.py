"""Phase 0 smoke: scaffold / config / CLI / qlib init / universe·필드 조회.

formula 평가는 Phase 1 범위이므로 여기서 다루지 않는다.
실행: (AlphaSearchBench/ 에서)  pytest tests/smoke/test_phase0_scaffold.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ASB_ROOT)

from alphasearchbench.config import Config, ConfigError  # noqa: E402


def test_config_default_loads_and_splits_are_null():
    cfg = Config.load()
    assert cfg.get("market") is None
    assert cfg.get("splits.train") is None
    with pytest.raises(ConfigError):
        cfg.splits()          # framework default는 split을 지정하지 않는다


def test_config_smoke_merge():
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    s = cfg.splits()
    assert s["train"] == ["2018-01-01", "2018-12-31"]
    assert cfg["market"] == "csi300"
    # default에서 상속된 값
    assert cfg["benchmark.map.csi300"] == "SH000300"
    assert cfg["backtest.execution"] == "next_open_oo"


def test_cli_help():
    r = subprocess.run(
        [sys.executable, "-m", "alphasearchbench", "--help"],
        cwd=ASB_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0
    assert "OOS / QD / Backtest" in r.stdout


def test_qlib_init_universe_and_field():
    cfg = Config.load(os.path.join(ASB_ROOT, "configs", "smoke.yaml"))
    from alphasearchbench.data.qlib_bootstrap import (
        bootstrap_qlib, get_calendar, list_instrument_spans, fetch_field,
        get_instruments_config,
    )
    bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                   cfg["dataset.qlib_kernels"])
    cal = get_calendar("2019-01-01", "2019-01-31")
    assert len(cal) > 15                      # 1월 거래일

    spans = list_instrument_spans("csi300", "2019-01-01", "2019-06-30")
    assert len(spans) >= 300                  # 편입 이력 포함 종목 수

    df = fetch_field(get_instruments_config("csi300"), "$close",
                     "2019-01-02", "2019-01-10")
    assert len(df) > 1000                     # ~300종목 × 7거래일
    assert df.columns.tolist() == ["$close"]
