"""miner result / weights 로더 (표준 스키마 → DataFrame/list)."""
from __future__ import annotations

import json
import os
from typing import List, Optional

import pandas as pd

from .schemas import RESULT_REQUIRED, SchemaError, validate_columns


def load_result(path: str, method: Optional[str] = None,
                seed_id: Optional[str] = None) -> pd.DataFrame:
    """miner 결과 파일 로드. 반환 컬럼: formula(+선택 컬럼) + method/seed 주입."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext in (".pkl", ".pickle"):
        df = pd.read_pickle(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise SchemaError(f"지원하지 않는 result 형식: {ext}")
    validate_columns(df, RESULT_REQUIRED, "miner result")
    df = df.copy()
    df["formula"] = df["formula"].astype(str)
    if method is not None:
        df["method"] = method
    elif "method" not in df.columns:
        df["method"] = os.path.splitext(os.path.basename(path))[0]
    if seed_id is not None:
        df["seed"] = seed_id
    elif "seed" not in df.columns:
        df["seed"] = "unknown"
    return df


def load_weights(path: str, n_expected: Optional[int] = None) -> List[float]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path) as f:
            w = json.load(f)
        if isinstance(w, dict):
            w = w.get("weights", None)
            if w is None:
                raise SchemaError("weights json에 'weights' 키가 없습니다")
    elif ext == ".csv":
        w = pd.read_csv(path, header=None).iloc[:, 0].tolist()
    else:
        raise SchemaError(f"지원하지 않는 weights 형식: {ext}")
    w = [float(x) for x in w]
    if n_expected is not None and len(w) != n_expected:
        raise SchemaError(f"weights 길이 {len(w)} ≠ formula 수 {n_expected}")
    return w
