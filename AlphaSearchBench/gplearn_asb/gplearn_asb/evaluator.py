"""MiningEvaluator — 신호 계산 + 원본 호환 IC + validity diagnostics (상시 계산).

신호: alphasearchbench FormulaEngine (silent fallback 없음, FormulaEvalError).
IC 집계: **원본 fast/ictester 호환** —
  provenance: backtest/ictester.py:66-82 (calculate1) 의 텐서판인
  AlphaEval/scripts/tensor_eval.py:457-479 (_daily_ic) 포팅.
  isnan 마스킹(±inf 유지 → 그 날의 corr가 NaN이 되어 탈락),
  유효쌍<2인 날 NaN, 쌍 0인 날은 시리즈에서 제외, NaN 비율>50% → 0.0,
  nanmean, 최종 NaN → 0.0.
  주의: ASB oos.metrics.masked_daily_corr(isfinite 마스킹)와 다르다 —
  마이닝 fitness는 원본 동등성이 우선이므로 이 의미론을 쓴다.
validity: alphasearchbench compute_validity_stats (isfinite 기준, ASB 게이트와
  동일 의미론) — constraint mode와 무관하게 항상 계산·기록된다 (Phase C).

$close fallback: 원본은 평가 실패 formula에 $close의 IC를 상속시킨다
(scripts/fast_eval.py:121-125). 이 루프홀 재현은 off 모드 전용이며 여기서는
fallback용 close IC만 제공한다 — 적용 여부는 fitness.py가 결정.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, List, Tuple

import numpy as np

from .cache import DiagnosticsCache
from . import SEMANTICS_VERSION

from alphasearchbench.data.qlib_provider import FormulaEngine, FormulaEvalError
from alphasearchbench.data.universe import build_universe_mask
from alphasearchbench.validity.metrics import compute_validity_stats

HARD_INVALID_REASONS = ("formula_eval_failed", "all_nonfinite",
                        "no_correlatable_day", "zero_ic_observations")


class MiningEvaluator:
    def __init__(self, cfg):
        market = cfg.require("market")
        start = cfg.require("search.start_date")
        end = cfg.require("search.end_date")
        k = int(cfg.get("label.horizon", 1))

        self.market = market
        self.search_start, self.search_end = str(start), str(end)
        self.engine = FormulaEngine(
            panel_start=self.search_start, panel_end=self.search_end,
            warmup_start=cfg.get("dataset.warmup_start"),
            right_buffer_days=int(cfg.get("dataset.right_buffer_days", 20)))
        self.sel_dates = self.engine.sel_dates(self.search_start, self.search_end)
        self.universe_mask, self.universe_hash = build_universe_mask(
            market, self.sel_dates, self.engine.columns)

        # label: 전체 패널에서 lead 후 창 슬라이스 — 창 마지막 날도 우측 버퍼로
        # 유효 (qlib Ref($close,-1)의 자동 우측 확장과 동일 효과)
        s, e = self.engine.row_range(self.search_start, self.search_end)
        full_close = self.engine.panels["$close"]
        lead = np.full_like(full_close, np.nan)
        lead[:-k] = full_close[k:]
        with np.errstate(all="ignore"):
            fwd_full = (lead / full_close - 1).astype(np.float32)
        self.label = fwd_full[s:e]
        self._close_window = full_close[s:e]

        self.cache = DiagnosticsCache({
            "market": market, "universe_hash": self.universe_hash,
            "search_start": self.search_start, "search_end": self.search_end,
            "dataset_uri": str(cfg.get("dataset.provider_uri")),
            "label_horizon": k,
            "semantics_version": SEMANTICS_VERSION,
        })

        # $close fallback IC (off 모드 전용 재료) — 원본 _close_ic와 동일 의미론
        ic, n_obs = self._daily_ic(self._close_window)
        self.close_signed_ic = ic
        self.close_ic_n_obs = n_obs

    # ------------------------------------------------------------ IC
    def _daily_ic(self, F: np.ndarray) -> Tuple[float, int]:
        """원본 calculate1/_ic_pair 호환 signed IC. 반환: (ic, 유한 IC 관측일 수).

        **two-pass(중심화) Pearson** — pandas Series.corr와 동일한 수치 안정성.
        tensor_eval의 one-pass 합산식(sum(x²)−sum(x)²/n)은 |값|이 극단적으로
        큰 병리 신호(예: Power($high,$change) ~1e130)에서 파국적 상쇄/overflow로
        pandas와 다른 NaN 패턴을 만든다 — canonical 원본(fast runner,
        ictester.calculate1)은 pandas corr이므로 그 의미론을 따른다.
        실측 근거: 883929 winner `Div(Less(Power(...)))`의 CSV fitness
        0.074644 = pandas 값 (one-pass는 NaN 과반 → 0.0으로 오판).
        """
        L = self.label
        valid = ~np.isnan(F) & ~np.isnan(L) & self.universe_mask
        cnt = valid.sum(axis=1)
        f = np.where(valid, F, 0).astype(np.float64)
        l = np.where(valid, L, 0).astype(np.float64)
        with np.errstate(all="ignore"):
            safe = np.where(cnt == 0, 1, cnt)
            mf = (f.sum(1) / safe)[:, None]
            ml = (l.sum(1) / safe)[:, None]
            fc = np.where(valid, f - mf, 0)
            lc = np.where(valid, l - ml, 0)
            cov = (fc * lc).sum(1)
            vf = (fc * fc).sum(1)
            vl = (lc * lc).sum(1)
            r = cov / np.sqrt(vf * vl)
        r[cnt < 2] = np.nan
        # pandas Series.corr는 입력에 ±inf가 있으면 NaN을 반환하며 절대 ±inf가
        # 아니다. 위 합산식은 드물게 inf-(-inf) 경로로 r=±inf를 만들 수 있어
        # (예: Power($volume,$amount)) 원본 의미론에 맞게 NaN으로 강등한다 —
        # 방치하면 |IC|=inf가 stopping_criteria를 오발시킨다.
        r[~np.isfinite(r)] = np.nan
        r = r[cnt >= 1]                     # 유효 쌍 0개인 날은 groupby에 없음
        n_finite = int(np.isfinite(r).sum())
        if len(r) == 0:
            return 0.0, 0
        if np.isnan(r).mean() > 0.5:        # calculate1의 NaN 과반 방어
            return 0.0, n_finite
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            ic = float(np.nanmean(r))
        return (0.0 if not np.isfinite(ic) else ic), n_finite

    # ------------------------------------------------------------ 진단
    def diagnose(self, formula: str) -> Dict[str, Any]:
        """formula의 순수 진단 (constraint mode·threshold 미적용, 캐시됨).

        반환 키:
          signed_train_IC, abs_train_IC  (평가 실패 시 NaN)
          eval_failed(bool), hard_invalid(bool), invalid_reason(str|None)
          n_ic_obs
          + compute_validity_stats 15키 (평가 실패 시 결측 규약: n_*/min_*=0,
            비율류=NaN — ASB report_eval_failure와 동일)
        """
        hit = self.cache.get(formula)
        if hit is not None:
            return hit

        diag: Dict[str, Any] = {"formula": formula}
        try:
            values = self.engine.compute(formula, self.search_start, self.search_end)
        except FormulaEvalError as exc:
            stats = _empty_stats()
            diag.update(stats)
            diag.update({
                "signed_train_IC": float("nan"), "abs_train_IC": float("nan"),
                "n_ic_obs": 0, "eval_failed": True, "hard_invalid": True,
                "invalid_reason": f"formula_eval_failed:{exc.reason}",
            })
            self.cache.put(formula, diag)
            return diag

        stats = compute_validity_stats(values, self.universe_mask)
        ic, n_obs = self._daily_ic(values)
        hard_reason = None
        if stats["n_valid_cells"] == 0:
            hard_reason = "all_nonfinite"
        elif stats["n_correlatable_days"] == 0:
            hard_reason = "no_correlatable_day"
        elif n_obs == 0:
            hard_reason = "zero_ic_observations"

        diag.update(stats)
        diag.update({
            "signed_train_IC": float(ic), "abs_train_IC": float(abs(ic)),
            "n_ic_obs": int(n_obs), "eval_failed": False,
            "hard_invalid": hard_reason is not None,
            "invalid_reason": hard_reason,
        })
        self.cache.put(formula, diag)
        return diag

    def diagnose_batch(self, formulas: List[str]) -> List[Dict[str, Any]]:
        return [self.diagnose(f) for f in formulas]


def _empty_stats() -> Dict[str, float]:
    """ASB validity/evaluator.py report_eval_failure의 결측 규약과 동일."""
    keys = ["n_total_days", "n_valid_days", "valid_day_ratio",
            "mean_daily_n_valid", "median_daily_n_valid", "min_daily_n_valid",
            "mean_daily_coverage_ratio", "median_daily_coverage_ratio",
            "p10_daily_coverage_ratio", "const_day_ratio", "n_correlatable_days",
            "nan_cell_ratio", "inf_cell_ratio", "n_universe_cells", "n_valid_cells"]
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = 0 if k.startswith(("n_", "min_")) else float("nan")
    return out
