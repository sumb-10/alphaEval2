# AlphaAgent_asb TODO

## Phase A — Scaffold + LLM layer
- [x] 디렉토리/PROVENANCE(편차 D-1~D-8)/configs(default·smoke)
- [x] config.py (gplearn_asb 패턴, YAML off 함정 방어)
- [x] llm.py: HTTPLLM(thin client, 유한 재시도 D-1) / FakeLLM(결정적,
      원형 판정 규칙 재현 + fake_accept_rule 테스트 노브) / ReplayLLM
      + llm_calls.jsonl 전량 로그 + budget 카운터(role별·retry 분리)
- [x] unit 6종 PASS (결정성/카운터/replay/키 게이트)

## Phase B — Prompt/Agent/Similarity parity port
- [x] vendored_alphaagent 사본(byte-identical md5 확인) + PROVENANCE
- [x] prompts.py verbatim (+seed 수식 37개) / similarity.py verbatim
      (+distinguish_terminals 옵션, 기본 원형 라벨버그 보존)
- [x] agents.py: parity(dict repr·silent-empty 원형) | safe 분기
- [x] regression 6종 PASS: 프롬프트 원문 일치, 유사도 원형 함수와 동일값,
      parity dict-repr 조립 일치, seed 수식 원문 일치, 라벨버그 보존/수정옵션

## Phase C — Evaluator parity gate (지도 원칙 1)
- [x] feedback.py: vendored FactorBacktester 직접 실행(원형 반올림·버그 보존),
      raw/prompt 값 분리
- [x] gate 통과 (jobs 884317/884319): **vendored == 원본 완전 동일**
      (fixture 5종 perf frame equal) + Mining/원본 차이 표 산출
      (`out/verification/feedback_parity_table.csv` — 정상 수식에서 두 의미론
      IC가 반올림 수준 일치, 예: −0.021084 vs −0.021)

## Phase D — Loop + trajectory
- [x] loop.py: 원형 seed×round 구조, generation=round_id·idx=seed_idx,
      자연어 궤적(idea_text/eval_feedback_text/previous_formula),
      D-2 seed 단위 격리, constraint overlay(기본 off)
- [x] cli.py: fake/replay/live, 산출물(final_pool CSV·candidate_diagnostics·
      round_stats·manifest(budget+trajectory_semantics))
- [x] 수동 smoke: FakeLLM E2E rc=0 (6 후보/16 콜, eval 콜은 feedback 성공분만
      — 원형 의미론)

## Phase E — FakeLLM E2E + ASB 호환
- [x] smoke suite 18/18 PASS (job 884319): trajectory 스키마/축, 자연어 필드,
      budget 분리 기록, accept 경로 + ASB load_result
- [x] **발견·해결**: ASB core FormulaEngine이 AlphaAgent의 qlib 전체 문법
      (infix 등)을 파싱 못 함 → (1) AA 진단은 `diagnostics.py`의
      qlib fallback 래퍼, (2) **ASB core에 signal engine 2단계 추가**
      (`SignalContext.evaluate` — parse 불가 시 qlib native로 같은 수식 계산,
      `signal_engine` 컬럼 기록; IMPLEMENTATION_NOTES 구조적 제약 #4,
      infix↔함수형 비트 일치 테스트 포함 3/3 PASS)
- [x] ASB `evaluate`에 smoke 산출물 입력 → **8종 parquet 생성**
      (Search-QD 세대 지표 포함), signed_train_IC 입력값 그대로 사용
- [x] 원본 무수정 검사 + import 검사 OK
- [x] 전체 회귀 확인 (job 884327): gplearn_asb 19/19, ASB 79+1(기존
      no-silent-fallback 테스트를 2단계 엔진 계약에 맞게 갱신 후 10/10 —
      raise 계약은 불변) → 세 suite 모두 green

## Phase F — Live pilot [사용자 승인 대기]
- [ ] Experiment B(우선 제안): csi800, 2010–2019, parity, constraint=off
- [ ] Experiment A(여력 시): all universe 원형 재현
- [ ] ASB evaluate + GP arms 교차 비교표 + REPORT.md
