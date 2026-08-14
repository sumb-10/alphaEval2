"""QD core behavioral descriptors.

개별 alpha가 "어떤 시장 조건에서 어떤 행동을 보이는가"를 기술한다.
core set (v0.1): H(Information Horizon) / V(Volatility Response) /
M(Market Direction Response) / L(Liquidity Response) / B(Activation Breadth) /
R(RRE_qd). structural: signal_coverage / signal_weight_turnover /
liquidity_footprint — 항상 계산·저장하되 PCA core 포함 여부는 manifest 선택.

원칙:
  * 모든 intermediate(IC_1d/5d/10d/20d, IC_high_vol, ...)를 함께 저장 —
    scalar 정의를 나중에 바꿔도 재평가 없이 재집계 가능
  * regime threshold는 train에서 캘리브레이션된 값(SignalContext.regime)을
    valid/test에 그대로 적용 (freeze)
  * normalized contrast D(a,b) = (a-b)/(|a|+|b|+eps); |a|+|b| < threshold면
    denom_small 플래그 기록
  * Breadth/turnover/footprint의 w는 oriented daily z-score 비례 가중
    (20/20 quantile membership은 상수로 퇴화하므로 사용하지 않음)
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from ..config import Config
from ..data.signal_context import SignalContext, daily_zscore
from ..oos.metrics import daily_ic_series, aggregate_ic
from .rre import rre_qd

STRUCTURAL_COLUMNS = ["signal_coverage", "signal_weight_turnover", "liquidity_footprint"]
CORE_COLUMNS = ["horizon", "volatility_response", "market_direction_response",
                "liquidity_response", "activation_breadth", "rre_qd"]


# ---------------------------------------------------------------- 순수 함수
def normalized_contrast(a: float, b: float, eps: float,
                        denom_threshold: float) -> Dict[str, float]:
    if not (np.isfinite(a) and np.isfinite(b)):
        return {"value": float("nan"), "denom_small": True}
    denom = abs(a) + abs(b)
    return {"value": (a - b) / (denom + eps), "denom_small": bool(denom < denom_threshold)}


def horizon_scalar(ic_means: Dict[int, float], reducer: str,
                   denom_threshold: float) -> Dict[str, float]:
    """H reducer (configurable). 기본: weighted_abs_ic — Σ h·|IC_h| / Σ|IC_h|."""
    hs = sorted(ic_means)
    vals = np.array([ic_means[h] for h in hs], dtype=np.float64)
    finite = np.isfinite(vals)
    if reducer == "weighted_abs_ic":
        w = np.abs(vals[finite])
        h_arr = np.array(hs, dtype=np.float64)[finite]
        denom = w.sum()
        if denom < denom_threshold or len(w) == 0:
            return {"value": float("nan"), "denom_small": True}
        return {"value": float((h_arr * w).sum() / denom), "denom_small": False}
    if reducer == "argmax_abs_ic":
        if not finite.any():
            return {"value": float("nan"), "denom_small": True}
        idx = int(np.nanargmax(np.abs(vals)))
        return {"value": float(hs[idx]), "denom_small": False}
    raise ValueError(f"unknown horizon reducer: {reducer!r}")


def activation_breadth(z: np.ndarray, valid: np.ndarray) -> float:
    """일별 N_eff/N_valid의 평균. z는 daily z-score(결측 0)."""
    absw = np.abs(z)
    s = absw.sum(axis=1, keepdims=True)
    p = absw / np.where(s == 0, 1, s)
    with np.errstate(all="ignore"):
        neff = 1.0 / np.maximum((p ** 2).sum(axis=1), 1e-300)
    n_valid = valid.sum(axis=1)
    ok = (n_valid >= 1) & (s[:, 0] > 0)
    if not ok.any():
        return float("nan")
    return float(np.mean(neff[ok] / n_valid[ok]))


def signal_weight_turnover(z: np.ndarray) -> float:
    """w = z/Σ|z| (일별), turnover_t = 0.5·Σ|w_t − w_{t−1}| 의 평균."""
    s = np.abs(z).sum(axis=1, keepdims=True)
    w = z / np.where(s == 0, 1, s)
    if w.shape[0] < 2:
        return float("nan")
    return float(0.5 * np.abs(np.diff(w, axis=0)).sum(axis=1).mean())


def liquidity_footprint(z: np.ndarray, liq_pct: np.ndarray,
                        valid: np.ndarray) -> float:
    """Σ|w_i|·liq_pct_i의 일평균. liq_pct: 일별 percentile (1=최고 유동성)."""
    s = np.abs(z).sum(axis=1, keepdims=True)
    absw = np.abs(z) / np.where(s == 0, 1, s)
    cell = valid & np.isfinite(liq_pct)
    contrib = np.where(cell, absw * liq_pct, 0.0)
    ok = s[:, 0] > 0
    if not ok.any():
        return float("nan")
    return float(contrib[ok].sum(axis=1).mean())


def daily_liquidity_percentile(adv: np.ndarray, universe_mask: np.ndarray) -> np.ndarray:
    """일별 cross-sectional ADV percentile (0~1, 1=최고 유동성). 비유니버스 NaN."""
    a = np.where(universe_mask & np.isfinite(adv), adv, np.nan)
    return pd.DataFrame(a).rank(axis=1, pct=True).to_numpy()


# ---------------------------------------------------------------- evaluator
class QDDescriptorEvaluator:
    def __init__(self, ctx: SignalContext, cfg: Config):
        self.ctx = ctx
        self.cfg = cfg
        self.horizons: List[int] = list(cfg.get("qd.horizons", [1, 5, 10, 20]))
        self.eps = float(cfg.get("qd.contrast_eps", 1e-4))
        self.denom_th = float(cfg.get("qd.contrast_denom_threshold", 1e-3))
        self.reducer = cfg.get("qd.horizon_reducer", "weighted_abs_ic")
        self.liq_split = cfg.get("qd.liquidity.split", "tercile")
        self.use_mid_vol = bool(cfg.get("qd.volatility.use_mid", False))
        self._liq_pct_cache: Dict[str, np.ndarray] = {}

    # ---- split별 조건 마스크 (train-frozen threshold 사용) ----
    def _vol_masks(self, split: str):
        vol = self.ctx.benchmark_vol(split)
        lo = self.ctx.regime["vol_low_threshold"]
        hi = self.ctx.regime["vol_high_threshold"]
        m_low = np.isfinite(vol) & (vol <= lo)
        m_high = np.isfinite(vol) & (vol >= hi)
        return m_high, m_low

    def _dir_masks(self, split: str):
        r = self.ctx.benchmark_returns(split)
        return (np.isfinite(r) & (r > 0)), (np.isfinite(r) & (r < 0))

    def _liq_pct(self, split: str) -> np.ndarray:
        if split not in self._liq_pct_cache:
            self._liq_pct_cache[split] = daily_liquidity_percentile(
                self.ctx.adv(split), self.ctx.split[split].universe_mask)
        return self._liq_pct_cache[split]

    def _liq_cell_masks(self, split: str):
        pct = self._liq_pct(split)
        if self.liq_split == "tercile":
            return (pct >= 2 / 3), (pct <= 1 / 3)
        if self.liq_split == "median":
            return (pct >= 0.5), (pct < 0.5)
        raise ValueError(f"unknown liquidity split: {self.liq_split!r}")

    # ------------------------------------------------------------------
    def compute(self, formula: str, train_sign: int, split: str) -> Dict:
        """formula 하나의 raw descriptor 전부 (intermediate 포함) — 1 row dict."""
        ctx, sc = self.ctx, self.ctx.split[split]
        values, valid = ctx.evaluate(formula, split)      # FormulaEvalError 전파
        oriented = ctx.oriented(values, train_sign)
        row: Dict = {"formula": formula, "split": split, "train_sign": train_sign}

        # H — horizon ICs (전부 저장)
        ic_means: Dict[int, float] = {}
        ic1_series = None
        for k in self.horizons:
            ic = daily_ic_series(oriented, sc.forward[k], valid)
            if k == min(self.horizons):
                ic1_series = ic
            agg = aggregate_ic(ic)
            row[f"IC_{k}d"] = agg["mean"]
            ic_means[k] = agg["mean"]
        h = horizon_scalar(ic_means, self.reducer, self.denom_th)
        row["horizon"] = h["value"]
        row["horizon_denom_small"] = h["denom_small"]

        # V — volatility regime (train-frozen threshold)
        m_high, m_low = self._vol_masks(split)
        ic_hv = float(np.nanmean(ic1_series[m_high])) if m_high.any() else float("nan")
        ic_lv = float(np.nanmean(ic1_series[m_low])) if m_low.any() else float("nan")
        c = normalized_contrast(ic_hv, ic_lv, self.eps, self.denom_th)
        row.update({"IC_high_vol": ic_hv, "IC_low_vol": ic_lv,
                    "volatility_response": c["value"],
                    "volatility_denom_small": c["denom_small"],
                    "n_high_vol_days": int(m_high.sum()),
                    "n_low_vol_days": int(m_low.sum())})

        # M — market direction
        m_up, m_dn = self._dir_masks(split)
        ic_up = float(np.nanmean(ic1_series[m_up])) if m_up.any() else float("nan")
        ic_dn = float(np.nanmean(ic1_series[m_dn])) if m_dn.any() else float("nan")
        c = normalized_contrast(ic_up, ic_dn, self.eps, self.denom_th)
        row.update({"IC_up": ic_up, "IC_down": ic_dn,
                    "market_direction_response": c["value"],
                    "direction_denom_small": c["denom_small"]})

        # L — liquidity (cell-level 분할)
        liq_hi_mask, liq_lo_mask = self._liq_cell_masks(split)
        k1 = min(self.horizons)
        ic_lh = aggregate_ic(daily_ic_series(oriented, sc.forward[k1],
                                             valid & liq_hi_mask))["mean"]
        ic_ll = aggregate_ic(daily_ic_series(oriented, sc.forward[k1],
                                             valid & liq_lo_mask))["mean"]
        c = normalized_contrast(ic_lh, ic_ll, self.eps, self.denom_th)
        row.update({"IC_liq_high": ic_lh, "IC_liq_low": ic_ll,
                    "liquidity_response": c["value"],
                    "liquidity_denom_small": c["denom_small"]})

        # B / structural — oriented z 기반 가중
        z = daily_zscore(oriented, valid)
        row["activation_breadth"] = activation_breadth(z, valid)
        row["signal_weight_turnover"] = signal_weight_turnover(z)
        row["liquidity_footprint"] = liquidity_footprint(z, self._liq_pct(split), valid)
        n_uni = np.maximum(sc.universe_mask.sum(axis=1), 1)
        row["signal_coverage"] = float((valid.sum(axis=1) / n_uni).mean())

        # R — RRE_qd (교집합 재정규화, oriented)
        row.update(rre_qd(oriented, valid))
        return row
