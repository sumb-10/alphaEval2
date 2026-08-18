"""[A] fixed Hall-of-Fame — 원본 HOF decorrelation 버그의 수정판 선택기.

원본 결함 (vendored genetic.py:400-436, 보존):
  * np.argsort(correlations)로 '제거 후보'를 고르지만 실제 pop에서 exact-dup을
    지우지 않아 중복이 최종 pool에 잔존 — seed sweep 실측 strict pool unique
    1–2/10.
  * decorrelation 상관은 qlib 재조회 신호 기반, NaN 상관 쌍의 처리 미정의.

fixed 선택기 (fit 이후 단계 — vendored 무수정, RNG 불소비 → 탐색 재현성 불변):
  1. 최종 population에서 exact-dup(formula 문자열) 선제거 (best effective 유지)
  2. effective fitness 내림차순 상위 hall_of_fame개
  3. NaN-safe decorrelation: 일별 z-score 신호의 공통 finite 셀 Pearson,
     퇴화 쌍(공통 셀 < min_common_cells 또는 corr NaN)은 0으로 간주 + 카운트.
     |corr| 최대 쌍에서 effective 낮은 쪽 제거 → n_components까지.

신호는 signal_fn(주입식 — MiningEvaluator.engine.compute 래핑)으로 계산:
search-창 train-only, HOF의 qlib 재조회 제거(부수 성능 개선).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np


def _daily_zscore(values: np.ndarray, universe_mask: np.ndarray) -> np.ndarray:
    """universe 내 finite 셀만으로 일별 z-score. 표준화 불가한 날은 NaN."""
    v = np.where(universe_mask & np.isfinite(values), values, np.nan).astype(np.float64)
    with np.errstate(all="ignore"):
        m = np.nanmean(v, axis=1, keepdims=True)
        s = np.nanstd(v, axis=1, ddof=0, keepdims=True)
        z = (v - m) / s
    z[~np.isfinite(z)] = np.nan
    return z.astype(np.float32)


def _pair_corr(za: Optional[np.ndarray], zb: Optional[np.ndarray],
               min_common_cells: int) -> Tuple[float, bool]:
    """공통 finite 셀에서 Pearson |corr|. 퇴화 시 (0.0, True)."""
    if za is None or zb is None:
        return 0.0, True
    common = np.isfinite(za) & np.isfinite(zb)
    n = int(common.sum())
    if n < min_common_cells:
        return 0.0, True
    a = za[common].astype(np.float64)
    b = zb[common].astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    if denom == 0 or not math.isfinite(denom):
        return 0.0, True
    r = float((a * b).sum()) / denom
    if not math.isfinite(r):
        return 0.0, True
    return abs(r), False


def select_pool_fixed(candidates: Iterable[Dict],
                      signal_fn: Callable[[str], np.ndarray],
                      universe_mask: np.ndarray,
                      hall_of_fame: int,
                      n_components: int,
                      min_common_cells: int = 100) -> Tuple[List[str], Dict]:
    """최종 population → fixed-HOF pool 선택.

    candidates: {"formula", "effective_fitness"} dict들 (population 순서).
    반환: (선택 formula 리스트 — effective 내림차순, 진단 dict)
    """
    best: Dict[str, float] = {}
    first_pos: Dict[str, int] = {}
    n_input = 0
    for c in candidates:
        f = str(c["formula"])
        eff = float(c["effective_fitness"])
        n_input += 1
        if f not in best:
            best[f] = eff
            first_pos[f] = n_input
        elif eff > best[f]:
            best[f] = eff
    n_dedup_removed = n_input - len(best)

    ranked = sorted(best, key=lambda f: (-best[f], first_pos[f]))
    top = ranked[:int(hall_of_fame)]

    sigs: Dict[str, Optional[np.ndarray]] = {}
    n_signal_failed = 0
    for f in top:
        try:
            sigs[f] = _daily_zscore(np.asarray(signal_fn(f)), universe_mask)
        except Exception:  # noqa: BLE001 — invalid도 population에 있을 수 있음
            sigs[f] = None
            n_signal_failed += 1

    k = len(top)
    corr = np.zeros((k, k))
    degenerate = 0
    for i in range(k):
        for j in range(i + 1, k):
            c, degen = _pair_corr(sigs[top[i]], sigs[top[j]], min_common_cells)
            corr[i, j] = corr[j, i] = c
            degenerate += int(degen)

    alive = list(range(k))
    n_decorr_removed = 0
    while len(alive) > int(n_components):
        sub = corr[np.ix_(alive, alive)]
        np.fill_diagonal(sub, -1.0)
        mx = float(sub.max())
        if mx <= 0:
            drop = alive[-1]                     # 상관 정보 없음 → 최하위 eff 제거
        else:
            i_loc, j_loc = np.unravel_index(int(sub.argmax()), sub.shape)
            a, b = alive[i_loc], alive[j_loc]
            drop = b if best[top[b]] <= best[top[a]] else a
        alive.remove(drop)
        n_decorr_removed += 1

    sel = [top[i] for i in alive]
    final_max = 0.0
    if len(alive) > 1:
        sub = corr[np.ix_(alive, alive)]
        np.fill_diagonal(sub, 0.0)
        final_max = float(np.abs(sub).max())
    diag = {"hof_mode": "fixed", "n_input": n_input,
            "n_dedup_removed": n_dedup_removed, "n_unique": len(best),
            "n_top": k, "n_signal_failed": n_signal_failed,
            "decorr_degenerate_pairs": degenerate,
            "n_decorr_removed": n_decorr_removed,
            "decorr_max_abs_corr_final": final_max}
    return sel, diag


def build_pool_rows(formulas: List[str], evaluator, mode: str, thresholds: Dict,
                    worst: float, seed: int, method_name: str,
                    fitness_opts: Optional[Dict] = None,
                    hof_diag: Optional[Dict] = None) -> List[Dict]:
    """fixed-HOF pool CSV 행 생성 (cli 원본 branch와 동일 스키마 + hof 진단 컬럼).

    IC 컬럼: 원본은 p.fitness_(=effective, parsimony 0)를 쓰므로 fixed에서도
    effective_fitness를 기입 — 스키마 호환.
    """
    from .fitness import apply_constraint
    rows = []
    for f in formulas:
        diag = evaluator.diagnose(f)
        info = apply_constraint(
            mode, diag, thresholds, worst, evaluator.close_signed_ic,
            fitness_metric=evaluator.fitness_metric,
            close_net_sharpe=getattr(evaluator, "close_net_sharpe", float("nan")),
            fitness_opts=fitness_opts,
            close_raw_fitness=getattr(evaluator, "close_raw_fitness", None))
        row = {
            "formula": f,
            "IC": info["effective_fitness"],
            "signed_train_IC": info["signed_train_IC"],
            "train_sign": 1 if info["signed_train_IC"] >= 0 else -1,
            "abs_train_IC": info["abs_train_IC"],
            "raw_fitness": info["raw_fitness"],
            "effective_fitness": info["effective_fitness"],
            "hard_invalid": info["hard_invalid"],
            "research_invalid": info["research_invalid"],
            "validity_pass": info["validity_pass"],
            "invalid_reason": info["invalid_reason"],
            "mean_daily_coverage_ratio": diag.get("mean_daily_coverage_ratio"),
            "median_daily_n_valid": diag.get("median_daily_n_valid"),
            "valid_day_ratio": diag.get("valid_day_ratio"),
            "method": method_name, "constraint_mode": mode, "seed": seed,
        }
        if hof_diag:
            row.update({k: hof_diag[k] for k in
                        ("hof_mode", "n_dedup_removed",
                         "decorr_degenerate_pairs", "n_decorr_removed",
                         "decorr_max_abs_corr_final")})
        rows.append(row)
    return rows
