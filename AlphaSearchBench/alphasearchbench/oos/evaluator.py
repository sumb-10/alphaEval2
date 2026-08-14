"""OOS Evaluation Pipeline — signal-level out-of-sample predictive ability.

portfolio rule에 의존하지 않는다. 지표: Mean IC / Mean RankIC / ICIR /
RankICIR (+ *_ann). daily series를 보존해 재집계 가능하게 한다.

sign 규약: evaluate_factor는 train_sign(±1)을 **입력으로만** 받는다 —
이 모듈에는 test 데이터로 방향을 추정하는 경로가 존재하지 않는다.
pool은 frozen weights로 결합한 신호 자체에서 계산한다 (component 평균 아님).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import Config
from ..data.signal_context import SignalContext
from .metrics import daily_ic_series, daily_rank_ic_series, aggregate_ic


class OOSResult:
    def __init__(self, row: Dict, daily: pd.DataFrame):
        self.row = row
        self.daily = daily


class OOSEvaluator:
    def __init__(self, ctx: SignalContext, cfg: Config):
        self.ctx = ctx
        self.cfg = cfg
        self.horizons: List[int] = list(cfg.get("oos.horizons", [1]))
        self.primary_h: int = self.horizons[0]

    # ------------------------------------------------------------------
    def _metrics_for_signal(self, signal: np.ndarray, valid: np.ndarray,
                            split: str, formula_id: str) -> OOSResult:
        sc = self.ctx.split[split]
        row: Dict = {"split": split}
        daily_frames = []
        for k in self.horizons:
            fwd = sc.forward[k]
            ic = daily_ic_series(signal, fwd, valid)
            ric = daily_rank_ic_series(signal, fwd, valid)
            agg_ic, agg_ric = aggregate_ic(ic), aggregate_ic(ric)
            suffix = "" if k == self.primary_h else f"_{k}d"
            row.update({
                f"IC{suffix}": agg_ic["mean"],
                f"RankIC{suffix}": agg_ric["mean"],
                f"ICIR{suffix}": agg_ic["icir"],
                f"RankICIR{suffix}": agg_ric["icir"],
                f"ICIR_ann{suffix}": agg_ic["icir_ann"],
                f"RankICIR_ann{suffix}": agg_ric["icir_ann"],
                f"n_ic_obs{suffix}": agg_ic["n_obs"],
            })
            v = valid & np.isfinite(signal) & np.isfinite(fwd)
            n_valid = v.sum(axis=1)
            n_uni = np.maximum(sc.universe_mask.sum(axis=1), 1)
            daily_frames.append(pd.DataFrame({
                "date": sc.dates, "formula_id": formula_id, "horizon": k,
                "IC": ic, "RankIC": ric,
                "n_valid": n_valid, "coverage_ratio": n_valid / n_uni,
            }))
        daily = pd.concat(daily_frames, ignore_index=True)
        return OOSResult(row, daily)

    # ------------------------------------------------------------------
    def evaluate_factor(self, formula: str, train_sign: int,
                        split: str = "test") -> OOSResult:
        values, valid = self.ctx.evaluate(formula, split)   # FormulaEvalError 전파
        oriented = self.ctx.oriented(values, train_sign)
        res = self._metrics_for_signal(oriented, valid, split, formula)
        res.row.update({"formula": formula, "train_sign": train_sign,
                        "kind": "individual"})
        return res

    def evaluate_pool(self, formulas: Sequence[str], weights: Sequence[float],
                      split: str = "test", pool_id: str = "pool") -> OOSResult:
        combo, mask = self.ctx.combined_signal(list(formulas), list(weights), split)
        res = self._metrics_for_signal(combo, mask, split, pool_id)
        res.row.update({"formula": pool_id, "kind": "pool",
                        "n_factors": len(formulas),
                        "n_unique_factors": len(set(formulas))})
        return res
