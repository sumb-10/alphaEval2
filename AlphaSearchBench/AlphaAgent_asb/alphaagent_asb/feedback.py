"""Feedback 지표 — vendored FactorBacktester **원형 그대로** 실행.

지도 원칙 1: LLM이 보는 AnnRet/IC는 원본 FactorBacktester의 산출(첫날 NaN
cost 버그·IC 3자리 반올림 포함)이어야 한다. MiningEvaluator/ASB backtest로의
대체는 numerical parity가 입증된 경우에만 허용 — 기본 설계는 분리 유지.

raw/prompt 분리: `feedback_IC_prompt` = perf["IC"]["total"](원형 round 3자리,
LLM이 실제로 본 값), `feedback_IC_raw` = 반올림 전 ic_series.mean().
AnnRet은 원형이 반올림하지 않으므로 raw == prompt.
"""
from __future__ import annotations

import signal
from contextlib import contextmanager
from typing import Any, Dict

from .vendored_alphaagent.backtester import FactorBacktester
from .diagnostics import has_bare_field


@contextmanager
def step_timeout(seconds: int):
    """후보별 하드 타임아웃 (D-11 — 원형엔 없음; qlib 교착/폭주 계산 방지).
    메인 스레드 SIGALRM 기반 — Slurm/login 단일 프로세스 실행 전제."""
    def _raise(signum, frame):
        raise TimeoutError(f"step timeout after {seconds}s")
    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


class FeedbackEvaluator:
    def __init__(self, start_date: str, end_date: str, instruments, freq: str = "day",
                 timeout_seconds: int = 600):
        self.start_date = start_date
        self.end_date = end_date
        self.instruments = instruments
        self.freq = freq
        self.timeout_seconds = int(timeout_seconds)
        self._memo: Dict[str, Dict[str, Any]] = {}

    def evaluate(self, expr: str) -> Dict[str, Any]:
        """원형 eval_agent.py:84-99와 동일 흐름. 실패 시 error 필드 반환
        (원형: 예외 삼킴 → is_valid=False, summary=에러 문자열)."""
        if expr in self._memo:
            return self._memo[expr]
        try:
            if has_bare_field(expr):
                raise ValueError("bare field name without $ (pre-rejected — D-11)")
            bt = FactorBacktester(factor_expr=expr,
                                  start_date=self.start_date,
                                  end_date=self.end_date,
                                  instruments=self.instruments,
                                  freq=self.freq)
            with step_timeout(self.timeout_seconds):
                bt.load_data()
                perf = bt.calculate_performance().to_dict()
            out = {
                "ok": True,
                "feedback_AnnRet_prompt": perf["AnnRet"]["total"],
                "feedback_AnnRet_raw": perf["AnnRet"]["total"],   # 원형 미반올림
                "feedback_IC_prompt": perf["IC"]["total"],        # 원형 round(...,3)
                "feedback_IC_raw": float(bt.ic_series.mean()),    # 반올림 전
                "error": None,
            }
        except Exception as e:  # noqa: BLE001 — 원형: 예외 삼킴
            out = {"ok": False,
                   "feedback_AnnRet_prompt": None, "feedback_AnnRet_raw": None,
                   "feedback_IC_prompt": None, "feedback_IC_raw": None,
                   "error": str(e)}
        self._memo[expr] = out
        return out
