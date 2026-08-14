# ASB Pilot 신뢰성 검증 — 6개 지적에 대한 감사 결과

**검증일**: 2026-08-14 ·
**대상**: `asb_pilot_evaluation.md`의 결론과 AlphaSearchBench v0.1 평가 체인 ·
**산출물**: `AlphaSearchBench/out/verification/*.csv`,
`AlphaSearchBench/out/pilot_signfix/`(마이닝 창 sign 재복원 재실행),
검증 스크립트 3종(`AlphaSearchBench/scripts/verify_winner_equivalence.py`,
`compare_train_sign_windows.py`, `derive_thresholds_no_test.py`),
회귀 테스트 1건 추가.

## 요약 판정표

| # | 지적 | 검증 결과 | 파일럿 결론 영향 |
|---|---|---|---|
| 1 | train_sign 창 불일치 (2010–2016 vs 마이닝 2010–2019) | **타당한 우려, 실측 결과 flip 0건** — 20개 전수에서 부호 동일, oriented test IC 완전 동일 | 없음 |
| 2 | 마이닝 evaluator ↔ ASB 신호 동등성 | **정상 formula 17/21 비트일치 + fitness 6자리 재현**; 병리 4개에서 overflow 경계 편차 발견(하단 상세) | 없음 (편차는 전부 아티팩트 판정 formula에 국한, 판정 동일) |
| 3 | coverage 분모의 PIT 여부 | **PIT 확인** — all: 날짜별 4,332→5,363 변동(정적 5,546 아님), csi800: 정확히 800 | 없음 |
| 4 | 일별 IC 최소 N=2의 무의미성 | **정확한 지적으로 실증** — gp_main IC 관측 44–47일 전부 n<5, 그중 39일 \|IC\|=1 | 서술 수정 (−0.35의 "부호 반전" 해석 격하) |
| 5 | threshold의 test leakage | **타당** — train/valid만으로 재도출 완료, 이봉 구조·권장값 유지(경계 1건 단서) | 근거 교체 |
| 6 | equal-weight pool 지표 | 이미 문서화된 한계, 프레이밍 유지 | 없음 |

**총평: ASB 평가 체인 자체의 결함은 발견되지 않았다.** 파일럿의 핵심 결론
(고IC 승자 = validity 아티팩트, OOS 예측력 부재)은 6개 감사 모두 통과
후에도 유지된다. 발견된 것은 (a) 병리 신호에서의 qlib native와의 overflow
처리 경계(문서화 완료, 판정 불변), (b) 보고서 서술 2곳의 수정 필요
(−0.35 해석, threshold 근거)다.

---

## V1. train_sign 창 재복원 (지적 1)

`configs/examples/csi_mining_window.yaml`(train=2010–2019 = 마이닝 fitness
창)으로 4개 pool의 OOS를 재실행(`out/pilot_signfix/`)하고 pilot(train
2010–2016)과 전수 대조했다
(`out/verification/train_sign_window_comparison.csv`).

- **비교 가능 20개 formula 전수에서 sign flip 0건.**
  signed IC의 크기는 창에 따라 다르지만(예: gp_main sibling +0.469 →
  +0.487, random 경계 +0.104 → +0.153) 부호는 전부 동일 →
  **oriented test IC가 소수점까지 완전 동일.**
- 유일하게 비교 불가한 1개(gp_main 절대승자, train \|IC\| 0.565)는 양쪽
  모두 test에서 `no_correlatable_day` hard invalid — sign 자체가 필요
  없는 케이스.
- 결론: 지적은 구조적으로 옳았고(`signed_ic_on_train`은 config의 train
  split을 사용), 이 데이터에서는 결론을 바꾸지 않았다. **향후 실험 규칙**:
  sign 복원용 train split은 마이닝 fitness 창과 일치시킬 것 (또는 러너가
  signed IC를 직접 덤프하는 표준 스키마 사용).

## V2. 신호 동등성 + 마이닝 fitness 재현 (지적 2)

pool 4개의 unique formula 21개 전부에 대해, 마이닝 창(2010–2019)에서
(a) qlib `D.features`(마이닝 원본 의미론) vs (b) ASB `FormulaEngine`의
신호를 **셀 단위로** 대조하고, fast runner의 `_ic_pair` 집계 그대로
fitness를 재계산해 CSV 기록값과 대조했다
(`out/verification/winner_equivalence.csv`).

**fitness 재현 — 완전 성공 (마이닝 산출물의 진위 확인):**

