# AlphaAgent_asb — 원형 대비 편차 목록 (Deviations)

원형 = `AlphaEval/Alphaagent/` + repo 루트 `alphaagent.py`
(vendored 사본: `alphaagent_asb/vendored_alphaagent/`).
기본 연구모드는 `compatibility.mode: parity` — 아래 D-1~D-5, D-8은 parity에도
적용되는 최소 편차(실행 가능성·산출물 계약), D-6은 safe mode 전용이다.

| ID | 편차 | 근거 | 적용 모드 |
|---|---|---|---|
| D-1 | FactorAgent 재시도를 유한화 (원형 `factor_agent.py:45-65`는 `try_times=0`이 재귀 호출마다 리셋되어 사실상 무한재귀 → RecursionError 위험). 한도 = `llm.max_retries`(기본 5 — 원형 코드의 의도값) | 실행 위험 | parity+safe |
| D-2 | IdeaAgent enhance 경로의 비JSON 응답 ValueError(`idea_agent.py:94-95`)가 전체 run을 중단시키는 문제 → **seed 단위 abort로 격리**하고 trajectory에 `seed_aborted` 기록 | 실행 위험 | parity+safe |
| D-3 | module-level `json.dump`(`alphaagent.py:97` — import만 해도 결과를 `[]`로 덮어씀, 중도 사망 시 전량 유실) → 후보 단위 증분 기록(trajectory) + atomic 최종 저장 | 산출물 계약 | parity+safe |
| D-4 | openai SDK 모듈 전역 호출 → 주입식 LLM 클라이언트(HTTP/fake/replay). **프롬프트 문자열·모델·온도는 원형 유지** (regression으로 고정) | 실행 가능성·재현성 | parity+safe |
| D-5 | `qlib.init` placeholder(`alphaagent.py:13`, 깨진 `~/.qlib` 경로) → config `dataset.provider_uri` | 실행 가능성 | parity+safe |
| D-6 | (safe 전용) dict를 f-string에 repr로 삽입하던 프롬프트 조립(`alphaagent.py:76,96`) → 명시적 문자열 조립; JSON 파싱 실패 시 silent-empty 대신 strict 재시도. **parity에서는 원형 그대로**(dict repr, silent-empty) | 탐색 행동 영향 | safe만 |
| D-7 | (Experiment B 전용) original AlphaAgent used `all` universe; the csi800 comparison overrides the mining universe for cross-method experimental control. (universe는 원형도 생성자 주입식 — `alphaagent.py:62` — 코드 수정 없음, 실험 조건 편차) | 통제 비교 | Exp B config |
| D-8 | seed 수식 슬라이스 `expressions[20:]`를 config `agent.seed_range`로 노출 (기본값 = 원형 [20, null]) | 재현·통제 | config |
| D-9 | LLM 모델: 원형 gpt-4o → **gpt-5.6-luna** (live 실험, 2026-08-14 사용자 선택 — 비용·JSON 준수 근거). LLM이 search를 이끌므로 탐색 행동이 원저자 실행과 다를 수 있음 — Exp A도 "gpt-4o 재현"이 아니라 "원형 파이프라인 + 대체 모델" | 실험 조건 | live config |
| D-10 | **온도 프로필 강제 편차**: gpt-5.6-luna는 temperature=1(기본값)만 허용 (실측 400: "Only the default (1) value is supported") → 원형 factor 0.3/eval 0.4를 재현 불가. HTTPLLM이 temperature 미지원 400 감지 시 파라미터를 제거하고 모델 기본값으로 진행하며, manifest `llm.temperature_fallback_models`에 기록. 온도 프로필 원형 재현이 필요하면 gpt-4o-mini 등 온도 지원 모델 사용 | 모델 제약 | live(luna) |
| D-11 | **행(hang) 방지 가드 2종** (Exp B 1차 실행에서 실측 — $ 없는 bare-name 수식을 qlib market=all에 던지면 종목별 NameError 폭주로 joblib 교착): ① bare 필드명 수식은 feedback·진단 모두 즉시 실패 처리(원형은 그대로 qlib에 전달돼 예외/교착), ② feedback 백테스트에 후보별 SIGALRM 타임아웃(기본 600s, config) — 타임아웃은 원형의 '예외 삼킴' 경로와 동일하게 is_valid=False로 분류 | 실행 위험 | parity+safe |

추가 기록 원칙: parity mode의 탐색 행동에 영향을 줄 수 있는 어떤 변경도 새
D-번호로 이 표에 등록한 뒤에만 적용한다.
