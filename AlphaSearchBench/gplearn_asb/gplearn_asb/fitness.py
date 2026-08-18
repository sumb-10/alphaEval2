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

FITNESS_METRICS = ("abs_ic", "net_sharpe", "ic_tstat", "fb_fitness")


def fb_fitness_value(net_sharpe: float, net_ann_ret_arith: float,
                     mean_daily_turnover_oneway: float) -> float:
    """[B3] fb_fitness = net_sharpe × √(|net_ann_ret_arith| / annualized_turnover).

    원본 backtester의 미사용 Fitness(Sharpe×√(|AnnRet|/turnover))의 **ASB 의미론
    재정의** — 원본은 카운트 기반 turnover·기하 AnnRet, 여기는 oneway L1
    turnover(일평균×252)·산술 AnnRet라 수치가 다르다 (NOTES 명기).
    구성값 NaN 또는 turnover ≤ 0 → NaN (fitness.py가 worst로 강등).
    """
    ann_turn = mean_daily_turnover_oneway * 252.0
    vals = (net_sharpe, net_ann_ret_arith, ann_turn)
    if any(v is None or not math.isfinite(float(v)) for v in vals) or ann_turn <= 0:
        return float("nan")
    return float(net_sharpe) * math.sqrt(abs(float(net_ann_ret_arith)) / ann_turn)


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
                     close_signed_ic: float,
                     fitness_metric: str = "abs_ic",
                     close_net_sharpe: float = float("nan"),
                     fitness_opts: Optional[Dict[str, Any]] = None,
                     close_raw_fitness: Optional[float] = None) -> Dict[str, Any]:
    """진단 → selection용 effective fitness + 판정 필드.

    반환: {effective_fitness, raw_fitness, signed_train_IC, abs_train_IC,
           hard_invalid, research_invalid, validity_pass, invalid_reason,
           fallback_used, fitness_condition_failed}
    raw_fitness = penalty 적용 전 fitness metric 값:
      abs_ic     → |train IC|
      net_sharpe → oriented 신호의 train-창 net Sharpe (signed 값 그대로 —
                   음수 Sharpe도 valid; sentinel은 config로 충분히 낮게)
      ic_tstat   → |mean daily IC| / SE  (≥0; 판정 불가 시 NaN→worst)
      fb_fitness → net_sharpe×√(|AnnRet|/ann_turnover) (ASB 의미론 — fb_fitness_value)
    (평가 실패 시 NaN — 스펙 #19: 계산 가능했던 raw 값은 invalid여도 보존)

    fitness_opts (전부 기본 null=off — 기존 run 의미 불변):
      net_sharpe_min_traded_days [B2]: n_traded_days < 값 → worst (모드 무관 —
        fitness 정의의 일부; 규약은 value >= threshold → pass)
      net_sharpe_min_abs_ic [B2]: |signed_train_IC| < 값 → worst
      max_program_length [P2-3]: program_size > 값 → worst (penalty 모드 전용 —
        원형에 없던 규칙이므로 off는 기록조차 안 함)
    close_raw_fitness: off-모드 fallback의 raw (활성 metric 기준). 미지정 시
      abs_ic/net_sharpe는 기존 인자에서 유도 (하위 호환).
    """
    hard = bool(diag["hard_invalid"])
    signed = float(diag["signed_train_IC"])
    opts = fitness_opts or {}

    def _num(d, key) -> float:
        v = d.get(key, float("nan"))
        try:
            return float(v) if v is not None else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    def _raw_of(d) -> float:
        if fitness_metric == "net_sharpe":
            return _num(d, "net_sharpe")
        if fitness_metric == "ic_tstat":
            return _num(d, "ic_tstat")
        if fitness_metric == "fb_fitness":
            return fb_fitness_value(_num(d, "net_sharpe"),
                                    _num(d, "net_ann_ret_arith"),
                                    _num(d, "mean_daily_turnover_oneway"))
        return float(d["abs_train_IC"])

    raw = _raw_of(diag)
    # 비-abs_ic metric이 NaN(무거래·판정불가 등)인 valid 후보는 penalty 대상이
    # 아니라 '정의 불가' — deterministic 비교를 위해 worst로 강등하되 사유 기록
    nan_raw_valid = (fitness_metric != "abs_ic" and not hard
                     and not math.isnan(signed) and math.isnan(raw))
    reason = diag.get("invalid_reason")
    fallback_used = False

    # [B2] fitness 정의 차원의 부가 조건 (constraint mode와 독립 — metric의 일부)
    # fb_fitness도 net_sharpe 내부값으로 정의되므로 동일 가드를 적용한다 —
    # fb는 회전 패널티만 있고 신호 하한이 없어 저IC 승자를 허용함이 실측됐다
    # (fbfit_42 승자 train |IC| 0.006). 가드 키 기본값은 null이라 기존 run 불변.
    cond_fail = None
    if (fitness_metric in ("net_sharpe", "fb_fitness")
            and not hard and not diag["eval_failed"]):
        mtd = opts.get("net_sharpe_min_traded_days")
        if mtd is not None:
            ntd = _num(diag, "n_traded_days")
            if math.isnan(ntd) or ntd < float(mtd):
                cond_fail = "fitness_undefined:insufficient_traded_days"
        mai = opts.get("net_sharpe_min_abs_ic")
        if cond_fail is None and mai is not None:
            if math.isnan(signed) or abs(signed) < float(mai):
                cond_fail = "fitness_undefined:ic_below_floor"

    # [P2-3] 길이 상한 — penalty 모드 전용 (static invalid ⊂ hard invalid 취급)
    static_long = False
    if mode != "off" and opts.get("max_program_length") is not None:
        ps = diag.get("program_size")
        if ps is not None and int(ps) > int(opts["max_program_length"]):
            static_long = True
    hard_eff = hard or static_long

    if mode == "off":
        if diag["eval_failed"]:
            # 원본 루프홀 재현: $close 지표 상속 (동등성 검증용 off 전용)
            signed = float(close_signed_ic)
            if close_raw_fitness is not None:
                raw = float(close_raw_fitness)
            elif fitness_metric == "net_sharpe":
                raw = float(close_net_sharpe)
            else:
                raw = abs(signed)
            fallback_used = True
        effective = worst_fitness if math.isnan(raw) else raw
        research_fails: list = []
    elif mode == "hard_penalty":
        effective = worst_fitness if (hard_eff or math.isnan(raw)) else raw
        research_fails = []
    elif mode == "strict_penalty":
        research_fails = research_failures(diag, thresholds)
        effective = (worst_fitness
                     if (hard_eff or research_fails or math.isnan(raw))
                     else raw)
    else:  # pragma: no cover — normalize_mode가 사전 차단
        raise ValueError(f"unknown constraint mode: {mode!r}")
    if cond_fail is not None:
        effective = worst_fitness           # 모드 무관 — fitness 정의의 일부
    if nan_raw_valid and reason is None:
        reason = f"fitness_undefined:{fitness_metric}_nan"
    if static_long and reason is None:
        reason = "static_invalid:too_long"
    if cond_fail is not None and reason is None:
        reason = cond_fail

    research_invalid = bool(research_fails)
    if research_invalid and not hard_eff and reason is None:
        reason = "research_threshold_failed:" + ",".join(research_fails)

    return {
        "effective_fitness": float(effective),
        "raw_fitness": raw,
        "signed_train_IC": signed,
        "abs_train_IC": abs(signed) if not math.isnan(signed) else float("nan"),
        "hard_invalid": hard_eff,
        "research_invalid": research_invalid,
        "validity_pass": (not hard_eff) and (not research_invalid),
        "invalid_reason": reason,
        "fallback_used": fallback_used,
        "fitness_metric": fitness_metric,
        "fitness_condition_failed": cond_fail is not None,
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
