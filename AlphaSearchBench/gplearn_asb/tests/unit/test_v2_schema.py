"""unit — [v2] config 스키마 화이트리스트·generations 파생 (qlib 불필요)."""
import os
import sys

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
for _p in (_PKG_ROOT, _ASB_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gplearn_asb.config import (ConfigError, derive_v2_generations,   # noqa: E402
                                validate_v2_schema)

VALID = {
    "profile": "vanilla_v2-draft",
    "market": "csi800",
    "search": {"start_date": "2010-01-01", "end_date": "2019-12-31"},
    "label": {"horizon": 1},
    "budget": {"candidates": 5000},
    "gp": {"population_size": 1000, "max_program_length": None},
    "pool": {"size": 10},
    "fitness": {"metric": "fb_fitness", "transaction_cost_rate": 0.0015,
                "long_short_quantile": 0.2},
    "validity": {"min_mean_daily_coverage_ratio": 0.05,
                 "min_median_daily_n_valid": 30,
                 "min_valid_day_ratio": 0.90},
    "seed": 42,
}


def test_valid_schema_passes():
    validate_v2_schema(dict(VALID))


@pytest.mark.parametrize("bad_top", ["constraint", "backtest", "qd"])
def test_forbidden_top_level_keys(bad_top):
    d = dict(VALID)
    d[bad_top] = {"mode": "off"}
    with pytest.raises(ConfigError):
        validate_v2_schema(d)


@pytest.mark.parametrize("blk,key", [
    ("gp", "hof_mode"), ("gp", "stopping_criteria"), ("gp", "fitness_metric"),
    ("gp", "generations"), ("gp", "static_gate"), ("gp", "hall_of_fame"),
])
def test_forbidden_legacy_gp_keys(blk, key):
    d = dict(VALID)
    d[blk] = dict(d[blk])
    d[blk][key] = 1
    with pytest.raises(ConfigError):
        validate_v2_schema(d)


def test_unknown_fitness_metric_rejected():
    d = dict(VALID)
    d["fitness"] = dict(d["fitness"], metric="sharpe_of_sharpes")
    with pytest.raises(ConfigError):
        validate_v2_schema(d)


def test_generations_derivation():
    assert derive_v2_generations(5000, 1000) == 5
    assert derive_v2_generations(60, 30) == 2


def test_generations_remainder_is_explicit_error():
    with pytest.raises(ConfigError):
        derive_v2_generations(5000, 999)
    with pytest.raises(ConfigError):
        derive_v2_generations(0, 1000)
