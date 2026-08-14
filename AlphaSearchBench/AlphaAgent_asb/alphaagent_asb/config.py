"""AlphaAgent_asb config 로더 — gplearn_asb.config 패턴 (default 경로만 교체)."""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                 # AlphaSearchBench/AlphaAgent_asb
_ASB_ROOT = os.path.dirname(_PKG_ROOT)             # AlphaSearchBench
_REPO_ROOT = os.path.dirname(_ASB_ROOT)            # AlphaEval
for _p in (_ASB_ROOT, os.path.join(_ASB_ROOT, "gplearn_asb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from alphasearchbench.config import Config, ConfigError  # noqa: E402

DEFAULT_CONFIG_PATH = os.path.join(_PKG_ROOT, "configs", "default.yaml")


def normalize_choice(v: Any, allowed, what: str) -> str:
    if v is False:      # YAML off → False 함정
        v = "off"
    v = str(v)
    if v not in allowed:
        raise ConfigError(f"{what} must be one of {allowed}, got {v!r}")
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
