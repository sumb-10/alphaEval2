"""Validity Gate.

두 계층을 분리한다 (스펙 §Phase 1 + 사용자 확정 원칙 5):

  * **hard invalid** — metric이 수학적으로 정의 불가능한 경우. 코드에 고정되며
    validity.mode와 무관하게 downstream(OOS/QD/Backtest) 평가에서 제외된다:
      - formula_eval_failed:<reason>   (silent fallback 금지 — 평가 실패)
      - all_nonfinite                  (valid cell 0개)
      - no_correlatable_day            (유효쌍≥2 이고 분산>0인 날이 하루도 없음)
      - zero_ic_observations           (label과의 겹침에서 유효 IC 관측 0 —
                                        OOS/train-sign 단계에서 발생 시 마킹)
  * **research threshold** — config(validity.*)로 지정. 기본 null=report only.
    mode=strict일 때만 게이트로 작동. (예: min_valid_day_ratio,
    min_mean_daily_coverage_ratio, min_median_daily_n_valid)

결과는 항상 통계 전체를 보고한다 (report_only여도 저장).
"""
from __future__ import annotations

from typing import Dict, Optional

from ..config import Config
from .metrics import compute_validity_stats


class ValidityReport:
    def __init__(self, formula: str, stats: Dict, hard_valid: bool,
                 invalid_reason: Optional[str], research_pass: bool,
                 research_failures: Dict[str, float]):
        self.formula = formula
        self.stats = stats
        self.hard_valid = hard_valid
        self.invalid_reason = invalid_reason
        self.research_pass = research_pass
        self.research_failures = research_failures

    @property
    def passes_gate(self) -> bool:
        """downstream 평가 진입 여부 (mode를 이미 반영한 최종 판정)."""
        return self.hard_valid and self.research_pass

    def to_row(self) -> Dict:
        row = {
            "formula": self.formula,
            "valid": self.passes_gate,
            "hard_valid": self.hard_valid,
            "invalid_reason": self.invalid_reason,
            "formula_eval_failed": bool(self.invalid_reason
                                        and self.invalid_reason.startswith("formula_eval_failed")),
        }
        row.update(self.stats)
        for k, v in self.research_failures.items():
            row[f"research_fail_{k}"] = v
        return row


_EMPTY_STATS_KEYS = [
    "n_total_days", "n_valid_days", "valid_day_ratio",
    "mean_daily_n_valid", "median_daily_n_valid", "min_daily_n_valid",
    "mean_daily_coverage_ratio", "median_daily_coverage_ratio",
    "p10_daily_coverage_ratio", "const_day_ratio", "n_correlatable_days",
    "nan_cell_ratio", "inf_cell_ratio", "n_universe_cells", "n_valid_cells",
]


class ValidityGate:
    def __init__(self, cfg: Config):
        self.mode = cfg.get("validity.mode", "report_only")
        if self.mode not in ("report_only", "strict"):
            raise ValueError(f"validity.mode must be report_only|strict, got {self.mode}")
        self.thresholds = {
            "min_valid_day_ratio": cfg.get("validity.min_valid_day_ratio"),
            "min_mean_daily_coverage_ratio": cfg.get("validity.min_mean_daily_coverage_ratio"),
            "min_median_daily_n_valid": cfg.get("validity.min_median_daily_n_valid"),
        }

    # ---- 평가 실패 (silent fallback 금지 경로) ----
    def report_eval_failure(self, formula: str, reason: str) -> ValidityReport:
        stats = {k: (0 if k.startswith("n_") or k.startswith("min_") else float("nan"))
                 for k in _EMPTY_STATS_KEYS}
        return ValidityReport(formula, stats, hard_valid=False,
                              invalid_reason=f"formula_eval_failed:{reason}",
                              research_pass=False, research_failures={})

    # ---- 정상 평가 신호 ----
    def assess(self, formula: str, values, universe_mask) -> ValidityReport:
        stats = compute_validity_stats(values, universe_mask)

        invalid_reason = None
        if stats["n_valid_cells"] == 0:
            invalid_reason = "all_nonfinite"
        elif stats["n_correlatable_days"] == 0:
            invalid_reason = "no_correlatable_day"
        hard_valid = invalid_reason is None

        failures: Dict[str, float] = {}
        checks = [
            ("min_valid_day_ratio", stats["valid_day_ratio"]),
            ("min_mean_daily_coverage_ratio", stats["mean_daily_coverage_ratio"]),
            ("min_median_daily_n_valid", stats["median_daily_n_valid"]),
        ]
        for key, observed in checks:
            th = self.thresholds.get(key)
            if th is not None and observed < th:
                failures[key] = observed
        research_pass = (self.mode == "report_only") or (len(failures) == 0)

        return ValidityReport(formula, stats, hard_valid, invalid_reason,
                              research_pass, failures)

    @staticmethod
    def mark_zero_ic(report: ValidityReport) -> ValidityReport:
        """label 겹침에서 유효 IC 관측 0 — OOS 단계에서 발견 시 hard invalid로 격하."""
        report.hard_valid = False
        report.invalid_reason = "zero_ic_observations"
        report.research_pass = False
        return report
