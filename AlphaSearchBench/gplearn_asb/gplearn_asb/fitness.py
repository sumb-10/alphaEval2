"""Constraint mode → effective fitness (worst-fitness penalty).

핵심 규약 (스펙 #2, #6, #9, #24):
  * invalid candidate는 population에서 삭제되지 않는다 — selection이 소비하는
    fitness만 worst sentinel로 강등된다.
  * sentinel은 **유한값**(기본 −1.0, config `constraint.worst_fitness`) —
    NaN/−inf 금지. greater_is_better=True에서 모든 valid |IC|(≥0)보다 작아
    tournament argmax·HOF argsort에서 deterministic하게 최하위.
  * research threshold 규약: value >= threshold → pass (경계값 통과).
    통계값이 NaN이면 fail (판정 불가 = 통과 아님).
  * off 모드는 원본 의미론 재현: 평가 실패 → $close signed IC 상속
    (provenance: scripts/fast_eval.py:121-125). fallback 사용 사실은 기록된다.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

THRESHOLD_KEYS = {
    "min_mean_daily_coverage_ratio": "mean_daily_coverage_ratio",
    "min_median_daily_n_valid": "median_daily_n_valid",
    "min_valid_day_ratio": "valid_day_ratio",
}


def research_failures(diag: Dict[str, Any],
                      thresholds: Dict[str, Optional[float]]) -> list:
    """활성(비-null) threshold 각각에 대해 value >= threshold 검사."""
    fails = []
    for th_key, stat_key in THRESHOLD_KEYS.items():
        th = thresholds.get(th_key)
        if th is None:
            continue
        v = diag.get(stat_key)
        try:
            ok = (v is not None) and (not math.isnan(float(v))) and float(v) >= float(th)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            fails.append(th_key)
    return fails


def apply_constraint(mode: str, diag: Dict[str, Any],
                     thresholds: Dict[str, Optional[float]],
                     worst_fitness: float,
                     close_signed_ic: float) -> Dict[str, Any]:
    """진단 → selection용 effective fitness + 판정 필드.

    반환: {effective_fitness, raw_fitness, signed_train_IC, abs_train_IC,
           hard_invalid, research_invalid, validity_pass, invalid_reason,
           fallback_used}
    raw_fitness = penalty 적용 전의 |IC| (평가 실패 시 NaN — 스펙 #19:
    계산 가능했던 raw IC는 invalid여도 보존).
    """
    hard = bool(diag["hard_invalid"])
    signed = float(diag["signed_train_IC"])
    raw = float(diag["abs_train_IC"])
    reason = diag.get("invalid_reason")
    fallback_used = False

    if mode == "off":
        if diag["eval_failed"]:
            # 원본 루프홀 재현: $close IC 상속 (동등성 검증용 off 전용)
            signed = float(close_signed_ic)
            raw = abs(signed)
            fallback_used = True
        effective = raw
        research_fails: list = []
    elif mode == "hard_penalty":
        effective = worst_fitness if hard else raw
        research_fails = []
    elif mode == "strict_penalty":
        research_fails = research_failures(diag, thresholds)
        effective = worst_fitness if (hard or research_fails) else raw
    else:  # pragma: no cover — normalize_mode가 사전 차단
        raise ValueError(f"unknown constraint mode: {mode!r}")

    research_invalid = bool(research_fails)
    if research_invalid and not hard and reason is None:
        reason = "research_threshold_failed:" + ",".join(research_fails)

    return {
        "effective_fitness": float(effective),
        "raw_fitness": raw,
        "signed_train_IC": signed,
        "abs_train_IC": abs(signed) if fallback_used else raw,
        "hard_invalid": hard,
        "research_invalid": research_invalid,
        "validity_pass": (not hard) and (not research_invalid),
        "invalid_reason": reason,
        "fallback_used": fallback_used,
    }


def check_sentinel_separation(worst_fitness: float, parsimony: float,
                              max_len_estimate: int = 500) -> Optional[str]:
    """parsimony≠0일 때 sentinel 분리 조건 경고문 반환 (없으면 None).

    valid의 fitness_ = |IC| − parsimony·len ≥ −parsimony·max_len 이므로
    parsimony·max_len < |worst_fitness| 여야 invalid < valid가 항상 성립.
    """
    if parsimony and parsimony * max_len_estimate >= abs(worst_fitness):
        return (f"parsimony({parsimony})×max_len({max_len_estimate}) ≥ "
                f"|worst_fitness|({abs(worst_fitness)}) — invalid가 valid보다 "
                f"유리해질 수 있음. worst_fitness를 더 낮추세요.")
    return None
