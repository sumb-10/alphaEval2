"""PFS — Perturbation Fidelity Score. mode를 명시적으로 분리한다.

배경 (조사 확정 — AlphaEval/docs/new_Eval_blueprint_v2.md §D):

  * AlphaEval 공개코드(legacy): noise를 **alpha 출력**에 **곱셈**으로 주고
    (S' = S·(1+ε)) **Pearson**으로 상관 — 논문과 3중 불일치. 원본은 시드가
    없어 비재현이며, 여기서는 재현 가능한 legacy 재구현(시드 고정)을 둔다.
  * 논문(paper_literal): S' = α(X + ε) — **raw feature tensor**에 덧셈,
    **Spearman**, σ = market index의 average daily volatility,
    Student-t(ν=3)를 Gaussian과 동일 std로 rescale, PFS = min(G, t).
    **주의: 논문은 heterogeneous raw feature scale의 normalization을 정의하지
    않는다 — literal 구현에는 scale ambiguity가 존재한다** (σ≈지수 일변동성
    스케일의 덧셈 노이즈는 $volume 같은 필드에는 사실상 무영향, $change에는
    지배적). 이 사실은 METRICS.md에 명기된다.
  * relative_input (**experimental**): X·(1+ε) — scale-free 입력 섭동.
    연구 semantics 미확정이므로 production default로 사용하지 않는다.

결정론: 모든 noise는 (market, split, noise_type, seed, draw_id,
dataset_version, mode) 키의 `np.random.default_rng`로 생성되어 method와
formula에 무관하게 **동일한 perturbed market tensor**가 공유된다.
formula마다 noise를 새로 만들지 않는다.

집계: daily cross-sectional Spearman(S_t, S'_t)의 기간 평균 → K draws 평균.
(flatten-all-cells 방식이 아님 — 문서화.)
PFS는 부호 반전에 불변이므로 orientation은 적용하지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..config import Config
from ..data.signal_context import SignalContext
from ..data.qlib_provider import FormulaEngine, FormulaEvalError, FEATURE_LIST
from ..oos.metrics import daily_rank_ic_series, masked_daily_corr

PFS_MODES = ("legacy_alphaeval", "paper_literal", "relative_input")
EXPERIMENTAL_MODES = ("relative_input",)


def _rng_for(key_parts: Sequence) -> np.random.Generator:
    digest = hashlib.sha256("|".join(str(p) for p in key_parts).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def _draw_noise(rng: np.random.Generator, shape, noise_type: str,
                sigma: float, dof: int) -> np.ndarray:
    if noise_type == "gaussian":
        return rng.normal(0.0, sigma, size=shape)
    if noise_type == "student_t":
        # t(ν)를 Gaussian과 동일 std로 rescale (provenance: noise_proc.py와 동일 식)
        return rng.standard_t(dof, size=shape) * sigma * np.sqrt((dof - 2) / dof)
    raise ValueError(f"unknown noise type: {noise_type!r}")


class PerturbationPolicy:
    """raw feature panel 섭동 정책 (pluggable)."""
    name = "base"
    experimental = False

    def perturb(self, panels: Dict[str, np.ndarray], rng: np.random.Generator,
                sigma: float, dof: int, noise_type: str) -> Dict[str, np.ndarray]:
        raise NotImplementedError


class PaperLiteralPolicy(PerturbationPolicy):
    """X + ε — 논문 문자적 정의. scale ambiguity 문서화 필수."""
    name = "paper_literal"

    def perturb(self, panels, rng, sigma, dof, noise_type):
        out = {}
        for f in FEATURE_LIST:
            eps = _draw_noise(rng, panels[f].shape, noise_type, sigma, dof)
            out[f] = (panels[f] + eps).astype(panels[f].dtype)
        return out


class RelativeInputPolicy(PerturbationPolicy):
    """X·(1+ε) — experimental. production default 금지."""
    name = "relative_input"
    experimental = True

    def perturb(self, panels, rng, sigma, dof, noise_type):
        out = {}
        for f in FEATURE_LIST:
            eps = _draw_noise(rng, panels[f].shape, noise_type, sigma, dof)
            out[f] = (panels[f] * (1.0 + eps)).astype(panels[f].dtype)
        return out


_POLICIES = {"paper_literal": PaperLiteralPolicy, "relative_input": RelativeInputPolicy}


class PFSEvaluator:
    def __init__(self, ctx: SignalContext, cfg: Config,
                 sigma_override: Optional[float] = None):
        self.ctx = ctx
        self.cfg = cfg
        self.mode: str = cfg.get("pfs.mode", "paper_literal")
        if self.mode not in PFS_MODES:
            raise ValueError(f"pfs.mode must be one of {PFS_MODES}")
        self.k_draws = int(cfg.get("pfs.k_draws", 3))
        self.seed = int(cfg.get("pfs.seed", 0))
        self.dof = int(cfg.get("pfs.student_t_dof", 3))
        self.dataset_version = str(cfg.get("dataset.provider_uri", ""))
        # σ: train benchmark 일수익률 std (train-frozen) — 논문의
        # "corresponding market index average daily volatility" 해석
        if sigma_override is not None:
            self.sigma = float(sigma_override)
        else:
            r = ctx.benchmark_returns("train")
            self.sigma = float(np.nanstd(r[np.isfinite(r)], ddof=1))
        self._pert_engine_cache: Dict = {}

    # ------------------------------------------------------------------
    def noise_config(self) -> Dict:
        return {"pfs_mode": self.mode, "sigma": self.sigma,
                "sigma_def": self.cfg.get("pfs.sigma_def"),
                "k_draws": self.k_draws, "seed": self.seed,
                "student_t_dof": self.dof,
                "experimental": self.mode in EXPERIMENTAL_MODES}

    def _perturbed_engine(self, split: str, noise_type: str, draw: int) -> FormulaEngine:
        key = (split, noise_type, draw)
        if key in self._pert_engine_cache:
            return self._pert_engine_cache[key]
        rng = _rng_for([self.ctx.market, split, noise_type, self.seed, draw,
                        self.dataset_version, self.mode])
        policy = _POLICIES[self.mode]()
        eng = copy.copy(self.ctx.engine)               # dates/columns/coverage 공유
        eng.panels = policy.perturb(self.ctx.engine.panels, rng,
                                    self.sigma, self.dof, noise_type)
        eng._frame_cache = {}
        self._pert_engine_cache[key] = eng
        return eng

    # ------------------------------------------------------------------
    def _daily_spearman_mean(self, s: np.ndarray, s2: np.ndarray,
                             valid: np.ndarray) -> float:
        r = daily_rank_ic_series(s, s2, valid)
        finite = r[np.isfinite(r)]
        return float(finite.mean()) if len(finite) else float("nan")

    def _daily_pearson_mean(self, s: np.ndarray, s2: np.ndarray,
                            valid: np.ndarray) -> float:
        r = masked_daily_corr(s, s2, valid)
        finite = r[np.isfinite(r)]
        return float(finite.mean()) if len(finite) else float("nan")

    def evaluate_factor(self, formula: str, split: str = "test") -> Dict:
        """formula 하나의 PFS 결과 (모드별 정의 준수). 결과 키에 mode 명시."""
        sc = self.ctx.split[split]
        values, valid = self.ctx.evaluate(formula, split)
        row: Dict = {"formula": formula, "split": split}
        row.update(self.noise_config())

        if self.mode == "legacy_alphaeval":
            # S' = S·(1+ε), Pearson (공개코드 재현 — 시드 고정만 추가)
            per_type: Dict[str, List[float]] = {"gaussian": [], "student_t": []}
            for noise_type in ("gaussian", "student_t"):
                for d in range(self.k_draws):
                    rng = _rng_for([self.ctx.market, split, noise_type,
                                    self.seed, d, self.dataset_version, self.mode])
                    eps = _draw_noise(rng, values.shape, noise_type,
                                      self.sigma, self.dof)
                    s2 = (values * (1.0 + eps)).astype(np.float32)
                    per_type[noise_type].append(
                        self._daily_pearson_mean(values, s2, valid))
            g, t = per_type["gaussian"], per_type["student_t"]
            row.update({
                "PFS_Gaussian_legacy": float(np.nanmean(g)),
                "PFS_t_legacy": float(np.nanmean(t)),
                "PFS_min_legacy": float(min(np.nanmean(g), np.nanmean(t))),
                "PFS_Gaussian_std_across_draws": float(np.nanstd(g)),
                "PFS_t_std_across_draws": float(np.nanstd(t)),
            })
            return row

        # 입력 섭동 모드: S' = α(perturbed X) — 모든 formula가 동일 텐서 공유
        per_type = {"gaussian": [], "student_t": []}
        fail_reason = None
        for noise_type in ("gaussian", "student_t"):
            for d in range(self.k_draws):
                eng = self._perturbed_engine(split, noise_type, d)
                try:
                    s2 = eng.compute(formula, sc.start, sc.end)
                except FormulaEvalError as e:
                    fail_reason = e.reason
                    per_type[noise_type].append(float("nan"))
                    continue
                v2 = valid & np.isfinite(s2)
                per_type[noise_type].append(
                    self._daily_spearman_mean(values, s2, v2))
        g, t = per_type["gaussian"], per_type["student_t"]
        suffix = "" if self.mode == "paper_literal" else f"_{self.mode}"
        row.update({
            f"PFS_Gaussian{suffix}": float(np.nanmean(g)),
            f"PFS_t{suffix}": float(np.nanmean(t)),
            f"PFS_min{suffix}": float(min(np.nanmean(g), np.nanmean(t))),
            "PFS_Gaussian_std_across_draws": float(np.nanstd(g)),
            "PFS_t_std_across_draws": float(np.nanstd(t)),
            "pfs_fail_reason": fail_reason,
        })
        return row
