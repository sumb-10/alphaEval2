"""ASB 진단 래퍼 — FormulaEngine이 못 읽는 문법은 qlib native로 fallback.

배경: gplearn_asb의 MiningEvaluator(FormulaEngine)는 GP가 생성하는 함수형
문법(Add/Div/Mean...)만 파싱한다. AlphaAgent는 qlib D.features 문법 전체
(infix 산술 `($low-$high)/$close`, 비교 `>` `<`, Corr/Cov/Rank, 숫자 리터럴)
를 쓰므로, 파싱 실패 시 **qlib native 쿼리로 신호를 얻어 동일한
validity/IC 의미론**(같은 universe mask·label·_daily_ic)으로 진단한다.
→ ASB core 무수정, GP와 진단 의미론 동일(교차 비교 성립).

trajectory에 diagnostics_source ∈ {formula_engine, qlib_fallback,
eval_failed}를 기록한다.
"""
from __future__ import annotations

import re
from typing import Any, Dict

import numpy as np

_BARE_FIELD = re.compile(r"(?<!\$)\b(open|high|low|close|volume|vwap|amount|factor)\b")


def has_bare_field(formula: str) -> bool:
    """$ 없는 필드명 존재 여부 — qlib에 던지면 종목별 NameError 폭주로
    joblib 교착을 유발할 수 있어 사전 차단한다 (D-11)."""
    return bool(_BARE_FIELD.search(formula or ""))


class DiagnosticsWithQlibFallback:
    def __init__(self, mining_eval):
        self.ev = mining_eval                  # gplearn_asb.evaluator.MiningEvaluator
        self._memo: Dict[str, Dict[str, Any]] = {}

    def diagnose(self, formula: str) -> Dict[str, Any]:
        if formula in self._memo:
            return self._memo[formula]
        diag = dict(self.ev.diagnose(formula))
        if not diag.get("eval_failed"):
            diag["diagnostics_source"] = "formula_engine"
        else:
            fb = self._qlib_fallback(formula)
            if fb is not None:
                diag = fb
                diag["diagnostics_source"] = "qlib_fallback"
            else:
                diag["diagnostics_source"] = "eval_failed"
        self._memo[formula] = diag
        return diag

    def _qlib_fallback(self, formula: str):
        """qlib D.features로 신호 계산 → engine 격자로 정렬 → 동일 의미론 진단."""
        if has_bare_field(formula):
            return None          # D-11: bare-name은 qlib 교착 위험 — 즉시 실패 처리
        from qlib.data import D
        from alphasearchbench.validity.metrics import compute_validity_stats
        ev = self.ev
        try:
            raw = D.features(D.instruments(market="all"), [formula],
                             start_time=ev.search_start, end_time=ev.search_end,
                             freq="day").iloc[:, 0]
            wide = raw.unstack(level="instrument")
            wide = wide.reindex(index=ev.sel_dates, columns=ev.engine.columns)
            values = wide.to_numpy().astype(np.float32)
        except Exception:  # noqa: BLE001 — qlib도 못 읽으면 진짜 eval 실패
            return None
        stats = compute_validity_stats(values, ev.universe_mask)
        ic, n_obs, ic_std = ev._daily_ic(values)
        hard_reason = None
        if stats["n_valid_cells"] == 0:
            hard_reason = "all_nonfinite"
        elif stats["n_correlatable_days"] == 0:
            hard_reason = "no_correlatable_day"
        elif n_obs == 0:
            hard_reason = "zero_ic_observations"
        out: Dict[str, Any] = {"formula": formula}
        out.update(stats)
        from gplearn_asb.evaluator import _ic_tstat
        out.update({"signed_train_IC": float(ic), "abs_train_IC": float(abs(ic)),
                    "ic_daily_std": float(ic_std),
                    "ic_tstat": _ic_tstat(ic, n_obs, ic_std),
                    "n_ic_obs": int(n_obs), "eval_failed": False,
                    "hard_invalid": hard_reason is not None,
                    "invalid_reason": hard_reason})
        return out

    @property
    def close_signed_ic(self):
        return self.ev.close_signed_ic

    @property
    def universe_hash(self):
        return self.ev.universe_hash
