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
from .static_check import static_check
from . import SEMANTICS_VERSION

from alphasearchbench.data.qlib_provider import (FormulaEngine, FormulaEvalError,
                                                 parse_expression)
from alphasearchbench.data.universe import build_universe_mask
from alphasearchbench.validity.metrics import compute_validity_stats

HARD_INVALID_REASONS = ("formula_eval_failed", "all_nonfinite",
                        "no_correlatable_day", "zero_ic_observations")


def apply_label_tail_exclusion(label, k: int) -> int:
    """[v2] 창 마지막 k행의 label을 NaN 마스크 (in-place).

    train 마지막 horizon 거래일의 forward label이 경계 밖(validation 첫
    거래일) 가격을 쓰는 1일 누출을 차단 — train-only 계약의 기본 처리
    (Vanilla_GP_v2.md §6 caveat 4). purge/embargo(P-4)와 별개.
    반환 = 실제 제외 일수 (k≤0 또는 창이 k 이하이면 0 — no-op)."""
    if k <= 0 or label.shape[0] <= k:
        return 0
    label[-k:] = np.nan
    return k


class MiningEvaluator:
    def __init__(self, cfg):
        market = cfg.require("market")
        start = cfg.require("search.start_date")
        end = cfg.require("search.end_date")
        k = int(cfg.get("label.horizon", 1))
        # 비용 인지형 fitness(net_sharpe/fb_fitness) — 필요할 때만 후보별 계산
        self.fitness_metric = str(cfg.get("gp.fitness_metric", "abs_ic"))
        self.cost_rate = float(cfg.get("backtest.transaction_cost_rate", 0.0015))
        self.ls_quantile = float(cfg.get("backtest.long_short_quantile", 0.2))
        # [P2] 정적 사전검증 게이트: penalty 모드에서만 static invalid의 데이터
        # 접근을 스킵 (off 모드는 원형 parity — 기록만). static ⊂ hard 증명으로
        # effective fitness는 불변, 사유 문자열·데이터 비용만 달라진다.
        self.static_gate = (bool(cfg.get("gp.static_gate", True))
                            and str(cfg.get("constraint.mode", "off")) != "off")

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
        # [v2 전용, legacy 기본 off — 동결 불변] label tail exclusion
        self.label_tail_excluded = 0
        if bool(cfg.get("label.tail_exclusion", False)):
            self.label = self.label.copy()
            self.label_tail_excluded = apply_label_tail_exclusion(self.label, k)
        self._close_window = full_close[s:e]

        cache_ctx = {
            "market": market, "universe_hash": self.universe_hash,
            "search_start": self.search_start, "search_end": self.search_end,
            "dataset_uri": str(cfg.get("dataset.provider_uri")),
            "label_horizon": k,
            "semantics_version": SEMANTICS_VERSION,
        }
        if self.label_tail_excluded:
            cache_ctx["label_tail_exclusion"] = self.label_tail_excluded
        # static gate가 켜진 run은 static-invalid의 진단이 데이터-프리 스텁이라
        # 게이트 없는 run(off/parity)과 캐시를 공유하면 안 됨 — 네임스페이스 분리.
        # (기본 off/기존 run의 fingerprint는 불변 — 키를 조건부로만 추가)
        if self.static_gate:
            cache_ctx["static_gate"] = True
        self.cache = DiagnosticsCache(cache_ctx)

        # $close fallback 재료 (off 모드 전용) — 원본 _close_ic와 동일 의미론.
        # close_raw_fitness = 활성 fitness_metric 기준의 fallback raw 값.
        ic, n_obs, ic_std = self._daily_ic(self._close_window)
        self.close_signed_ic = ic
        self.close_ic_n_obs = n_obs
        self.close_net_sharpe = float("nan")
        self.close_raw_fitness = abs(ic)
        if self.fitness_metric in ("net_sharpe", "fb_fitness"):
            self.close_net_sharpe, ns_stats = self._net_sharpe(
                self._close_window, 1 if ic >= 0 else -1)
            if self.fitness_metric == "net_sharpe":
                self.close_raw_fitness = self.close_net_sharpe
            else:
                from .fitness import fb_fitness_value
                self.close_raw_fitness = fb_fitness_value(
                    self.close_net_sharpe, ns_stats["net_ann_ret_arith"],
                    ns_stats["mean_daily_turnover_oneway"])
        elif self.fitness_metric == "ic_tstat":
            self.close_raw_fitness = _ic_tstat(ic, n_obs, ic_std)

    # ------------------------------------------------------------ IC
    def _daily_ic(self, F: np.ndarray) -> Tuple[float, int, float]:
        """원본 calculate1/_ic_pair 호환 signed IC.
        반환: (ic, 유한 IC 관측일 수, 일별 IC 표본표준편차 ddof=1 — ic_tstat 재료).

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
        # 일별 IC 표본표준편차 (ic_tstat 재료) — 유한 r 기준 ddof=1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            daily_std = (float(np.nanstd(r, ddof=1)) if n_finite >= 2
                         else float("nan"))
        if len(r) == 0:
            return 0.0, 0, daily_std
        if np.isnan(r).mean() > 0.5:        # calculate1의 NaN 과반 방어
            return 0.0, n_finite, daily_std
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            ic = float(np.nanmean(r))
        return (0.0 if not np.isfinite(ic) else ic), n_finite, daily_std

    # ------------------------------------------------------------ net Sharpe
    def _net_sharpe(self, F: np.ndarray, sign: int,
                    return_weights: bool = False) -> Tuple[float, Dict[str, float]]:
        """oriented 신호의 일별 20/20 long-short net Sharpe (search window).

        return_weights=True(기본 False — 동작 불변): stats에 일별 가중치
        행렬 W("weights")와 일별 net 수익 시계열("net_daily")을 추가.
        C-1 scorer의 n=1 equivalence regression 관측 전용 kwarg.

        의미론 = ASB simple backtest와 동일 수학 (weights 명시형, gross 1 =
        long 0.5 + short 0.5, turnover_oneway = l1/2, 첫날 건립 비용 부과,
        Sharpe = mean(net)/std(net, ddof=1)×√252). label = forward k(IC와 동일).
        비용률·quantile은 config 주입 (backtest.transaction_cost_rate 등).
        """
        s = sign * F
        L = self.label
        valid = np.isfinite(s) & np.isfinite(L) & self.universe_mask
        T, N = s.shape
        W = np.zeros((T, N), dtype=np.float64)
        for t in range(T):
            m = valid[t]
            n = int(m.sum())
            if n < 5:                                   # 극소 단면일은 무포지션
                continue
            v = s[t, m].astype(np.float64)
            k = max(1, int(np.floor(n * self.ls_quantile)))
            order = np.argsort(v, kind="mergesort")
            idx = np.where(m)[0]
            W[t, idx[order[-k:]]] = 0.5 / k             # long top-q
            W[t, idx[order[:k]]] = -0.5 / k             # short bottom-q
        with np.errstate(all="ignore"):
            gross = np.nansum(np.where(valid, W * L, 0.0), axis=1)
        dW = np.abs(np.diff(W, axis=0)).sum(axis=1)
        turn_l1 = np.concatenate([[np.abs(W[0]).sum()], dW])   # 첫날 건립 포함
        net = gross - self.cost_rate * (turn_l1 / 2.0)         # oneway
        traded = np.abs(W).sum(axis=1) > 0
        stats = {"net_ann_ret_arith": float(net.mean() * 252),
                 "mean_daily_turnover_oneway": float((turn_l1 / 2).mean()),
                 "n_traded_days": int(traded.sum())}
        if return_weights:
            stats["weights"] = W
            stats["net_daily"] = net
        sd = float(np.std(net, ddof=1)) if len(net) > 1 else float("nan")
        if not np.isfinite(sd) or sd == 0:
            return float("nan"), stats
        return float(net.mean() / sd * np.sqrt(252)), stats

    # ------------------------------------------------------------ 진단
    def diagnose(self, formula: str) -> Dict[str, Any]:
        """formula의 순수 진단 (constraint mode·threshold 미적용, 캐시됨).

        반환 키:
          signed_train_IC, abs_train_IC  (평가 실패 시 NaN)
          ic_daily_std, ic_tstat  (판정 불가 시 NaN)
          eval_failed(bool), hard_invalid(bool), invalid_reason(str|None)
          n_ic_obs
          static_invalid_reason(str|None), static_flag_constant_subtree(bool),
          program_size(int|None)  — [P2] formula-결정적 정적 검사 (상시 기록)
          + compute_validity_stats 15키 (평가 실패 시 결측 규약: n_*/min_*=0,
            비율류=NaN — ASB report_eval_failure와 동일)

        [P2] static gate가 켜진 evaluator(penalty 모드 전용)는 static invalid
        수식의 데이터 접근을 스킵하고 스텁 진단(hard_invalid=True,
        invalid_reason=static_invalid:*)을 반환한다 — 별도 캐시 네임스페이스.
        """
        hit = self.cache.get(formula)
        if hit is not None:
            return hit

        diag: Dict[str, Any] = {"formula": formula}
        # [P2] 정적 검사 (파스 실패는 아래 engine.compute가 정식 사유로 분류)
        sc = {"static_invalid_reason": None,
              "static_flag_constant_subtree": False,
              "static_flag_nonstd_window": False,
              "program_size": None, "program_depth": None}
        try:
            sc = static_check(parse_expression(formula))
        except Exception:
            pass
        diag.update(sc)

        if self.static_gate and sc["static_invalid_reason"]:
            # 데이터 접근 스킵 — static ⊂ hard 이므로 penalty 모드의 effective
            # fitness는 데이터 경로와 동일(worst). off 모드는 이 경로에 오지 않음.
            diag.update(_empty_stats())
            diag.update({
                "signed_train_IC": float("nan"), "abs_train_IC": float("nan"),
                "ic_daily_std": float("nan"), "ic_tstat": float("nan"),
                "n_ic_obs": 0, "eval_failed": False, "hard_invalid": True,
                "invalid_reason": sc["static_invalid_reason"],
            })
            self.cache.put(formula, diag)
            return diag

        try:
            values = self.engine.compute(formula, self.search_start, self.search_end)
        except FormulaEvalError as exc:
            stats = _empty_stats()
            diag.update(stats)
            diag.update({
                "signed_train_IC": float("nan"), "abs_train_IC": float("nan"),
                "ic_daily_std": float("nan"), "ic_tstat": float("nan"),
                "n_ic_obs": 0, "eval_failed": True, "hard_invalid": True,
                "invalid_reason": f"formula_eval_failed:{exc.reason}",
            })
            self.cache.put(formula, diag)
            return diag

        stats = compute_validity_stats(values, self.universe_mask)
        ic, n_obs, ic_std = self._daily_ic(values)
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
            "ic_daily_std": float(ic_std), "ic_tstat": _ic_tstat(ic, n_obs, ic_std),
            "n_ic_obs": int(n_obs), "eval_failed": False,
            "hard_invalid": hard_reason is not None,
            "invalid_reason": hard_reason,
        })
        if self.fitness_metric in ("net_sharpe", "fb_fitness") and hard_reason is None:
            sign = 1 if ic >= 0 else -1
            ns, ns_stats = self._net_sharpe(values, sign)
            diag["net_sharpe"] = ns
            diag.update(ns_stats)
        self.cache.put(formula, diag)
        return diag

    def diagnose_batch(self, formulas: List[str]) -> List[Dict[str, Any]]:
        return [self.diagnose(f) for f in formulas]


def _ic_tstat(ic: float, n_obs: int, daily_std: float) -> float:
    """[B1] ic_tstat = |mean(daily IC)| / (std(daily IC, ddof=1)/√n_obs).

    판정 불가(n<2, std 비유한/0) → NaN — fitness.py가 worst로 강등
    (fitness_undefined:ic_tstat_nan). ic는 _daily_ic의 방어 적용 후 값을
    그대로 쓴다(NaN 과반 방어로 0이 된 경우 t=0 — fitness 의미론과 일관).
    """
    import math
    if n_obs < 2 or not math.isfinite(daily_std) or daily_std == 0:
        return float("nan")
    if not math.isfinite(ic):
        return float("nan")
    return abs(ic) / (daily_std / math.sqrt(n_obs))


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
