# gplearn_asb 3-arm Comparison Pilot 보고서

**실험일**: 2026-08-14 · **조건**: csi800, 마이닝 창 2010-01-01~2019-12-31,
pop 1000 × gens 5 (= 후보 5,000), hof 50 → pool 10, seed 42 — **세 arm은
constraint mode만 다름** (off / hard_penalty / strict_penalty).
**산출**: `out/pilot_csi800_{off,hard,strict}_42/` (+ 각 `asb_eval/`),
ASB 평가 split: train 2010–2016 / valid 2017–2019 / test 2021–2024
(sign은 CSV의 마이닝 창 signed IC 사용 — 사후 복원 아님).
**해석 노트북**: `alphasearchbench/notebooks/asb_results_explorer_v2.ipynb`.

## 1. Original equivalence (off 모드)

- **gen-0 동일성**: 같은 seed에서 vendored 프로그램 생성이 원본 gplearn과
  200/200 문자열 일치 (RNG 소비 순서 보존).
- **전체-run 재현**: 883881(smoke) 조건 off-run이 원본 fast runner의 최종
  pool을 **완전 재현** — formula 목록·HOF 중복 패턴 동일, IC 최대차 0.0
  (`out/replicate_883881_off/`).
- 이번 pilot의 off arm 역시 883929(tensor)의 아티팩트 pool을 재현했다
  (fitness 0.074825 / 0.074644 일치).
- 구현 중 확정된 수치 경계 2건은 IMPLEMENTATION_PLAN '구현 중 발견' 참조
  (one-pass IC의 파국적 상쇄 → two-pass(pandas 의미론) 채택; r=±inf 가드 —
  방치 시 stopping_criteria 오발).

## 2. Penalty 구현

- worst sentinel = **−1.0**(유한, config): `p.raw_fitness_`에 주입 →
  tournament(fitness_ argmax)와 HOF(raw_fitness_ argsort)가 동시에 소비.
- **population 불변**: 원본 evolve에는 reject 경로가 없고 본 구현도 무조건
  append — 세 arm 모두 전 세대 population=1,000 확인 (합성 테스트: invalid
  89%에서도 크기 유지 + invalid 잔존 + valid 부모 과대표집).
- raw/effective 분리 저장: 아티팩트의 "raw 0.0748 / effective −1.0"이
  trajectory에 그대로 남는다.

## 3. Validity behavior — pathological winner 처리

| | off | hard | strict |
|---|---|---|---|
| 아티팩트 계열(coverage<5% & raw>0.049) 발견 | 7개 | 7개 | **0개** |
| raw-fitness top-20 중 아티팩트 | 7 | 7 | 0 |
| eval 실패(hard invalid) unique | 81 | 81 | 74 |
| 최종 pool coverage | ~1% | ~1% | **49–96%** |

- **hard_penalty는 무효했다**: 루프홀 후보는 eval 실패가 아니라 research-
  invalid(희소 coverage)이므로 hard 게이트에 걸리지 않는다. off와 hard는
  budget(5,000/1,675 unique/3,021 memo)까지 **bit 단위 동일 경로**.
- **strict는 발견 자체를 차단**: gen2에서 경로가 갈라져 아티팩트 계보가
  번식하지 못했고, 탐색이 `Div(Less(...), $volume)` 계열(1/거래량형,
  coverage 96%)로 이동했다.

## 4. Search behavior (H1·H2·H4)

세대 통계(`generation_stats_*.parquet`, 노트북 §9):

- **H1 수정 — population collapse가 아니라 elite capture**: off에서 median
  coverage는 5세대 내내 0.96대, invalid rate 1–2%로 안정. 아티팩트는 개체군을
  점령하지 않고 **fitness 상위권만 점령**해(top-20 전부) HOF/최종 pool을
  독식한다. best_raw는 gen2에서 0.0748로 점프 후 고정.
- **H2 입증**: strict의 research_invalid_rate는 0.1–2%로 낮게 유지 —
  아티팩트형 후보가 나타나는 즉시 worst가 되어 부모가 되지 못한다.
  best_valid_train_IC는 0.0492(gen2) → 0.0677(gen3)로 고커버리지 영역에서
  상승.
- **H4 기각(이 조건)**: parent_selection_entropy off 4.79–5.14 vs strict
  4.79–5.19, top-parent share도 동등 — worst-penalty로 인한 다양성 붕괴는
  관측되지 않았다.

