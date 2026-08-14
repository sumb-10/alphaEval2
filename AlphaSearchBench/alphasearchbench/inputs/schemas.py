"""표준 입력 스키마 — AlphaSearchBench core의 유일한 miner 접점.

core는 아래 스키마만 알면 되고, 특정 miner(gplearn/AutoAlpha/LLM 등) 내부
구현에 의존하지 않는다. miner별 어댑터는 instrumentation/(optional)에 둔다.

[miner result]  (csv/pkl DataFrame)
  필수: formula (str)
  선택: IC(레거시 |IC|), signed_train_IC, train_sign, method, seed

[weights]       (json list | csv 1열 | DataFrame)

[trajectory]    (jsonl — 한 줄 = 후보 하나)
  필수: run_id, method, seed, generation, idx_in_population,
        formula, raw_fitness
  선택: signed_train_IC, operation, parent_idx, donor_idx,
        program_length, program_depth, memo_hit
"""
from __future__ import annotations

from typing import Dict, List

RESULT_REQUIRED = ["formula"]
RESULT_OPTIONAL = ["IC", "signed_train_IC", "train_sign", "method", "seed"]

TRAJECTORY_REQUIRED = ["run_id", "method", "seed", "generation",
                       "idx_in_population", "formula", "raw_fitness"]
TRAJECTORY_OPTIONAL = ["signed_train_IC", "operation", "parent_idx", "donor_idx",
                       "program_length", "program_depth", "memo_hit"]


class SchemaError(ValueError):
    pass


def validate_columns(df, required: List[str], what: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"{what}에 필수 컬럼이 없습니다: {missing} "
                          f"(현재: {list(df.columns)})")
