"""gplearn_asb config 로더 — ASB Config(deep-merge) 재사용, default 경로만 교체."""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                 # AlphaSearchBench/gplearn_asb
_ASB_ROOT = os.path.dirname(_PKG_ROOT)             # AlphaSearchBench
_REPO_ROOT = os.path.dirname(_ASB_ROOT)            # AlphaEval
if _ASB_ROOT not in sys.path:
    sys.path.insert(0, _ASB_ROOT)

from alphasearchbench.config import Config, ConfigError  # noqa: E402

DEFAULT_CONFIG_PATH = os.path.join(_PKG_ROOT, "configs", "default.yaml")


def normalize_mode(v: Any) -> str:
    """YAML의 `off`(→False) 함정 방어 + 모드 검증."""
    from . import CONSTRAINT_MODES
    if v is False:
        v = "off"
    v = str(v)
    if v not in CONSTRAINT_MODES:
        raise ConfigError(f"constraint.mode must be one of {CONSTRAINT_MODES}, got {v!r}")
    return v


# [v2] public 스키마 화이트리스트 — Vanilla_GP_v2.md §4.
# 결과를 바꾸는 값 + 명시-고정 spec만 허용. legacy 키(constraint.*, gp.hof_mode,
# gp.stopping_criteria, gp.fitness_metric, gp.generations 등)는 존재 자체가 에러.
V2_SCHEMA = {
    "profile": None,
    "market": None,
    "search": {"start_date", "end_date"},
    "label": {"horizon"},
    "budget": {"candidates"},
    "gp": {"population_size", "max_program_length", "max_program_depth"},
    "pool": {"size"},
    "fitness": {"metric", "transaction_cost_rate", "long_short_quantile",
                "net_sharpe_min_traded_days", "net_sharpe_min_abs_ic"},
    "validity": {"min_mean_daily_coverage_ratio", "min_median_daily_n_valid",
                 "min_valid_day_ratio"},
    "seed": None,
    "run_id": None,
    "output": {"root"},
    "dataset": {"provider_uri", "region", "qlib_kernels", "warmup_start",
                "right_buffer_days"},
}
V2_FITNESS_METRICS = ("fb_fitness", "abs_ic", "ic_tstat", "net_sharpe")


def validate_v2_schema(data: Dict[str, Any], source: str = "config") -> None:
    """v2 실험 파일(dict, merge 전)의 화이트리스트 검증. 위반 시 ConfigError."""
    errors = []
    for top, val in data.items():
        if top not in V2_SCHEMA:
            errors.append(f"금지/미지원 최상위 키: {top!r}")
            continue
        allowed = V2_SCHEMA[top]
        if allowed is None:
            continue
        if not isinstance(val, dict):
            errors.append(f"{top}: 블록(dict)이어야 합니다")
            continue
        for sub in val:
            if sub not in allowed:
                errors.append(f"금지/미지원 키: {top}.{sub}")
    metric = (data.get("fitness") or {}).get("metric")
    if metric is not None and metric not in V2_FITNESS_METRICS:
        errors.append(f"fitness.metric은 {V2_FITNESS_METRICS} 중 하나: {metric!r}")
    if errors:
        raise ConfigError(
            "[vanilla_v2] config 스키마 위반 — legacy 키는 v2에서 사용할 수 없습니다 "
            "(configs/LEGACY_INDEX.md 참조):\n  " + "\n  ".join(errors)
            + f"\n  (파일: {source})")


def derive_v2_generations(candidates: int, population_size: int) -> int:
    """generations = budget // population. 나머지는 명시적 에러 (예산 왜곡 금지)."""
    candidates, population_size = int(candidates), int(population_size)
    if population_size <= 0 or candidates <= 0:
        raise ConfigError("budget.candidates와 gp.population_size는 양수여야 합니다")
    if candidates % population_size != 0:
        raise ConfigError(
            f"budget.candidates({candidates})가 population_size({population_size})로 "
            f"나누어떨어지지 않습니다 — generations 파생 불가 (나머지 "
            f"{candidates % population_size}). 예산 또는 population을 조정하세요.")
    return candidates // population_size


def load_config(path: Optional[str] = None,
                overrides: Optional[Dict[str, Any]] = None) -> Config:
    with open(DEFAULT_CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    if path:
        with open(path) as f:
            data = Config._deep_merge(data, yaml.safe_load(f) or {})
    if overrides:
        data = Config._deep_merge(data, overrides)
    return Config(data)


def resolve_paths() -> Dict[str, str]:
    return {"pkg_root": _PKG_ROOT, "asb_root": _ASB_ROOT, "repo_root": _REPO_ROOT}
