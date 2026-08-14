"""Fixed PCA projection — 모든 method를 동일 좌표계에 투영.

원칙:
  * fit은 **reference runs의 validation descriptor만** 사용 (test 금지 — leakage)
  * fit 후 scaler/PCA/descriptor 순서/reference 메타를 디스크에 고정
  * 이후 valid/test/new method 전부 동일 transform
  * descriptor에 NaN이 있는 행은 투영 불가 → projected=False로 기록 (drop 아님)
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd


class QDProjection:
    def __init__(self, columns: List[str], n_components: int = 2):
        self.columns = list(columns)
        self.n_components = n_components
        self.scaler = None
        self.pca = None
        self.meta: Dict = {}

    # ------------------------------------------------------------------
    def fit_reference(self, descriptors: pd.DataFrame,
                      reference_meta: Optional[Dict] = None) -> "QDProjection":
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA
        X = descriptors[self.columns].to_numpy(dtype=np.float64)
        ok = np.isfinite(X).all(axis=1)
        if ok.sum() < max(3, self.n_components + 1):
            raise ValueError(
                f"reference descriptor가 부족합니다: finite rows={int(ok.sum())}")
        self.scaler = StandardScaler().fit(X[ok])
        self.pca = PCA(n_components=self.n_components).fit(
            self.scaler.transform(X[ok]))
        self.meta = {
            "columns": self.columns,
            "n_components": self.n_components,
            "n_reference_rows": int(ok.sum()),
            "explained_variance_ratio": [float(v) for v in
                                         self.pca.explained_variance_ratio_],
            **(reference_meta or {}),
        }
        return self

    def transform(self, descriptors: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """(pcs (n×k) — 투영 불가 행은 NaN, projected mask)"""
        if self.scaler is None or self.pca is None:
            raise RuntimeError("projection not fitted/loaded")
        X = descriptors[self.columns].to_numpy(dtype=np.float64)
        ok = np.isfinite(X).all(axis=1)
        out = np.full((len(X), self.n_components), np.nan)
        if ok.any():
            out[ok] = self.pca.transform(self.scaler.transform(X[ok]))
        return out, ok

    def standardized(self, descriptors: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """scaler만 적용한 표준화 raw descriptor 공간 (NN distance용)."""
        X = descriptors[self.columns].to_numpy(dtype=np.float64)
        ok = np.isfinite(X).all(axis=1)
        out = np.full_like(X, np.nan)
        if ok.any():
            out[ok] = self.scaler.transform(X[ok])
        return out, ok

    # ------------------------------------------------------------------
    def save(self, dir_path: str) -> None:
        os.makedirs(dir_path, exist_ok=True)
        joblib.dump(self.scaler, os.path.join(dir_path, "scaler.pkl"))
        joblib.dump(self.pca, os.path.join(dir_path, "pca.pkl"))
        import sklearn
        manifest = dict(self.meta)
        manifest["sklearn_version"] = sklearn.__version__
        with open(os.path.join(dir_path, "qd_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)

    @classmethod
    def load(cls, dir_path: str) -> "QDProjection":
        with open(os.path.join(dir_path, "qd_manifest.json")) as f:
            meta = json.load(f)
        obj = cls(meta["columns"], meta["n_components"])
        obj.scaler = joblib.load(os.path.join(dir_path, "scaler.pkl"))
        obj.pca = joblib.load(os.path.join(dir_path, "pca.pkl"))
        obj.meta = meta
        return obj


def descriptor_diagnostics(descriptors: pd.DataFrame,
                           columns: List[str]) -> Dict[str, pd.DataFrame]:
    """PCA 전 진단: Pearson/Spearman corr, variance, missing ratio."""
    sub = descriptors[columns]
    return {
        "pearson": sub.corr(method="pearson"),
        "spearman": sub.corr(method="spearman"),
        "variance": sub.var().to_frame("variance"),
        "missing_ratio": sub.isna().mean().to_frame("missing_ratio"),
    }
