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

## 8. Seed sweep + A+B+P 확장 결과 (2026-08-14~15 추가)

### 8.1 HOF 붕괴의 정량화와 fixed-HOF 소급 (A)

원본 HOF(중복 미제거 decorrelation)의 pool 유효 unique는 seed에 따라 1~10으로
붕괴했다. `scripts/repool_fixed_hof.py`(trajectory 마지막 세대 = 최종 population
사실을 이용, 재마이닝 없음)로 8 run에 fixed-HOF를 소급한 결과:

| run | 원본 unique | fixed unique(valid) | 비고 |
|---|---|---|---|
| strict_0 | 6 | 10 (10) | 최종 max\|corr\|=1.0 쌍 잔존* |
| strict_1 | 2 | 10 (10) | |
| strict_2 | 1 | 10 (10) | population unique 자체가 16 |
| strict_3 | 4 | 10 (1) | **population에 유효 unique 1개** — 탐색 자체 붕괴 seed |
| strict_42 | 10 | 10 (10) | max\|corr\|=1.0 쌍 잔존* |
| netsharpe_0/1/2 | 2/1/7 | 10/10/10 (10/9/10) | |

\* 문자열은 다르나 신호가 동일한 쌍(교환법칙 변형 등) — exact-dup 제거로는 못
잡는 **canonical 중복**. P2-4(canonical 정규화)를 보류한 대가가 HOF 층위에서
재등장함을 기록한다 (사전 실측 중복률 1.2%와 일관).

pool 결합 test IC는 양방향으로 움직였다(strict_0 0.0102→0.0142,
strict_1 0.0268→0.0077). 원본 strict_1의 높은 pool IC는 **사실상 단일 수식
중복 pool의 착시**였다 — fixed-HOF가 pool 지표를 "pool의 지표"로 되돌린다.

### 8.2 신뢰도 fitness ablation (B, strict, seed 42, 1-seed 예비)

| arm | trajectory unique | 승자 (raw) | 승자 \|IC\| | 관찰 |
|---|---|---|---|---|
| ic_tstat | 1,716 | Div(Div(Less(...),$vol),$vol) (t=23.3) | 0.042 | t-stat이 낮은-분산 IC 계열로 수렴 |
| ns_guarded | 2,045 | Std(WMA(Mad($amount,5),12),12) (Sharpe 1.96) | 0.014 | **unique의 59%(1,213)가 ic_below_floor로 차단** |
| fb_fitness | 1,506 | Sub(EMA(Kurt(Var($amount,30),12),30),...) (fb 0.15) | 0.006 | 저-turnover 편향 — IC floor 없이는 여전히 저IC 허용 |

핵심: 무가드 net_sharpe 탐색의 지배 모드가 "IC 없는 Sharpe"였음이 가드
발동률 59%로 실증된다(B2 가설 확정). fb_fitness는 turnover 패널티로도 이
모드를 막지 못한다 — IC floor(B2)와의 결합이 필요.

### 8.3 정적 사전검증층 (P) 운영 실측

ablation 3 run에서 `static_invalid:constant_expression` 2~5건/run이 데이터
접근 0회로 분류됐다(사전 실측 0.32%와 일치). 구현 중 원판정기의 오류 2건을
정정: Greater/Less는 qlib에서 max/min(f(x,x)=x 항등 — 상수 아님, 13 run에서
101건이 이 부류), window 0/실수 창은 엔진이 유효 평가(expanding/지수창) —
bad-window는 invalid가 아닌 flag로 강등. **static ⊂ hard가 증명된 규칙만
invalid로 승격**해 penalty 모드의 effective fitness 불변을 보장한다.

### 8.4 AlphaAgent Exp B (참조)

gpt-5.6-luna 기반 Exp B는 51 후보 전량 미수락(평가된 24 후보 \|IC\|≤0.022,
LLM eval 전부 저품질 판정; 나머지 27건은 parse/bare-name 실패)으로 **빈 pool
완주** — 그 자체가 결과이며 v2 노트북에 빈-pool run으로 편입된다.
ASB evaluate(빈-pool 허용 runner 확장 + SignalContext bare-name 가드 이식
후)는 trajectory 51 후보의 allcand descriptor(평가 가능 24, skip 27)와
search-QD 3 round(coverage ≤0.025 — GP off-arm 대비 크게 좁은 탐색 폭)를
산출했다.

## 9. 참고연구 프로토콜 동등화 (WS-A / E3, 2026-08-18)

상세: `AlphaSearchBench/docs/experiments/2026-08-18_E3_protocol_4arm_sweep.md`

* 참고연구 실측(논문 PDF 직독): AlphaAgent(KDD'25)는 **qlib TopkDropout
  top-50/drop-5 long-only + 비대칭 비용(5/15bps) + 지수 대비 초과 AR·IR**로
  평가하며, 스칼라 fitness 없이 자연어+지표 피드백을 쓴다. 우리 v0.1 프로토콜
  (분위 20/20 LS, 매일 전량 리밸런스)은 회전 상한이 없어 |IC| pool에서 연
  96~193배 회전을 유발 — 비용 구조가 근본적으로 다르다.
* **E3 결정 게이트 판독** (29 pool × 4 arm): A3(논문형)에서 초과 AR ≥ +4%
  도달은 **fbfit_42 하나**(+17.2%, IR 1.29 — 논문 CSI500 대역). |IC| 계열은
  회전을 23배까지 눌러도 전부 음수 → **비용은 손실을 증폭했을 뿐, 신호
  부재가 근본 원인**. 우리 GP 수치는 논문 자신의 GP 베이스라인 붕괴(Fig 4)
  및 AlphaEval 벤치마크 GP(PPS 0.017)와 정합 — "참고연구 GP 베이스라인 재현"
  으로 포지셔닝한다.
* 원본 HOF 결함 재확정: "중복 미제거"가 아니라 **anti-selection**(pool =
  최고 1 + HOF 꼬리 9; np.corrcoef 전-NaN → argmax가 항상 (0,1)). 이후 pool
  단위 보고 기준은 `*_fixedhof`.
* split 재정렬: valid를 2020(마이닝 창 밖)으로 교체 — 기존 valid(2017–19)는
  마이닝 창 내부라 OOS가 아니었다.

## 10. WS-B 판정 — fb_fitness 재현성 (E1/E2, 2026-08-18)

상세: `AlphaSearchBench/docs/experiments/2026-08-18_E1_fbfit_seed_sweep.md`, `_E2_fbfit_ic_floor.md`

* **수익 재현 실패**: 5-seed 중 A3 초과AR>0은 seed 42 하나(+17.2%; 나머지
  −3.6~−7.3%) — 사전 규칙상 "seed 의존", 실질 "seed 42 행운".
* **탐색은 재현**: 5 seed 전원이 같은 $amount-분산 저회전 계열로 수렴
  (train fb 0.14–0.17) — fb_fitness는 니치 발견 장치로는 안정, 수익 장치는 아님.
* **IC-floor 결합(E2)은 역효과**: 가드가 unique 63%를 차단하고 승자 IC를
  올렸지만 test 수익 소멸 — seed 42의 흑자는 IC를 경유하지 않는 수익이었다.
* **종합 판정(§9 게이트 갱신)**: 프로토콜은 증폭기일 뿐, 격차의 지배 원인은
  **신호 부재**. 본 GP 계열은 "참고연구 GP 베이스라인 재현"으로 최종
  포지셔닝하며, 다음 사이클 의제는 miner 개선(결합층·다양성 압력·기간/universe)
  이다.
