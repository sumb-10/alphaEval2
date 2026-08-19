"""unit — [ASB-P1.0] combiner 정책(pool_weights)과 family 프로파일 집계."""
import math
import os
import sys
import types

import numpy as np
import pandas as pd

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ASB_ROOT not in sys.path:
    sys.path.insert(0, _ASB_ROOT)

from alphasearchbench.runner import EvaluationRun                      # noqa: E402


def _stub(combiner, tau=0.0, sics=None):
    """EvaluationRun.pool_weights를 위한 최소 스텁."""
    sics = sics or {}
    st = types.SimpleNamespace(
        combiner=combiner, sign_threshold=tau, _no_direction=[],
        formulas=list(sics), weights=[1.0 / max(len(sics), 1)] * len(sics),
        weights_source="equal_default",
        train_sign=lambda f: (sics[f], 1 if (sics[f] or 0) >= 0 else -1, False))
    return st


def test_raw_equal_passthrough():
    st = _stub("raw_equal", sics={"a": 0.02, "b": -0.05})
    f, w, src = EvaluationRun.pool_weights(st, ["a", "b"])
    assert f == ["a", "b"] and src == "equal_default"
    assert np.allclose(w, [0.5, 0.5])                  # 부호 미적용 (label-free)


def test_signed_equal_orients_and_renormalizes():
    st = _stub("train_signed_equal", sics={"a": 0.02, "b": -0.05, "c": 0.01})
    f, w, src = EvaluationRun.pool_weights(st, ["a", "b", "c"])
    assert src == "train_signed_equal" and f == ["a", "b", "c"]
    assert np.allclose(w, [1/3, -1/3, 1/3])            # w_i = sign/n'


def test_signed_equal_tau_excludes_weak_direction():
    st = _stub("train_signed_equal", tau=0.015,
               sics={"a": 0.02, "b": -0.05, "c": 0.01, "d": float("nan")})
    f, w, _ = EvaluationRun.pool_weights(st, ["a", "b", "c", "d"])
    assert f == ["a", "b"]                             # |IC|<=τ, NaN 제외
    assert np.allclose(w, [0.5, -0.5])                 # n' = 2로 재정규화
    assert st._no_direction == ["c", "d"]              # 조용한 유실 금지


def test_signed_equal_all_excluded_returns_empty():
    st = _stub("train_signed_equal", tau=1.0, sics={"a": 0.02})
    f, w, _ = EvaluationRun.pool_weights(st, ["a"])
    assert f == [] and w == []


# ---------------------------------------------------------------- 프로파일
def _mk(arm_rows):
    return pd.DataFrame(arm_rows)


def test_ls_profile_family_scoped():
    from scripts.deployment_profile import ls_profile
    g = _mk([
        {"status": "ok", "Sharpe": 1.0, "AnnRet_arith": 0.10, "MDD": 0.1,
         "annualized_turnover_oneway": 5.0, "cost_rate": 0.0015},
        {"status": "ok", "Sharpe": -0.5, "AnnRet_arith": -0.05, "MDD": 0.3,
         "annualized_turnover_oneway": 6.0, "cost_rate": 0.0015},
        {"status": "ok", "Sharpe": 1.4, "AnnRet_arith": 0.12, "MDD": 0.1,
         "annualized_turnover_oneway": 5.0, "cost_rate": 0.0},
        {"status": "ok", "Sharpe": 0.2, "AnnRet_arith": 0.02, "MDD": 0.2,
         "annualized_turnover_oneway": 6.0, "cost_rate": 0.0},
    ])
    p = ls_profile(g)
    assert p["n_ok"] == 4
    assert math.isclose(p["median_sharpe"], np.median([1.0, -0.5, 1.4, 0.2]))
    assert math.isclose(p["pdr"], 0.75)                # Sharpe>0 3/4
    assert math.isclose(p["worst_sharpe"], -0.5)
    # gross→net: 0bps median(0.8) − 유비용 median(0.25) = 0.55
    assert math.isclose(p["gross_to_net_sharpe_drop"], 0.8 - 0.25)


def test_anchor_profile_separate_metrics():
    from scripts.deployment_profile import anchor_profile
    g = _mk([{"status": "ok", "AnnRet_excess": 0.05, "IR": 0.8,
              "MDD_excess": 0.1, "AnnRet_arith": 0.02,
              "annualized_turnover_oneway": 20.0}])
    p = anchor_profile(g)
    assert math.isclose(p["excess_ar"], 0.05) and math.isclose(p["ir"], 0.8)
    assert "median_sharpe" not in p                    # family 간 지표 혼합 금지


def test_profile_handles_empty():
    from scripts.deployment_profile import ls_profile
    p = ls_profile(_mk([{"status": "error:x", "Sharpe": np.nan,
                         "AnnRet_arith": np.nan, "MDD": np.nan,
                         "annualized_turnover_oneway": np.nan,
                         "cost_rate": 0.0015}]))
    assert p["n_ok"] == 0 and math.isnan(p["median_sharpe"])