## 5. Pilot comparison (스펙 #34 핵심 표)

| 지표 | off (=원본 GP) | hard | strict |
|---|---|---|---|
| attempted / unique evals | 5,000 / 1,675 | 동일(경로 일치) | 5,000 / 1,635 |
| best raw train \|IC\| | **0.0748** | 0.0748 | 0.0677 |
| best valid train \|IC\| (research 통과) | 0.0492 | 0.0492 | **0.0677** |
| 최종 pool unique / coverage | 3 / ~1% | 3 / ~1% | 4 / 49–96% |
| factor test IC (대표) | Rsquare 0.0041·Div 0.0231* | 동일 | winner 0.0119·계열 0.0092 |
| valid→test 유지 (winner) | 0.0742→0.0041 (−94%) | 동일 | 0.0631→0.0119 (−81%) |
| **pool 결합 test IC / RankIC** | +0.0003 / +0.0017 | 동일 | **+0.0095** / −0.0152 |
| pool Sharpe / CAGR / MDD | −0.45 / −7.4% / 0.45 | 동일 | −4.20 / −23.7% / 0.65 |
| wall clock (마이닝) | 88.8분 | 88.6분 | 86.5분 |

\* off의 Div 0.0231은 coverage ~1% 초소표본 IC — 크기 해석 불가.

**H3 판정 — 신호와 포트폴리오가 갈린다 (예단 없이):**
1. **신호 수준에서는 strict 우세**: pool test IC +0.0095 vs +0.0003.
   strict의 test IC는 전 종목 coverage에서 계산된 통계적으로 유효한 값인
   반면, off의 값들은 초소표본이라 비교 자체가 성립하기 어렵다.
2. **포트폴리오 수준에서는 strict 열세**: Sharpe −4.2 vs −0.45. 단 off의
   "우세"는 실체가 아니라 **거래 부재**의 산물이다(coverage 1% → 대부분의
   날 포지션 없음 → 평평한 곡선). strict pool은 실제로 매일 거래하며
   2021–2024 약세장 + 15bp 비용을 온전히 흡수했고, 신호(1/거래량형)의 IC
   크기(~0.01)가 비용을 이기기에 부족했다.
3. strict의 RankIC 음수(−0.015)와 IC 양수의 괴리는 Pearson이 소수 외곽값에
   끌렸을 가능성을 시사 — 개별 factor의 RankIC도 음수여서, 이 pool의 실질
   예측력은 "약함"으로 평가하는 것이 정직하다.

**요약**: strict penalty는 "루프홀 제거"라는 1차 목표를 완전히 달성했고
(발견 자체 차단, 다양성 비용 없음), 그 결과 남은 것은 "진짜지만 약한"
신호였다. 이는 validity 게이트의 성공이지 알파 발견의 성공은 아니다.

## 6. Limitations

- **provisional thresholds** (0.05/30/0.90): 파일럿 근거 재도출값이며 이
  실험 설계에 그대로 주입 — multi-seed 후 재확정 필요.
- **single-seed(42)**: arm 간 차이의 seed 안정성 미검증 — 통계 비교는
  노트북 §10 규칙상 불가(기술 통계만).
- **runtime/cache**: off·hard 경로 동일로 budget이 완전히 일치했으나,
  일반적으로 penalty가 경로를 바꾸면 unique/memo가 달라질 수 있다(strict
  1,635 vs 1,675 — 2.4% 차이).
- **pool 결합 = equal weights** (참고용), HOF 중복 버그(원본 보존)로 pool
  유효 unique가 3–4개에 불과.
- **overflow 경계**: 중간노드 overflow 병리 formula에서 엔진 간 값이
  불안정한 영역이 존재(IMPLEMENTATION_PLAN 발견 #1) — 해당 후보는 모두
  validity 게이트 대상이라 판정에는 영향 없음.
- diversity collapse는 이 조건에서 미관측이나, 더 강한 threshold·더 긴
  세대에서는 재검이 필요.

## 7. 다음 단계 제안

1. **seed sweep**(예: 0–4) — H2/H3의 seed 안정성 + §10 통계층 가동.
2. strict 조건에서 **비용 인지형 fitness**(IC 대신 net-return 지표) ablation.
3. attempted 후보 전체 descriptor 덤프 옵션(ASB 확장) → search-QD를
   niche 수준에서 측정.
4. AlphaAgent(Exp B)와의 교차 비교 — 동일 노트북 registry에 편입 예정.
