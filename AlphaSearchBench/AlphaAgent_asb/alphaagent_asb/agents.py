"""3-agent 포팅 — 주입식 LLM 클라이언트 + parity|safe formatting.

provenance: vendored_alphaagent/{idea_agent.py, factor_agent.py, eval_agent.py}.
parity mode는 원형 동작을 유지한다: dict가 프롬프트에 repr로 삽입되고
(alphaagent.py:76,96 계약), idea JSON 파싱 실패는 빈 아이디어로 조용히
전파된다. safe mode만 명시적 조립·strict 파싱을 쓴다 (PROVENANCE D-6).
편차: 재시도 유한화(D-1), enhance 비JSON ValueError는 호출자에서 seed 단위
격리(D-2 — loop.py).
"""
from __future__ import annotations

import ast
import json
from typing import Any, Dict, Optional, Tuple

from . import prompts


class IdeaAgentA:
    def __init__(self, llm, mode: str = "parity"):
        self.llm = llm
        self.mode = mode

    def generate(self, context=None, hypothesis=None, previous_expr=None,
                 eval_report=None) -> Dict[str, str]:
        if context is not None and hypothesis is None:
            # 신규 아이디어 (idea_agent.py:40-58)
            content = self.llm.chat("idea", [
                {"role": "system", "content": prompts.IDEA_SYSTEM_NEW},
                {"role": "user", "content": prompts.idea_user_new(context)}]).strip()
            return self.parse_response(content)
        elif hypothesis is not None and previous_expr is not None and eval_report is not None:
            # 개선 (idea_agent.py:72-97) — parity: hypothesis 자리에 idea dict가
            # 그대로 들어옴(repr 문자열화). safe: 명시적 문자열 조립.
            if self.mode == "safe" and isinstance(hypothesis, dict):
                hypothesis = hypothesis.get("hypothesis", "")
            content = self.llm.chat("idea", [
                {"role": "system", "content": prompts.IDEA_SYSTEM_ENHANCE},
                {"role": "user", "content": prompts.idea_user_enhance(
                    context, hypothesis, previous_expr, eval_report)}]).strip()
            start = content.find('{')
            end = content.rfind('}') + 1
            content = content[start:end]
            if not content.startswith('{') or not content.endswith('}'):
                # 원형: ValueError → 호출자(loop)가 seed 단위로 격리 (D-2)
                raise ValueError("LLM response does not match expected JSON format.")
            return self.parse_response(content)
        else:
            raise ValueError(f"context: {context}, hypothesis: {hypothesis}, "
                             f"previous_expr: {previous_expr}, eval_report: {eval_report} ")

    def parse_response(self, text: str) -> Dict[str, str]:
        # idea_agent.py:101-122 — parity: 실패 시 빈 아이디어 조용히 반환
        try:
            data = json.loads(text)
            hypothesis = data.get("hypothesis", "").strip()
            description = data.get("description", "").strip()
            if not hypothesis or not description:
                raise ValueError("Missing hypothesis or description in response.")
        except Exception as e:  # noqa: BLE001 — 원형 동작
            if self.mode == "safe":
                raise
            return {"hypothesis": "", "description": ""}
        return {"hypothesis": hypothesis, "description": description}


class FactorAgentA:
    def __init__(self, llm, mode: str = "parity", max_retries: int = 5):
        self.llm = llm
        self.mode = mode
        self.max_retries = max_retries   # D-1: 원형 무한재귀의 의도값 유한화

    def generate(self, description) -> Tuple[str, Optional[ast.AST]]:
        # factor_agent.py:32-66 — parity: description 자리에 idea dict(repr)
        if self.mode == "safe" and isinstance(description, dict):
            description = description.get("description", "")
        for attempt in range(self.max_retries):
            try:
                content = self.llm.chat(
                    "factor",
                    [{"role": "system", "content": prompts.FACTOR_SYSTEM},
                     {"role": "user", "content": prompts.factor_user(description)}],
                    _retry_of=None if attempt == 0 else attempt)
                expr = content.strip().replace('"', "")
                expr_ast = self.parse_ast(expr.replace("$", ""))
                return expr, expr_ast
            except Exception as e:  # noqa: BLE001 — 원형: LLM/파싱 예외 재시도
                if attempt >= self.max_retries - 1:
                    return "", None       # 원형 실패 반환값
        return "", None

    def parse_ast(self, expr: str) -> Optional[ast.AST]:
        # factor_agent.py:68-73 — parity: 문법 오류 시 None 반환하고 진행
        try:
            return ast.parse(expr, mode='eval')
        except SyntaxError:
            if self.mode == "safe":
                raise
            return None


class EvalAgentA:
    """원형 EvalAgent의 LLM 판정부 (백테스트는 feedback.py가 담당)."""

    def __init__(self, llm, mode: str = "parity"):
        self.llm = llm
        self.mode = mode

    def assess(self, perf: Dict[str, Any], expr: str) -> Dict[str, Any]:
        # eval_agent.py:114-152
        perf_str = json.dumps(perf, indent=2)
        reply = self.llm.chat("eval", [
            {"role": "system", "content": prompts.EVAL_SYSTEM},
            {"role": "user", "content": prompts.eval_user(perf_str, expr)}]).strip()
        try:
            report = json.loads(reply)
        except Exception:  # noqa: BLE001 — 원형: 실패 시 None verdict
            report = {"summary": "", "recommendation": "", "is_high_quality": None}
        return report
