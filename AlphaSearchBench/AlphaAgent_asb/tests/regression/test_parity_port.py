"""regression — 프롬프트/유사도/parity formatting의 원형 동등성.

원형 모듈은 openai 모듈 전역에 의존하므로 import 전에 스텁을 주입한다
(참조 비교 전용 — 원본 무수정).
"""
import ast
import os
import sys
import types

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ASB_ROOT = os.path.dirname(_PKG_ROOT)
_REPO_ROOT = os.path.dirname(_ASB_ROOT)
for p in (_PKG_ROOT, _REPO_ROOT):
    sys.path.insert(0, p)

# openai 스텁 (원형 모듈 import 용 — 호출은 하지 않음)
if "openai" not in sys.modules:
    stub = types.ModuleType("openai")
    stub.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=None))
    stub.api_key = ""
    sys.modules["openai"] = stub

from alphaagent_asb import prompts                       # noqa: E402
from alphaagent_asb.similarity import (                  # noqa: E402
    ast_similarity_by_common_subtree_ast as ours)

# 원형 모듈 (참조 import — Alphaagent에는 __init__.py가 없어 파일 로드 방식 사용)
import importlib.util


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_REPO_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_orig_idea = _load("orig_idea", "Alphaagent/agents/idea_agent.py")
_orig_factor = _load("orig_factor", "Alphaagent/agents/factor_agent.py")


def test_prompt_strings_match_original():
    ia = _orig_idea.IdeaAgent()
    assert prompts.IDEA_SYSTEM_NEW == ia.system_prompt_new
    assert prompts.IDEA_SYSTEM_ENHANCE == ia.system_prompt_enhance
    fa = _orig_factor.FactorAgent()
    assert prompts.FACTOR_FUNCTION_DEFINITION == fa.function_definition
    # FactorAgent system prompt 재조립 (factor_agent.py:36-41)
    expected_system = (
        "You are a quant researcher assistant. Given a natural language description of a factor idea, "
        "your job is to output a valid expression using ONLY the allowed features and functions.\n"
        + fa.function_definition +
        "\nOutput only a single-line expression string. Do NOT explain or format as code."
    )
    assert prompts.FACTOR_SYSTEM == expected_system


def test_eval_system_prompt_matches_source_text():
    # eval_agent.py의 system_prompt는 메서드 로컬 — 소스 텍스트로 대조
    src = open(os.path.join(_REPO_ROOT, "Alphaagent/agents/eval_agent.py")).read()
    for line in ["You are a quantitative investment assistant.",
                 "When the annual return > 10% and IC > 0.03, it is considered a high-quality factor.",
                 "The similarity the lower, the better."]:
        assert line in src and line in prompts.EVAL_SYSTEM


def test_parity_dict_repr_formatting():
    """parity: idea dict가 f-string에 repr로 들어가는 원형 계약(alphaagent.py:76,96)."""
    idea = {"hypothesis": "h1", "description": "d1"}
    # 원형 factor_agent.py:43 — f"Description: {description}\n..."
    assert prompts.factor_user(idea) == (f"Description: {idea}\n"
                                         f"Generate the factor expression:")
    # 원형 idea_agent.py:73-78 — hypothesis 자리에 dict
    up = prompts.idea_user_enhance("ex", idea, "expr", "report")
    assert f'Previous hypothesis: "{idea}"' in up


def test_similarity_equivalence_with_original():
    _orig_eval = _load("orig_eval_sim", "Alphaagent/agents/eval_agent.py") \
        if False else None
    # eval_agent.py는 상대 import(..backtester)가 있어 파일 로드 불가 —
    # 유사도 함수는 소스 텍스트에서 함수부만 exec로 추출해 대조한다.
    src = open(os.path.join(_REPO_ROOT, "Alphaagent/agents/eval_agent.py")).read()
    header = src.index("class ASTNodeWrapper")
    footer = src.index("class EvalAgent")
    ns = {"ast": ast}
    exec(src[header:footer], ns)                      # noqa: S102 — 참조 비교 전용
    orig_fn = ns["ast_similarity_by_common_subtree_ast"]

    pairs = [
        ("(close-open)/open", "(close-open)/open"),
        ("(close-open)/open", "(volume-high)/high"),     # 라벨 버그: 구조 동일
        ("Mean(close, 5)/close", "Std(volume, 10)/volume"),
        ("Ref(close, 5)", "(high-low)/(close+1e-12)"),
        ("Corr(close, Log(volume+1), 5)", "Corr(close/Ref(close,1), Log(volume+1), 10)"),
    ]
    for a, b in pairs:
        ta, tb = ast.parse(a, mode="eval"), ast.parse(b, mode="eval")
        assert ours(ta, tb) == orig_fn(ta, tb), (a, b)


def test_label_bug_preserved_and_fix_option():
    a = ast.parse("(close-open)/open", mode="eval")
    b = ast.parse("(volume-high)/high", mode="eval")
    assert ours(a, b) == 1.0                                  # 원형: 구조만 비교
    assert ours(a, b, distinguish_terminals=True) < 1.0       # 수정 옵션


def test_seed_expressions_match_original_source():
    src = open(os.path.join(_REPO_ROOT, "alphaagent.py")).read()
    for expr in prompts.SEED_EXPRESSIONS:
        assert f"'{expr}'" in src, expr
    assert len(prompts.SEED_EXPRESSIONS) == 37
