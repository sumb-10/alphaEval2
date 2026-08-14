# vendored_alphaagent — 출처와 용도

- 출처: `AlphaEval/Alphaagent/`(논문 "AlphaAgent: LLM-Driven Alpha Mining with
  Regularized Exploration to Counteract Alpha Decay" 구현) + repo 루트
  `alphaagent.py`. 2026-08-14 시점 **byte-identical verbatim 사본** (md5 대조).
- 파일별 용도:
  - `backtester.py` — **feedback 경로에서 직접 실행됨** (FactorBacktester —
    LLM이 보는 AnnRet/IC의 원형 산출기. 첫날 NaN cost 버그·IC 3자리 반올림
    포함 원형 그대로 보존).
  - `idea_agent.py` / `factor_agent.py` / `eval_agent.py` — 프롬프트·로직
    parity의 **텍스트 기준 원문** (실행은 alphaagent_asb/agents.py 포팅본이
    담당 — 원문은 openai 모듈 전역에 묶여 있어 주입식 LLM과 호환 불가).
  - `alphaagent_entry.py`(= 루트 alphaagent.py) — seed 수식 37개·루프 상수의
    원문 기준.
- 수정 이력: **없음** (필요 시 이 파일에 기록).
- 원본 `AlphaEval/Alphaagent/`는 무수정 유지 — 특히 `Alphaagent/backtester.py`
  는 gplearn_asb shim의 런타임 의존 대상.
