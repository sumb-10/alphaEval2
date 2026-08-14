"""AlphaSearchBench configuration.

YAML 파일 → 중첩 dict → 점표기 접근이 가능한 Config 객체.
framework default(configs/default.yaml)는 특정 연구 split을 hard-code하지
않는다 — splits는 null이며, 실제 실험 split은 example/experiment config가
지정한다. 필수값 미지정 시 명확한 에러를 낸다.
"""
from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional

import yaml

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(_PKG_ROOT, "configs", "default.yaml")


class ConfigError(ValueError):
    pass


class Config:
    """중첩 dict 래퍼. cfg["a.b.c"] / cfg.get("a.b.c", default) / cfg.require("a.b")."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    # ---- 접근 ----
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, dotted: str) -> Any:
        sentinel = object()
        v = self.get(dotted, sentinel)
        if v is sentinel:
            raise ConfigError(f"config key not found: {dotted!r}")
        return v

    def require(self, dotted: str) -> Any:
        v = self.get(dotted, None)
        if v is None:
            raise ConfigError(
                f"required config key {dotted!r} is not set. "
                f"framework default.yaml은 연구 split 등을 지정하지 않습니다 — "
                f"experiment config(예: configs/examples/csi_example.yaml)에서 지정하세요."
            )
        return v

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    # ---- 로딩 ----
    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = Config._deep_merge(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out

    @classmethod
    def load(cls, path: Optional[str] = None,
             overrides: Optional[Dict[str, Any]] = None) -> "Config":
        """default.yaml을 베이스로, path의 yaml을 deep-merge해서 로드."""
        with open(DEFAULT_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        if path:
            with open(path) as f:
                user = yaml.safe_load(f) or {}
            data = cls._deep_merge(data, user)
        if overrides:
            data = cls._deep_merge(data, overrides)
        return cls(data)

    # ---- 파생 편의 ----
    def splits(self) -> Dict[str, List[str]]:
        """{'train': [start, end], 'valid': [...], 'test': [...]} — 전부 필수."""
        out = {}
        for name in ("train", "valid", "test"):
            rng = self.require(f"splits.{name}")
            if (not isinstance(rng, (list, tuple))) or len(rng) != 2:
                raise ConfigError(f"splits.{name} must be [start, end], got {rng!r}")
            out[name] = [str(rng[0]), str(rng[1])]
        return out
