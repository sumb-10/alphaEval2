"""SignalContext — OOS/QD/Backtest가 공유하는 공통 signal/data 계층.

책임:
  * market / benchmark / train·valid·test split
  * split별 point-in-time universe mask
  * formula 평가 (FormulaEngine) + oriented signal (train_sign 적용)
  * forward returns (config horizon들) / execution returns
  * benchmark returns / rolling volatility (+train에서 regime 경계 캘리브레이션)
  * ADV20 및 일별 유동성 percentile
  * 일별 cross-sectional z-score (provenance: modeltester.zscore — ddof=0,
    std<1e-8→1, 결측→0)
  * pool combined signal (frozen weights)

sign 규약: train_sign은 이 계층 밖(train split의 signed IC)에서만 결정되고,
평가기는 sign을 **입력으로만** 받는다. test IC를 보고 방향을 정하는 API는
존재하지 않는다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..config import Config, ConfigError
from .qlib_bootstrap import bootstrap_qlib
from .qlib_provider import FormulaEngine, FormulaEvalError
from .universe import build_universe_mask
from .labels import forward_return, execution_return


def daily_zscore(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """일별 cross-sectional z-score. 결측(invalid)은 0.

    provenance: AlphaEval backtest/modeltester.py zscore() — mean/std(ddof=0),
    std<1e-8 → 1 치환, 이후 NaN→0. 여기서는 valid 마스크 기반으로 동일 의미를
    dense하게 구현한다.
    """
    v = np.where(valid, values, np.nan).astype(np.float64)
    with np.errstate(all="ignore"):
        mu = np.nanmean(v, axis=1, keepdims=True)
        sd = np.nanstd(v, axis=1, keepdims=True)          # ddof=0
        sd = np.where(sd < 1e-8, 1.0, sd)
        z = (v - mu) / sd
    z[~np.isfinite(z)] = 0.0
    return z


class SplitContext:
    """단일 split(train/valid/test)의 공유 데이터."""

    def __init__(self, name: str, start: str, end: str, engine: FormulaEngine,
                 market: str, horizons: Sequence[int]):
        self.name = name
        self.start, self.end = start, end
        self.engine = engine
        self.dates = engine.sel_dates(start, end)
        s, e = engine.row_range(start, end)
        self._rows = (s, e)
        self.universe_mask, self.universe_hash = build_universe_mask(
            market, self.dates, engine.columns)
        close_full = engine.panels["$close"]
        open_full = engine.panels["$open"]
        self.forward: Dict[int, np.ndarray] = {
            k: forward_return(close_full, k)[s:e] for k in horizons
        }
        self._close_full = close_full
        self._open_full = open_full

    def execution_return(self, mode: str) -> np.ndarray:
        s, e = self._rows
        return execution_return(mode, self._close_full, self._open_full)[s:e]

    @property
    def n_universe_daily(self) -> np.ndarray:
        return self.universe_mask.sum(axis=1)


class SignalContext:
    """전체 컨텍스트: engine 1개 + split 3개 + benchmark/유동성/regime 캘리브레이션."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.market: str = cfg.require("market")
        self.splits_cfg = cfg.splits()
        bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"],
                       cfg["dataset.qlib_kernels"])

        horizons = sorted(set(
            list(cfg.get("qd.horizons", [1, 5, 10, 20])) +
            list(cfg.get("oos.horizons", [1]))))
        panel_start = self.splits_cfg["train"][0]
        panel_end = self.splits_cfg["test"][1]
        self.engine = FormulaEngine(
            panel_start, panel_end,
            warmup_start=cfg.get("dataset.warmup_start"),
            right_buffer_days=cfg.get("dataset.right_buffer_days", 20))
        self._qlib_native_cache: Dict[Tuple[str, str], np.ndarray] = {}
        self._engine_used: Dict[str, str] = {}

        self.split: Dict[str, SplitContext] = {}
        for name, (s0, s1) in self.splits_cfg.items():
            self.split[name] = SplitContext(name, s0, s1, self.engine,
                                            self.market, horizons)

        # ---- benchmark ----
        bench_ticker = cfg.get(f"benchmark.map.{self.market}")
        if bench_ticker is None:
            raise ConfigError(f"benchmark.map에 {self.market!r} 매핑이 없습니다")
        self.benchmark_ticker = bench_ticker
        self._bench_ret_full = self._benchmark_returns_full(bench_ticker)

        # ---- 유동성 (ADV) ----
        adv_w = int(cfg.get("qd.liquidity.adv_window", 20))
        amount = pd.DataFrame(self.engine.panels["$amount"])
        self._adv_full = amount.rolling(adv_w, min_periods=1).mean().to_numpy()

        # ---- regime 캘리브레이션 (train에서만) ----
        self.regime = self._calibrate_regimes()

    # ------------------------------------------------------------------
    def _benchmark_returns_full(self, ticker: str) -> np.ndarray:
        """지수 일수익률 (full 패널 길이). 지수는 'all' 패널 컬럼에 포함되어 있음."""
        cols = self.engine.columns
        if ticker in cols:
            close = self.engine.panels["$close"][:, cols.get_loc(ticker)]
        else:  # 패널에 없으면 직접 질의 (방어적)
            from qlib.data import D
            s = D.features([ticker], ["$close"],
                           start_time=str(self.engine.dates[0].date()),
                           end_time=str(self.engine.dates[-1].date()),
                           freq="day").iloc[:, 0].droplevel(0)
            close = s.reindex(self.engine.dates).to_numpy()
        with np.errstate(all="ignore"):
            ret = close[1:] / close[:-1] - 1
        return np.concatenate([[np.nan], ret]).astype(np.float64)

    def benchmark_returns(self, split: str) -> np.ndarray:
        s, e = self.engine.row_range(*self.splits_cfg[split])
        return self._bench_ret_full[s:e]

    def benchmark_vol(self, split: str) -> np.ndarray:
        w = int(self.cfg.get("qd.volatility.window", 20))
        vol_full = pd.Series(self._bench_ret_full).rolling(
            w, min_periods=max(2, w // 2)).std().to_numpy()
        s, e = self.engine.row_range(*self.splits_cfg[split])
        return vol_full[s:e]

    def adv(self, split: str) -> np.ndarray:
        s, e = self.engine.row_range(*self.splits_cfg[split])
        return self._adv_full[s:e]

    def _calibrate_regimes(self) -> Dict[str, float]:
        """volatility regime 경계를 train split에서 산출해 freeze."""
        qs = self.cfg.get("qd.volatility.quantiles", [1 / 3, 2 / 3])
        vol_train = self.benchmark_vol("train")
        v = vol_train[np.isfinite(vol_train)]
        if len(v) == 0:
            raise ConfigError("train 구간에서 benchmark volatility를 계산할 수 없습니다")
        lo, hi = float(np.quantile(v, qs[0])), float(np.quantile(v, qs[1]))
        return {"vol_low_threshold": lo, "vol_high_threshold": hi,
                "vol_window": int(self.cfg.get("qd.volatility.window", 20)),
                "vol_quantiles": [float(qs[0]), float(qs[1])]}

    # ------------------------------------------------------------------
    def evaluate(self, formula: str, split: str) -> Tuple[np.ndarray, np.ndarray]:
        """formula → (values float32, valid mask). 실패는 FormulaEvalError 전파.

        valid cell = finite(value) & point-in-time universe.

        signal engine 2단계: (1) FormulaEngine(고속, GP 함수형 문법) →
        (2) 문법 미지원(parse_error/unknown_operator/unknown_field)일 때만
        **qlib native `D.features`로 같은 수식을 계산**해 동일 격자에 정렬.
        qlib이 reference 의미론이므로 이것은 silent fallback(다른 신호로의
        대체 — 금지)이 아니라 엔진 선택이며, 어떤 엔진이 쓰였는지
        `engine_used(formula)`로 조회·기록된다. (AlphaAgent처럼 infix 등
        qlib 전체 문법을 쓰는 miner 지원 — IMPLEMENTATION_NOTES 참조.)
        """
        sc = self.split[split]
        try:
            values = self.engine.compute(formula, sc.start, sc.end)
        except FormulaEvalError as e:
            reason = getattr(e, "reason", "")
            if not reason.startswith(("parse_error",
                                      "eval_error:unknown_operator",
                                      "eval_error:unknown_field")):
                raise                       # 진짜 평가 실패는 그대로 전파
            values = self._qlib_native_compute(formula, split)
        valid = np.isfinite(values) & sc.universe_mask
        return values, valid

    def _qlib_native_compute(self, formula: str, split: str) -> np.ndarray:
        """qlib native 평가 → engine 격자(sel_dates × columns)로 정렬 (캐시)."""
        key = (formula, split)
        if key in self._qlib_native_cache:
            return self._qlib_native_cache[key]
        from qlib.data import D
        sc = self.split[split]
        try:
            raw = D.features(D.instruments(market="all"), [formula],
                             start_time=sc.start, end_time=sc.end,
                             freq="day").iloc[:, 0]
        except Exception as ex:
            raise FormulaEvalError(f"eval_error:qlib_native:{type(ex).__name__}:{ex}",
                                   formula)
        wide = raw.unstack(level="instrument").reindex(
            index=sc.dates, columns=self.engine.columns)
        values = wide.to_numpy().astype(np.float32)
        self._qlib_native_cache[key] = values
        self._engine_used[formula] = "qlib_native"
        return values

    def engine_used(self, formula: str) -> str:
        return self._engine_used.get(formula, "formula_engine")

    def oriented(self, values: np.ndarray, train_sign: int) -> np.ndarray:
        if train_sign not in (-1, 1):
            raise ValueError(f"train_sign must be ±1, got {train_sign!r}")
        return train_sign * values

    def signed_ic_on_train(self, formula: str) -> float:
        """train split에서 signed daily-IC 평균 — train_sign 복원용.

        (AlphaEval ictester.calculate1과 동일한 집계 의미의 signed 버전.)
        """
        from ..oos.metrics import daily_ic_series
        values, valid = self.evaluate(formula, "train")
        fwd = self.split["train"].forward[1]
        ic = daily_ic_series(values, fwd, valid)
        finite = ic[np.isfinite(ic)]
        if len(finite) == 0:
            raise FormulaEvalError("hard_invalid:zero_ic_observations", formula)
        return float(finite.mean())

    def combined_signal(self, formulas: List[str], weights: Sequence[float],
                        split: str) -> Tuple[np.ndarray, np.ndarray]:
        """frozen weights로 결합 신호 생성: Σ wᵢ·zscore(alphaᵢ).

        weights가 방향을 흡수하므로 개별 train_sign은 적용하지 않는다
        (provenance: modeltester 149행 — 일별 z-score 후 dot(weights)).
        반환: (combined (T×N) float64, valid mask = 유효 z가 1개 이상인 셀...
        결합 신호는 결측을 0으로 보므로 universe mask를 valid로 반환)
        """
        if len(formulas) != len(weights):
            raise ValueError("formulas와 weights 길이가 다릅니다")
        sc = self.split[split]
        combo = np.zeros(sc.universe_mask.shape, dtype=np.float64)
        for f, w in zip(formulas, weights):
            values, valid = self.evaluate(f, split)
            combo += float(w) * daily_zscore(values, valid)
        return combo, sc.universe_mask.copy()
