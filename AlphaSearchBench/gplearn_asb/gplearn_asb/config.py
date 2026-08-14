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
