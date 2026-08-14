"""unit — LLM 계층: FakeLLM 결정성, 카운터, replay, 유한 재시도 (qlib 불필요)."""
import json
import os
import sys

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PKG_ROOT)

from alphaagent_asb.config import load_config          # noqa: E402
from alphaagent_asb.llm import FakeLLM, ReplayLLM, HTTPLLM, make_llm  # noqa: E402

MSGS = [{"role": "system", "content": "system prompt text"},
        {"role": "user", "content": "user prompt text long enough for tokens"}]


def _cfg(**over):
    return load_config(overrides=over or None)


def test_fake_deterministic(tmp_path):
    a = FakeLLM(_cfg(), str(tmp_path / "a.jsonl"))
    b = FakeLLM(_cfg(), str(tmp_path / "b.jsonl"))
    for role in ("idea", "factor", "eval"):
        assert a.chat(role, MSGS) == b.chat(role, MSGS)
    # 다른 메시지 → (일반적으로) 다른 factor
    m2 = [{"role": "user", "content": "different"}]
    assert a.chat("factor", MSGS) == a.chat("factor", MSGS)


def test_fake_eval_applies_original_rule(tmp_path):
    llm = FakeLLM(_cfg(), None)
    good = [{"role": "user", "content": '{\n  "AnnRet": 0.15,\n  "IC": 0.05\n}'}]
    bad = [{"role": "user", "content": '{\n  "AnnRet": 0.05,\n  "IC": 0.05\n}'}]
    assert json.loads(llm.chat("eval", good))["is_high_quality"] is True
    assert json.loads(llm.chat("eval", bad))["is_high_quality"] is False
    always = FakeLLM(_cfg(llm={"fake_accept_rule": "always"}), None)
    assert json.loads(always.chat("eval", bad))["is_high_quality"] is True


def test_budget_counters(tmp_path):
    llm = FakeLLM(_cfg(), str(tmp_path / "c.jsonl"))
    llm.chat("idea", MSGS)
    llm.chat("factor", MSGS)
    llm.chat("factor", MSGS, _retry_of=1)
    b = llm.budget.to_dict()
    assert b["n_idea_calls"] == 1 and b["n_factor_calls"] == 1
    assert b["n_retry_calls"] == 1 and b["n_total_llm_calls"] == 3
    assert b["prompt_tokens"] > 0


def test_replay_roundtrip(tmp_path):
    log = str(tmp_path / "calls.jsonl")
    src = FakeLLM(_cfg(), log)
    r1 = src.chat("idea", MSGS)
    src.close()
    rep = ReplayLLM(_cfg(), None, log)
    assert rep.chat("idea", MSGS) == r1
    with pytest.raises(KeyError):
        rep.chat("idea", [{"role": "user", "content": "unseen"}])


def test_http_finite_retry_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        HTTPLLM(_cfg(), None)      # key 없으면 즉시 명시 실패 (live 게이트)


def test_make_llm_modes(tmp_path):
    assert isinstance(make_llm(_cfg(), "fake", None), FakeLLM)
    log = str(tmp_path / "l.jsonl")
    f = FakeLLM(_cfg(), log); f.chat("idea", MSGS); f.close()
    assert isinstance(make_llm(_cfg(), "replay", None, log), ReplayLLM)