| 검증 | 결과 |
|---|---|
| qlib-direct 재계산 \|IC\| vs CSV 기록 fitness | **21/21 전부 6자리 일치** (0.565217, 0.485306, 0.145641, … 포함) |
| gp_main 절대승자 0.565217의 정체 | IC 관측일 **23일**, 유효 셀 **57개/6.7M 그리드** — 0.565217 = 13/23, 즉 "2종목 상관 ±1이 23일 중 +18일/−5일" |

**신호 동등성 — 정상 17/21 비트일치, 병리 4개에서 경계 편차:**

- 정상 formula 17개: `max|diff| = 0.0`, NaN/inf 패턴 완전 일치
  (`Power(Resi($high,30),…)`의 +inf 2,261셀 위치까지 동일).
- 병리 4개(gp_main 3 + random 경계 Rsquare 1): **중간 노드 overflow가
  rolling 연산으로 흘러가는 경우** qlib native(노드별 float32 조기 캐스팅
  → NaN 전파)와 ASB(내부 float64, 후기 캐스팅 → +inf 유지)가 어긋난다.
  winner: qlib NaN 셀 266,805개가 ASB에선 +inf. 경계 formula: 공통 셀
  max|diff| 0.435, ASB가 42,473셀 추가 마스킹(Rsquare std≈0 규칙).
  → ASB 재평가 IC가 마이닝 기록과 달라진 사례: 0.4853→0.4866,
  0.1456→0.1529 (부호 동일, 판정 동일).
- 집계 의미론 차이 1건: inf 셀 존재 시 fast runner는 그 **날 전체** 탈락,
  ASB는 그 **셀만** 제외 (smoke Power 계열 0.0498 vs 0.0647 — 부호 동일).
- 처리: `AlphaSearchBench/docs/IMPLEMENTATION_NOTES.md` 구조적 제약 #3으로
  문서화. **영향받는 신호가 전부 validity gate가 걸러내는 병리 케이스**
  (정확히 그 목적으로 설계된 gate)라 v0.1에서는 수정하지 않는다.

## V3. coverage 분모 PIT 감사 (지적 3)

`out/verification/coverage_denominator_audit.csv`:

| market | 날짜 | PIT 분모 | 정적 컬럼 수 | finite $close |
|---|---|---|---|---|
| all | 2021-06-01 | 4,332 | 5,546 | 4,318 |
| all | 2023-06-01 | 5,194 | 5,546 | 5,169 |
| all | 2024-06-03 | 5,363 | 5,546 | 5,344 |
| csi800 | 3개 날짜 | **800** | 1,105 | 797–800 |

분모는 날짜별 point-in-time 편입 수와 일치하고 정적 목록(5,546/1,105)이
아니다. PIT 분모가 finite $close보다 약간 큰 것(거래정지 종목 포함)도
올바른 동작 — 정지 종목은 분모에 있고 분자(finite signal)에서 빠진다.

## V4. 일별 IC 최소 N 실증 (지적 4)

기존 pilot `oos_daily.parquet` 재집계 (test, h=1):

| run | IC 관측일 / 969 | 그중 n<5 | \|IC\|=1인 날 | IC 관측일의 median n |
|---|---|---|---|---|
| gp_main sibling ×3 | 44–47 | **44–47 (전부)** | 22–39 | **2–3** |
| gp_csi800 ×3 | 520 | 163 | 73–74 | 11 |
| random ×10 / gp_smoke ×4 | 969 | 0 | 0 | 2,406–5,063 |

- "969일 중 44–47일" 재확인. **gp_main의 test IC −0.35는 종목 2~3개
  상관(대부분 문자 그대로 ±1)의 44개 평균** — 크기·부호 모두 통계적
  해석 불가. 파일럿의 "부호 반전" 서술은 "신호 없음 + validity 실패"로
  격하한다 (아티팩트 판정 자체는 불변 — 오히려 강화).
- hard invalid의 N≥2는 설계대로 "수학적 최소"이며, 연구 판정은 research
  threshold(`min_median_daily_n_valid`)가 담당한다는 이층 구조가 정확히
  이 사례를 위해 존재함을 확인.
- **결정 제안(사용자)**: `oos.min_daily_n_for_ic` config 신설(기본 2 유지
  시 기존 결과 불변; 연구값 30 채택 시 일별 IC 자체가 소표본 날을 제외).

## V5. threshold 재도출 — test 미참조 (지적 5)

`derive_thresholds_no_test.py`가 **train(2010–2016)·valid(2017–2019)
분포만으로** 21개 formula의 coverage 통계를 재계산했다
(`out/verification/validity_stats_train_valid.csv`):

