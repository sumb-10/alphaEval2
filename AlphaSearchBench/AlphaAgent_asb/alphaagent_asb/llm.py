"""LLM 계층 — OpenAI-호환 thin HTTP client + FakeLLM + Replay.

재현성 계층: FakeLLM(결정적) < Replay(기록 재생, 결정적) < HTTP(live —
비결정, 전량 로깅으로 사후 감사). 모든 클라이언트는 동일 인터페이스:

    chat(role, messages) -> str        # role ∈ {"idea","factor","eval"}

- 콜 카운터: role별 + retry 분리 (지도 원칙 4 — budget은 후보 수와 콜 수 분리)
- 전량 로그: llm_calls.jsonl (한 콜 = 한 줄: role/model/temperature/messages/
  response/usage/retry_of) → --replay 입력으로 재사용 가능
- D-1: 재시도는 유한 (config llm.max_retries)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional


class LLMBudget:
    def __init__(self, price_prompt=None, price_completion=None):
        self.calls = {"idea": 0, "factor": 0, "eval": 0}
        self.retry_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._pp, self._pc = price_prompt, price_completion

    def record(self, role: str, usage: Optional[Dict], is_retry: bool):
        if is_retry:
            self.retry_calls += 1
        else:
            self.calls[role] = self.calls.get(role, 0) + 1
        if usage:
            self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)

    def to_dict(self) -> Dict[str, Any]:
        total = sum(self.calls.values()) + self.retry_calls
        cost = None
        if self._pp is not None and self._pc is not None:
            cost = (self.prompt_tokens / 1000 * float(self._pp)
                    + self.completion_tokens / 1000 * float(self._pc))
        return {"n_idea_calls": self.calls.get("idea", 0),
                "n_factor_calls": self.calls.get("factor", 0),
                "n_eval_calls": self.calls.get("eval", 0),
                "n_retry_calls": self.retry_calls,
                "n_total_llm_calls": total,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "estimated_cost": cost}


def _load_key_from_env_file(cfg, key_env: str) -> Optional[str]:
    """dotenv 스타일 파일에서 key_env 값을 읽는다 (값은 어디에도 로그하지 않음).

    탐색 순서: config `llm.env_file` → AlphaEval repo 루트 `.env`
    (.gitignore로 보호되는 사용자 관행 지원). 형식: `KEY=...` 또는
    `export KEY=...`, `#` 주석/빈 줄 무시, 값의 양끝 따옴표 제거.
    """
    from .config import resolve_paths
    candidates = []
    if cfg.get("llm.env_file"):
        candidates.append(str(cfg.get("llm.env_file")))
    candidates.append(os.path.join(resolve_paths()["repo_root"], ".env"))
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export "):]
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key_env:
                        v = v.strip().strip('"').strip("'")
                        if v:
                            os.environ[key_env] = v   # 프로세스 로컬
                            return v
        except OSError:
            continue
    return None


class _LoggedLLM:
    """공통: 호출 로그 + budget. 서브클래스는 _complete()만 구현."""

    def __init__(self, cfg, log_path: Optional[str]):
        self.models = {r: cfg.get(f"llm.models.{r}") for r in ("idea", "factor", "eval")}
        self.temps = {r: float(cfg.get(f"llm.temperatures.{r}")) for r in ("idea", "factor", "eval")}
        self.budget = LLMBudget(cfg.get("llm.price_per_1k.prompt"),
                                cfg.get("llm.price_per_1k.completion"))
        self._log_path = log_path
        self._call_id = 0
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            self._log_fh = open(log_path, "a", encoding="utf-8")
        else:
            self._log_fh = None

    def chat(self, role: str, messages: List[Dict[str, str]],
             _retry_of: Optional[int] = None) -> str:
        content, usage = self._complete(role, messages)
        self._call_id += 1
        self.budget.record(role, usage, is_retry=_retry_of is not None)
        if self._log_fh:
            rec = {"call_id": self._call_id, "role": role,
                   "model": self.models.get(role), "temperature": self.temps.get(role),
                   "messages": messages, "response": content, "usage": usage,
                   "retry_of": _retry_of}
            self._log_fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._log_fh.flush()
        return content

    def close(self):
        if self._log_fh:
            self._log_fh.close()

    def _complete(self, role, messages):  # pragma: no cover
        raise NotImplementedError


class HTTPLLM(_LoggedLLM):
    """OpenAI-호환 chat.completions thin client (requests). D-1: 유한 재시도."""

    def __init__(self, cfg, log_path: Optional[str]):
        super().__init__(cfg, log_path)
        self.base_url = str(cfg.get("llm.base_url")).rstrip("/")
        key_env = cfg.get("llm.api_key_env", "OPENAI_API_KEY")
        self.api_key = os.environ.get(key_env) or _load_key_from_env_file(cfg, key_env)
        if not self.api_key:
            raise RuntimeError(
                f"환경변수 {key_env}가 없고 .env 파일에서도 찾지 못했습니다 "
                f"(탐색: llm.env_file 또는 AlphaEval/.env — "
                "live LLM run은 사용자 승인·API key 필요)")
        self.request_seed = cfg.get("llm.request_seed")
        self.max_retries = int(cfg.get("llm.max_retries", 5))
        self.timeout = float(cfg.get("llm.timeout_seconds", 120))
        self.temperature_fallback_models: set = set()   # D-10: temp 미지원 모델 기록

    def _complete(self, role, messages):
        import requests
        model = self.models[role]
        payload = {"model": model, "messages": messages}
        if model not in self.temperature_fallback_models:
            payload["temperature"] = self.temps[role]
        if self.request_seed is not None:
            payload["seed"] = int(self.request_seed)
        last_err = None
        for attempt in range(self.max_retries):
            try:
                r = requests.post(f"{self.base_url}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.api_key}",
                                           "Content-Type": "application/json"},
                                  json=payload, timeout=self.timeout)
                if r.status_code == 400 and "temperature" in payload:
                    msg = ""
                    try:
                        msg = (r.json().get("error") or {}).get("message", "")
                    except Exception:  # noqa: BLE001
                        pass
                    if "temperature" in msg:
                        # D-10: 모델이 원형 온도 프로필을 거부 — temperature를
                        # 빼고 재시도(모델 기본값 사용). 강제 편차로 기록됨.
                        self.temperature_fallback_models.add(model)
                        payload.pop("temperature")
                        continue
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    # 4xx(429 제외)는 재시도 무의미 — 본문 포함 즉시 실패
                    try:
                        msg = (r.json().get("error") or {}).get("message", "")
                    except Exception:  # noqa: BLE001
                        msg = r.text[:200]
                    raise RuntimeError(f"LLM 4xx ({r.status_code}): {msg}")
                r.raise_for_status()
                data = r.json()
                return (data["choices"][0]["message"]["content"],
                        data.get("usage"))
            except RuntimeError:
                raise
            except Exception as e:  # noqa: BLE001 — 429/5xx/네트워크만 재시도
                last_err = e
                if attempt < self.max_retries - 1:
                    self.budget.retry_calls += 1
                    time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"LLM 호출이 {self.max_retries}회 모두 실패: {last_err}")


class FakeLLM(_LoggedLLM):
    """결정적 mock — messages md5로 템플릿 선택. 개발·테스트·smoke 전용.

    eval 역할은 원형 규칙("annual return > 10% and IC > 0.03")을 프롬프트의
    수치에서 파싱해 그대로 적용한다 → verdict가 결정적이고 원형 판정 규칙과
    일관된다.
    """

    FACTOR_POOL = [
        "($close - $open) / $open",
        "Mean($close, 5) / $close",
        "Std($volume, 10) / ($volume + 1e-12)",
        "($high - $low) / $close",
        "Ref($close, 3) / $close",
        "Corr($close, $volume, 10)",
        "NotAnOperator($close, 5)",          # 의도적 invalid — 실패 경로 검증
        "Sum($volume, 20) / $volume",
    ]
    IDEA_TMPL = ('{{ "hypothesis": "fake hypothesis {h}", '
                 '"description": "fake factor description {h}" }}')

    def __init__(self, cfg, log_path):
        super().__init__(cfg, log_path)
        # 테스트 전용 노브: original(원형 판정 규칙) | always | never
        self.accept_rule = str(cfg.get("llm.fake_accept_rule", "original"))

    def _key(self, messages) -> int:
        return int(hashlib.md5(json.dumps(messages, sort_keys=True,
                                          ensure_ascii=False).encode()).hexdigest(), 16)

    def _complete(self, role, messages):
        k = self._key(messages)
        usage = {"prompt_tokens": sum(len(m["content"]) // 4 for m in messages),
                 "completion_tokens": 32}
        if role == "idea":
            return self.IDEA_TMPL.format(h=k % 1000), usage
        if role == "factor":
            return self.FACTOR_POOL[k % len(self.FACTOR_POOL)], usage
        if role == "eval":
            user = messages[-1]["content"]
            def _num(name):
                m = re.search(rf'"{name}":\s*(-?[0-9.eE+-]+|NaN)', user)
                try:
                    return float(m.group(1)) if m else float("nan")
                except ValueError:
                    return float("nan")
            annret, ic = _num("AnnRet"), _num("IC")
            if self.accept_rule == "always":
                hq = True
            elif self.accept_rule == "never":
                hq = False
            else:
                hq = bool(annret > 0.10 and ic > 0.03)   # 원형 판정 규칙
            return json.dumps({
                "summary": f"fake summary (AnnRet={annret}, IC={ic})",
                "recommendation": "fake recommendation: improve smoothing",
                "is_high_quality": hq}), usage
        raise ValueError(f"unknown role: {role}")


class ReplayLLM(_LoggedLLM):
    """이전 run의 llm_calls.jsonl을 messages-hash 키로 재생 — 결정적 재실행."""

    def __init__(self, cfg, log_path: Optional[str], replay_path: str):
        super().__init__(cfg, log_path)
        self._bank: Dict[str, List[str]] = {}
        with open(replay_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                key = self._key(rec["role"], rec["messages"])
                self._bank.setdefault(key, []).append(rec["response"])
        self._cursor: Dict[str, int] = {}

    @staticmethod
    def _key(role, messages) -> str:
        return hashlib.md5((role + json.dumps(messages, sort_keys=True,
                            ensure_ascii=False)).encode()).hexdigest()

    def _complete(self, role, messages):
        key = self._key(role, messages)
        if key not in self._bank:
            raise KeyError(f"replay 로그에 없는 호출입니다 (role={role}) — "
                           "결정적 재생 불가")
        i = self._cursor.get(key, 0)
        responses = self._bank[key]
        self._cursor[key] = min(i + 1, len(responses) - 1)
        return responses[min(i, len(responses) - 1)], None


def make_llm(cfg, mode: str, log_path: Optional[str],
             replay_path: Optional[str] = None):
    if mode == "fake":
        return FakeLLM(cfg, log_path)
    if mode == "replay":
        return ReplayLLM(cfg, log_path, replay_path)
    if mode == "live":
        return HTTPLLM(cfg, log_path)
    raise ValueError(f"unknown llm mode: {mode}")
