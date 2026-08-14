# AlphaAgent_asb 구현 계획 (승인판 요약)

전체 계획·감사 근거는 승인된 plan 문서 기준. 여기에는 실행 중 참조할 핵심만.

## 지도 원칙 (사용자 확정 4문장)

1. AlphaAgent의 IC/AnnRet은 LLM feedback에 직접 영향을 주므로,
   MiningEvaluator와 ASB simple backtest는 원본 FactorBacktester와
   numerical parity가 확인된 뒤에만 feedback evaluator로 대체한다.
   불일치 시 원형 feedback metric과 ASB diagnostic metric을 분리한다.
   → 구현: feedback.py = vendored FactorBacktester 직접 실행(분리 기본).
2. trajectory의 기본 시간축은 seed_idx와 round_id로 명시. 공통 generation
   필드는 round_id에 대응. semantic mapping은 manifest에 기록
   (seed 간 독립 — reproducing population 아님).
3. parity mode(원형 formatting·동작)가 기본 연구모드. runnable/safety
   개선으로 behavior가 달라지는 부분은 deviation(PROVENANCE) 또는 safe
   mode로 분리. 무한재귀만 parity에도 유한 가드(D-1).
4. LLM budget은 candidate 수와 LLM call 수를 분리 기록 (Idea/Factor/Eval/
   retry 콜 수, tokens, cost).

## 원형 감사 요약

- 루프: seed 37개 중 [20:] × max_rounds 3, round당 Idea/Factor/Eval 3콜.
- 논문 정규화 중 코드 존재는 AST 유사도뿐(임계값 없음, 라벨 버그 보존).
- feedback = FactorBacktester AnnRet["total"]·IC["total"](3자리) + 유사도
  → LLM 자연어 비평 → IdeaAgent enhance 프롬프트.
- 원형은 실행 불가 상태(key/qlib placeholder, mock·seed·trajectory 없음).

## Phase 진행 상태
A(scaffold+LLM) ✅ → B(parity port) ✅ → C(parity gate) 테스트 제출 →
D(loop/trajectory/cli) ✅ → E(FakeLLM E2E+ASB 호환) 진행 → F(live, 승인 대기)

## Experiment A/B 구분 (live)
- A: 원형 재현 — universe `all`, 2010–2019, parity, off.
- B: 통제 비교 — universe csi800(D-7 편차 기록), GP 3-arm과 동일 창.
  "원 저자 재현"이라 부르지 않는다.