| 그룹 (train+valid) | coverage | median n_valid | valid_day_ratio |
|---|---|---|---|
| 정상 15개 | **0.477 ~ 0.997** | 1,176 ~ 3,535 | 1.00 |
| 아티팩트 7개 (gp_main 4 + csi800 3) | **0.000 ~ 0.011** | 0 ~ 14 | 0.00 ~ 1.00* |
| 경계 1개 (random Rsquare) | train 0.038 / valid 0.057 | 83 / 202 | 1.00 |

(*gp_main sibling의 valid split은 vdr=1.00이지만 median n=14로 n-기준에서 탈락)

- **이봉 구조는 test 없이도 동일**: 아티팩트 ≤0.011 vs 정상 ≥0.477.
  권장값 (0.05 / 30 / 0.90)은 train/valid만으로 아티팩트 7개 전부 제외 +
  정상 15개 전부 유지 — leakage 없이 재도출됨.
- **경계 1건의 단서**: coverage가 train 0.038(<0.05) / valid 0.057(>0.05)
  로 threshold를 걸친다. **gate 적용 통계의 기준 split을 명시해야 한다**
  — "train과 valid 모두 통과" 규칙(보수적, 권장)이면 pilot과 동일하게
  제외된다. 또는 threshold를 gap 중앙(≈0.15)으로 올리면 split 무관하게
  안정 제외된다. 선택은 연구자 결정 사항.
- 2021–2024 test 구간은 threshold 논의에 노출되었으므로(파일럿 보고서가
  test 분포·test IC를 인용) 최종 논문용 판정에는 **새 seed set**(제안
  job 2)의 test 평가를 1회성으로 쓰는 것을 권장. (데이터 번들이 2024년
  까지라 새 시간 holdout은 현재 불가.)

## V6. Orientation 단일 적용 감사 (추가 검증)

- 코드 경로: `runner.train_sign` → `OOSEvaluator.evaluate_factor` →
  `ctx.oriented(values, sign)`(신호에 1회 곱) → 지표는 oriented 신호에서
  계산. sign을 재적용하는 경로 없음 (`oos/evaluator.py` 모듈 규약 주석).
- 회귀 테스트 추가: `tests/synthetic/test_synthetic_suite.py::
  test_orientation_applied_exactly_once` — 역방향 예측자에 sign=−1 적용
  시 IC 부호만 반전·크기 보존 확인. **7/7 PASSED.**
- 따라서 gp_main의 test −0.35가 부호 처리 버그일 가능성은 배제.

## V7. 헤드라인 수치 독립 재계산 (추가 검증)

ASB 지표 코드를 전혀 쓰지 않고(qlib `D.features` + pandas만) 재계산
(`out/verification/independent_recompute.csv`):

| 수치 | 파일럿(ASB) | 독립 재계산 | 일치 |
|---|---|---|---|
| `Log($volume)` test IC | +0.021552 | **+0.021552** | 소수점 6자리 |
| `Log($volume)` test RankIC | +0.056354 | **+0.056354** | 〃 |
| gp_main sibling oriented test IC | −0.349462 | **−0.349462** | 〃 (IC 관측 44일도 일치) |

## 남은 결정 사항 (사용자)

1. validity gate 통계의 기준 split 규칙: **train+valid 모두 통과(권장)** /
   train만 / valid만 — config 명시 필요.
2. `oos.min_daily_n_for_ic` config 신설 여부 (기본 2 유지 시 무영향).
3. 경계 대비 threshold 상향(0.05 → 0.15) 여부.
4. 최종 판정용 fresh holdout: 새 seed set(제안 job 2) 채택 여부.

## 결론

여섯 지적은 모두 검증할 가치가 있었고, 그중 둘(지적 4의 −0.35 해석,
지적 5의 threshold 근거)은 보고서 수정으로 이어졌다. 그러나 **ASB의
평가 체인(신호 계산, PIT 분모, orientation, 지표 집계)에서 파일럿 결론을
무효화하는 결함은 발견되지 않았다.** 특히 마이닝 fitness 21/21 완전
재현은 "ASB가 마이닝이 본 것과 같은 세계를 평가하고 있다"는 것의 가장
강한 증거이며, gp_main 절대승자의 fitness 0.565217이 마이닝 창에서도
**유효 셀 57개/23일짜리 ±1 산술**이었다는 사실은 아티팩트 판정을 원천
데이터 수준에서 재확인한다.
