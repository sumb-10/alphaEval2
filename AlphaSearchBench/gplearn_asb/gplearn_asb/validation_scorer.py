"""[C-1] GP-side validation scorer — budget 배분 결정 전용 내부 도구.

train에서 생성된 최종 alpha pool을 validation 기간에 **동일 GP semantics**
로 점수화한다. 범용 평가 프레임워크가 아니며, ASB evaluation policy
(evaluator/backtest/OOS/QD)를 사용하지 않는다 — shared data/utility 계층
(`FormulaEngine`, `daily_zscore`)의 재사용만 허용 (Phase C 경계,
Vanilla_GP_v2.md §8-5). 계약 전문: docs/experiments/2026-08-19_C1_runbook_draft.md

계약 요약 (동결):
  * orientation = pool CSV의 raw `signed_train_IC` 부호 고정 (validation
    재추정 금지; raw임은 회귀 테스트로 고정)
  * combiner = train_signed_equal: combined = Σᵢ (signᵢ/n)·daily_zscore(sigᵢ)
    combined valid mask = ∨ᵢ validᵢ (결측→0 치환 셀의 누수 차단)
  * 포트폴리오·성과 = MiningEvaluator._net_sharpe(combined, sign=+1)
    직접 호출 (재구현 금지 — n=1 equivalence regression contract)
  * pool_fb = fb_fitness_value(..., min_annual_turnover=0.01) 재사용
  * integrity gate 위반·퇴화 pool → cell failure (임의 저점수 부여 금지)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from alphasearchbench.data.signal_context import daily_zscore

from .cli import V2_FB_MIN_ANNUAL_TURNOVER
from .fitness import fb_fitness_value


# ------------------------------------------------------------ 순수 함수부
def combine_pool_signals(signals: Sequence[np.ndarray],
                         valids: Sequence[np.ndarray],
                         signs: Sequence[int]) -> Tuple[np.ndarray, np.ndarray]:
    """train_signed_equal 결합 (계약 2).

    combined = Σᵢ (signᵢ/n)·daily_zscore(sigᵢ, validᵢ);
    union mask = ∨ᵢ validᵢ. union 밖 셀은 NaN — daily_zscore의 결측→0
    치환값이 mask 없이 포트폴리오에 새는 것을 차단하고, n=1에서 candidate
    평가(raw 신호 + finite mask)와 동일 포트폴리오를 보장한다(z-score는
    일별 양수 스케일 아핀 변환 → rank 보존).
    """
    if not (len(signals) == len(valids) == len(signs)) or not signals:
        raise ValueError("signals/valids/signs 길이 불일치 또는 빈 pool")
    n = len(signals)
    combined = np.zeros(signals[0].shape, dtype=np.float64)
    union = np.zeros(signals[0].shape, dtype=bool)
    for sig, valid, sgn in zip(signals, valids, signs):
        combined += (float(sgn) / n) * daily_zscore(sig, valid)
        union |= valid
    combined = np.where(union, combined, np.nan)
    return combined, union


def pool_integrity_check(formulas: Sequence[str],
                         sics: Sequence[float],
                         pool_size: int) -> Tuple[bool, Optional[str]]:
    """계약 5의 구조 검사 (신호 계산 성공 여부는 score_pool에서 판정).

    validation에서 candidate-level coverage threshold를 재적용하지 않는다
    — C-1은 factor 추가 선별이 아니라 pool 전체의 OOS utility 평가.
    """
    if len(formulas) != pool_size:
        return False, f"model_failure:n_factors={len(formulas)}!=pool_size={pool_size}"
    if len(set(formulas)) != pool_size:
        return False, f"model_failure:duplicate_formulas({pool_size - len(set(formulas))})"
    for f, sic in zip(formulas, sics):
        try:
            v = float(sic)
        except (TypeError, ValueError):
            return False, f"model_failure:orientation_missing:{f[:60]}"
        if math.isnan(v):
            return False, f"model_failure:orientation_missing:{f[:60]}"
    return True, None


def train_signs(sics: Sequence[float]) -> List[int]:
    """계약 1 — runner 규약과 동일: sign = +1 if sic >= 0 else −1."""
    return [1 if float(s) >= 0 else -1 for s in sics]


# ------------------------------------------------------------ scorer 본체
def score_pool(evaluator, formulas: Sequence[str], sics: Sequence[float],
               pool_size: int = 10) -> Dict:
    """validation 창으로 인스턴스화된 MiningEvaluator로 pool 점수화.

    evaluator: search.start/end = validation 창인 MiningEvaluator.
    반환(계약 6): pool_fb/net_sharpe/net_ann_ret_arith/
    annualized_turnover_oneway/n_traded_days/n_factors/signs/
    integrity_pass/failure_reason. 실패 시 metric은 NaN 유지.
    """
    out: Dict = {"pool_fb": float("nan"), "net_sharpe": float("nan"),
                 "net_ann_ret_arith": float("nan"),
                 "annualized_turnover_oneway": float("nan"),
                 "n_traded_days": None, "n_factors": len(formulas),
                 "signs": None, "integrity_pass": False,
                 "failure_reason": None,
                 "validation_window": [evaluator.search_start,
                                       evaluator.search_end]}
    ok, reason = pool_integrity_check(formulas, sics, pool_size)
    if not ok:
        out["failure_reason"] = reason
        return out

    signals, valids = [], []
    for f in formulas:
        try:
            sig = evaluator.engine.compute(f, evaluator.search_start,
                                           evaluator.search_end)
        except Exception as e:                       # engine exception → model failure
            out["failure_reason"] = f"model_failure:eval_error:{type(e).__name__}:{f[:60]}"
            return out
        valid = np.isfinite(sig) & evaluator.universe_mask
        if not valid.any():                          # all-nonfinite → model failure
            out["failure_reason"] = f"model_failure:all_nonfinite:{f[:60]}"
            return out
        signals.append(sig)                          # 일부 NaN은 failure 아님(mask 처리)
        valids.append(valid)

    signs = train_signs(sics)
    combined, _union = combine_pool_signals(signals, valids, signs)
    ns, stats = evaluator._net_sharpe(combined, sign=1)
    fb = fb_fitness_value(ns, stats["net_ann_ret_arith"],
                          stats["mean_daily_turnover_oneway"],
                          min_annual_turnover=V2_FB_MIN_ANNUAL_TURNOVER)
    out.update({
        "integrity_pass": True,
        "signs": signs,
        "net_sharpe": float(ns) if ns == ns else float("nan"),
        "net_ann_ret_arith": stats["net_ann_ret_arith"],
        "annualized_turnover_oneway": stats["mean_daily_turnover_oneway"] * 252.0,
        "n_traded_days": stats["n_traded_days"],
        "pool_fb": fb,
    })
    if math.isnan(fb):                               # 퇴화 pool → cell failure
        out["failure_reason"] = "model_failure:degenerate_pool_fb_nan"
    return out
