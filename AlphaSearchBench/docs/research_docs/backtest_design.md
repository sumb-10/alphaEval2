# ASB Backtest Design (ASB-P1.0-RC3)

상태: **pre-freeze release candidate** (개정 3차) — 본 명세는 §13의 freeze
선행 조건을 충족한 뒤 **ASB-P1.0으로 동결**한다. 현재는 동결 상태가
아니다. · 관련 문서: `docs/BACKTEST.md`(엔진 구현 계약),
`docs/METRICS.md`, `docs/experiments/`(근거 실험 기록), 연구 개요 Q1–Q4

---

## 0. 개요

AlphaSearchBench(ASB)의 backtest 층은 **alpha pool의 downstream 유용성과
배치 민감도를 측정하는 표준화된 측정기구**다. 최고 수익 전략의 전시가
목적이 아니며, 서로 다른 mining method가 산출한 pool을 비교 가능하게 만드는
것이 목적이다.

```
                     [입력 계약 §8]  수식 목록(필수) + 방향/가중/native 결합 명세(선택)
                          │
     ┌────────────────────┼──────────────────────┐
 Track A                Track B                Track C
 Common Deployment      Paper Anchor           Native / Repaired-native
 Suite (공식 비교)        (참고연구 정렬 참조점)     (원 방법의 결합 기제)
 동일 엔진 8구성          qlib top-50/drop-5      명세 제출 시에만
 2결합×2규칙×2비용        long-only·초과수익        fidelity 라벨 필수
     │                      │                      │
 family별 프로파일        Anchor 프로파일          Pure Combiner Lift /
 (§4)                    (§4)                   Native Deployment Gap (§9)
     │
 공식 순위·**primary** Q4 분석은 Track A에서만 (§10)
 (Track B는 supplementary Q4 robustness/external-alignment 분석)
```

---

## 1. 설계 철학

### 1.1 Backtest는 측정기구다

본 벤치마크의 연구질문(Q4)은 "pool의 Quality-Diversity 특성이 OOS·포트폴리오
성능과 연결되는가"이다. 포트폴리오 성능은 이 검정의 **종속변수**다. 따라서
backtest 층의 설계 기준은 수익 극대화가 아니라 **pool 간 차이를 왜곡 없이
드러내는 측정의 타당성**이며, 이후 모든 결정은 이 기준에서 도출된다.

여기서 QD와 backtest의 역할을 구분한다: **QD는 alpha-pool의 구조
분석**(행동 기술자 공간에서의 coverage·diversity)이고, **backtest 층은
downstream 강건성·민감도 분석**이다. 둘은 별개의 측정이며, 둘 사이의 관계를
조사하는 것이 Q4다.

### 1.2 식별 문제 — 성능은 곱이다

공표되는 모든 mining 성능은 다음의 곱이다:

```
발견한 수식 집합(pool) × 결합 방법(combiner) × 포트폴리오 규칙 × 비용 가정 × 실행 시맨틱
```

각 연구는 뒤의 네 요소를 자율적으로 선택하므로, 최종 성능의 직접 비교는
"pool이 좋은가"와 "배치 기계가 좋은가"를 식별할 수 없다. ASB는 이 곱을
분해하는 것을 설계 목표로 삼는다: pool을 고정하고 배치를 표준화하거나
(Track A), 배치를 원 명세로 두고 **native deployment 전체의 시스템 거동을
기술하며 — 조건을 통제할 수 있는 경우에 한해 — combiner 기여를 분리한다**
(Track C, §9). Track C가 pool 기여를 일반적으로 분리해 준다고 주장하지
않는다(§9의 단일 요인 귀속 금지와 동일 취지).

### 1.3 "동일"은 보장하되 "중립"은 주장하지 않는다

유일하게 공정한 combiner·포트폴리오 규칙은 존재하지 않는다. 어떤 결합
방식이든 특정 pool 형태(소수 정예형, 균질 다수형, 결합-시너지 전제형)에
서로 다르게 작용하는 귀납 편향을 갖는다. 따라서 Common 트랙의 주장은
"공정한 배치를 찾았다"가 아니라 다음이다:

> **모든 pool에 동일한(identical) 표준 배치를 가한 뒤 비교하며, 그 배치의
> 귀납 편향은 명세로 공개한다.**

같은 이유로 배치 조건을 하나로 고정하지 않는다. 단일 조건은 pool×배치
상호작용을 숨기므로, 소수의 사전 정의된 조건 집합을 적용하고 **배치
민감도 자체를 측정값으로 승격**한다(§4).

### 1.4 세 층위의 질문을 섞지 않는다

| 층위 | 질문 | 트랙 |
|---|---|---|
| L1 Native-protocol | 원 방법의 배치 기제 아래에서의 성능은? | Track B·C (참조) |
| L2 Standardized Pool | 동일 배치 아래에서 어느 pool이 유용한가? | **Track A (공식)** |
| L3 Controlled Search | 동일 DSL·목적함수·데이터·label·**탐색 예산**에서 GP/RL/LLM의 탐색 행동 차이는? | 별도 실험(Q1·Q2), 본 문서 범위 밖 |

L1을 "재현(reproduction)"이라 부르지 않는다. 원 연구들의 프롬프트·
하이퍼파라미터·구현 세부가 완전 공개되지 않는 경우가 일반적이므로, 가능한
것은 **공개된 배치·결합 프로토콜의 범위 내 재현(native-protocol)**이다.
주장 문구도 층위를 따른다: "방법 A가 B보다 우수하다"가 아니라 "동일 표준
배치 아래에서 A의 pool이 B의 pool보다 높은 downstream 유용성을 보였다".

---

## 2. 평가 트랙

### 2.1 Track A — Common Deployment Suite (공식 비교 트랙)

**단일 엔진 원칙**: Track A의 모든 구성은 동일한 ASB simple 엔진에서
실행된다. 백테스트 엔진이 다르면 거래가능성 처리·비용 기계·회전율 정의가
함께 달라져 "동일 배치" 보장이 깨지므로, 엔진이 다른 조건은 정의상 Track
A에 속할 수 없다(§2.2). 이 때문에 구성 집합을 **사전 정의된 배치 구성
(predefined deployment configurations)** 이라 부른다 — 아래 세 축은 완전
교차(2×2×2)이지만 **배치를 규정하는 축 전체에 대한 요인설계는 아니다**:
엔진·universe·실행 시맨틱 등은 고정 명세로 빼두었고 특히 엔진 축은 Track
A 정의상 변주할 수 없다. 즉 "요인설계"라는 명칭이 배치 전체를 실험 축으로
다룬다는 오해를 주므로 쓰지 않는다.

**구성 (2 × 2 × 2 = 8)**:

| 축 | 값 | 설계 근거 |
|---|---|---|
| Combiner | `raw_equal` / `train_signed_equal` | §3 — label-free 결합과 최소 지도(1-bit orientation) 결합의 대비 |
| 포트폴리오 규칙 | LS-Q: 분위 20/20 long-short, 매일 리밸런스 / LS-K: top-50 long-short, 5일 보유 | 회전 상한이 구조에 내재된 규칙과 아닌 규칙의 대비 — 비용 민감도를 규칙 차원에서 분리 |
| 비용 | 0bps / 15bps(편도 L1 기준) | 비용률 논쟁을 스윕으로 흡수. 0bps 구성이 gross/net 분해를 내장 |

**전 구성 공통(고정 명세)**: universe·PIT 멤버십 마스크, label(1일 forward),
실행 시맨틱 **`next_open_oo`**(canonical enum — t 종가 신호 → **t+1 시가
진입, t+2 시가 청산**: `open_{t+2}/open_{t+1} − 1`. `next_open`은 청산
시점을 규정하지 않아 `next_open_oc`와 혼동되므로 규범 문서에서 쓰지
않는다), 회전율·비용 정의(아래 수식), 첫날 건립 비용 부과, 연환산
규약(√252, ddof=1), gross 1(0.5 long / 0.5 short), 결측 수익 보유종목의
당일 손익 0 처리.

**회전율·비용 (수식 고정)**:

```
turnover_l1,t     = Σ_i |w_{i,t} − w_{i,t−1}|
turnover_oneway,t = 0.5 × turnover_l1,t
cost_t            = c × turnover_oneway,t,      c ∈ {0, 0.0015}
w_{i,0−1} ≡ 0     (첫날은 전량 신규 건립 → 건립 비용 부과)
net_t             = gross_t − cost_t
```

**포트폴리오 규칙의 재구현 명세**:

* **LS-Q**: 매일 리밸런스. long = `S ≥ Q_{0.8}`, short = `S ≤ Q_{0.2}`
  (해당일 valid 종목 위의 quantile, linear interpolation), **양쪽에 동시
  속하는 셀(퇴화 분포)은 양 leg에서 제거**하고, 어느 한 leg가 비면 그날은
  무포지션. 각 leg 내부 equal weight로 `0.5 / n_leg` (leg 크기는 tie·퇴화
  처리 결과이므로 정확히 20%가 아닐 수 있다).
* **LS-K**: 상위 K=50 long / 하위 K=50 short, 각 side equal weight
  (gross 1 = 0.5/0.5), **5거래일마다 전체 리밸런스하며 비리밸런스일에는
  직전 weight를 그대로 유지**한다(그날 회전 0) — **overlapping cohort
  방식이 아니다**. valid 종목이 2K 미만이면 `K ← floor(n_valid/2)`로
  축소하고, 그래도 0이면 무포지션(동수는 안정 정렬로 결정론적).

**Long-short의 지위**: A-share에서 임의 종목의 공매도 가능성을 가정하지
않는다. Track A의 LS 포트폴리오는 실배치 전략이 아니라 **신호 품질 진단
포트폴리오**(상·하위 순위 정보를 모두 사용하는 분석 도구)로 규정한다.
배치 지향 관점은 Track B가 담당한다.

### 2.2 Track B — Paper Anchor (참고연구 정렬 참조점)

qlib TopkDropout **top-50 / drop-5, long-only**, 체결 t+1 시가, 비용 매수
5bps/매도 15bps(비대칭), 성과는 **지수 대비 초과 AR·IR**. AlphaAgent
(KDD'25) §4.1.2의 배치층과 정렬된 **deployment-protocol anchor**다 —
**수치의 직접 비교는 dataset·universe·benchmark·기간까지 일치할 때만**
가능하며, 그렇지 않으면 "동일 배치층, 상이 데이터"로 명시한 정성 대조만
허용한다(§12 한계 5).

Track B는 qlib Exchange 엔진(상하한가·정지·min_cost·계좌가치 분모 회전율)
을 사용하므로 Track A와 **엔진이 다르다**. 따라서:

* Track A의 프로파일 집계(§4)에 포함하지 않는다.
* 별도 프로파일(초과 AR, IR, MDD_excess, 회전율)로만 보고한다.
* 롱온리 초과수익은 벤치마크 하락기에 확대되는 특성이 있으므로 벤치마크
  수익률을 병기한다.

### 2.3 Track C — Native / Repaired-native 결합

pool 제출 시 native 결합 명세(알고리즘+하이퍼파라미터)가 오면 그 명세로도
평가한다. 목적은 방법의 시스템 거동 설명과 결합 기여 분리(§9)이며, **방법
간 공식 순위에는 사용하지 않는다**.

**fidelity 명명 규칙**: 원 구현을 그대로 쓰면 `native`, 재현성·정확성을
위해 수정하면 `repaired-native`로 구분하고 수정 내역을 명세에 기록한다.
seed 고정처럼 결과 분포를 바꾸지 않는 패치와, 반복 횟수 정상화·선택 로직
수정처럼 **알고리즘 거동을 바꾸는 패치**는 구분해 후자만 repaired로
격상한다. pool 구성 단계의 수정본(예: HOF 재선발)도 동일 원칙으로 별도
식별자를 갖는다.

---

## 3. Combiner 명세

### 3.1 두 표준 combiner

모든 결합은 factor별 일별 단면 z-score(ddof=0, 결측→0) 위에서 정의된다.

**`raw_equal`** — wᵢ = 1/n. **label-free**: 어떤 지도 정보도 쓰지 않는다.
답하는 질문: "생성된 수식이 부호까지 포함해 그대로 결합 가능한가?"
수식에 방향이 내재된 pool(명시적 매매 방향을 가진 expert alpha 등)에
의미 있는 구성이다.

**`train_signed_equal`** — wᵢ = sign(train-IC ᵢ) / **|kept|**, 여기서
kept = §3.2의 부호 판정을 통과한 **directional component 집합**이다
(방향 없는 factor는 결합에서 제외되고 분모에서도 차감된다 — 전체 factor
수 n이 아니다). 이는 `oos_test_design.md` §6의 pool combiner 계약과 동일
정의이며 **L1-normalized directional equal weighting**이다(Σ|wᵢ| = 1,
일반적으로 Σwᵢ ≠ 1). 이는 무학습이 아니라
**1-bit 지도 보정(one-bit supervised orientation)**이다: label 정보를
방향 1비트만큼 사용한다. 답하는 질문: "방향만 보정해 주면 결합 가능한가?"

"Common combiner는 pool 구조를 직접 반영한다"고 주장하지 않는다. 두
combiner 모두 z-score → 방향 → 등가중 → 순위 → 포지션이라는 downstream
변환을 거친다. 정확한 주장은: **학습형 결합 대비 downstream 매개
(mediation)를 최소화한다**.

### 3.2 방향(orientation) 정책

방향의 기준 창은 **mining window(train)의 일별 IC 평균 부호**로 한다.
근거: (i) 방향 추정의 표본 크기 — 단년 캘리브레이션 창의 부호 추정은
표준오차상 불안정하다(일별 IC 표준편차 ~0.1, 1년 ~250 관측이면 SE≈0.006 —
|IC| 0.01 수준의 factor에서 부호가 동전던지기에 가까워진다). (ii) 벤치마크
내 일관성 — **OOS orientation 계약(train-side sign, `oos_test_design.md`
§5.1)** 과 방향원을 통일한다. 단 **QD Behavioral Core v2는 sign-invariant
(raw signal 기반, train_sign 불요 — `QD_Descriptors_v2.md` §2)** 이므로
orientation 정합성의 근거에 포함하지 않는다; QD 쪽에서 orientation을
소비하는 것은 `rre_qd` 등 supplementary diagnostic뿐이다.

**부호 판정 규칙(명세)**:

```
|train IC| >  τ_sign          → sign(IC)
|train IC| ≤  τ_sign          → 방향 없음: signed 결합에서 제외,
                                분모 |kept|에서 차감 (사유 기록)
IC 판정불가(NaN/관측 부족)     → 방향 없음: 동일 처리
τ_sign 기본값 = 0            → |IC| > 0 이면 부호 사용, **IC = 0은 방향 없음으로 제외**
                                (τ_sign=0이 "필터 없음"을 뜻하지 않는다)
```

**개별 orientation과의 이중 규약 (중요 — 오독 방지)**: 위 규칙은 **pool
combiner 경로**의 것이다. ASB의 **개별 factor orientation은 `sign = +1 if
sic ≥ 0 else −1`(0 → +1)** 이고(`oos_test_design.md` §5.1,
`validity_gate_design.md` §6), pool의 `train_signed_equal`은 τ_sign=0에서
**sic = 0을 방향 없음으로 제외**한다 — 두 경로의 0 처리가 다른 것은
**의도된 이중 규약**이며(`oos_test_design.md` §6에 명문화, 구현
`runner.py:100-107`의 `|sic| > τ`) "방향 증거가 없는 factor를 pool 방향
결정에 쓰지 않는다"는 취지다. 따라서 τ_sign=0을 "필터 없음 = 개별
orientation과 동치"로 해석해서는 안 된다.

**τ_sign 민감도의 범위 (계약)**: **Track A core는 τ_sign = 0만**이다 —
그래야 §2.1의 좌표가 정확히 2×2×2 = 8로 유지된다. `τ_sign = SE 근사치`는
**supplementary sensitivity analysis**이며 8-cell 프로파일·PDR·IQR 집계에
**포함하지 않는다**. SE의 정의는 **factor별**
`SEᵢ = sd(IC_{i,t}) / √nᵢ`(전 factor 공통 상수 0.006이 아니다 — 위
0.006은 전형값 예시일 뿐)로 고정한다.

Calibration 창(§6 — validation 2022-01-01~2023-12-31)의 부호는 **진단
정보로 기록**한다: **`sign_agreement_calibration`** = train 부호와
calibration 창 부호의 일치율. **명칭 주의**: 이는
`oos_test_design.md` §7의 `sign_preservation`
(= 1[sign(IC_valid) = sign(IC_test)])과 **다른 지표**이므로 같은 이름을
쓰지 않는다. 방향의 기준 창으로 calibration을 쓰지 않는 이유는 위 (i),
(ii)와 같다.

### 3.3 방향 시맨틱의 카테고리 구분

* **명시적 매매 방향을 가진 수식 집합**(예: Alpha101 — 수식 내 부호·조건이
  거래 방향을 정의): `raw_equal`이 1차 의미를 갖고, `train_signed_equal`은
  "시장·기간 이전(transfer) 시 방향 재보정"으로 해석한다.
* **방향 미정의 feature 집합**(예: Alpha158 — ML feature 라이브러리):
  `raw_equal`은 해석이 약하며 `train_signed_equal`이 1차 구성이다.
* mined pool은 fitness가 |IC|류(무부호)인 경우 방향 미정의로 취급한다.

---

## 4. 성과 프로파일 — family 내부에서만 집계

서로 다른 성과량(시장중립 Sharpe와 롱온리 초과 AR)은 하나의 분포로 합치지
않는다. 집계는 **동질 family 내부**로 제한한다.

**Track A(Common-LS) 프로파일** — 8구성에 대해:

| 범주 | 지표 |
|---|---|
| 성과 크기 | median Sharpe, median net AnnRet |
| 배치 민감도 | Sharpe IQR, **PDR(Positive Deployment Rate)** = Sharpe>0 구성 비율 |
| 하방 | worst Sharpe(tail 진단), median MDD |
| 비용 민감도 | gross→net 하락폭, 연회전율(편도) |

**Track B(Anchor) 프로파일**: 초과 AR, IR, MDD_excess, 연회전율, 벤치마크
수익률.

**PDR의 지위**: 기술적(descriptive) 강건성 진단이다. 임계 민감성(±0에서
0/1 반전)과 비대칭 손익 은폐 가능성이 있으므로 **단독 headline로 쓰지
않고 반드시 분산 지표(IQR)·worst와 함께** 제시한다. 구성들은 독립 표본이
아니므로 신뢰구간을 부여하지 않는다.

**종합 스칼라 점수는 만들지 않는다.** 범주 간 가중은 또 하나의 자의성이다.

---

## 5. Pool 크기 정규화

**Canonical dedup 규약 (채택)** — Track A의 pool 평가는
`oos_test_design.md` §6의 계약을 그대로 소비한다: **stable
`formula_id` 기준으로 dedup한 canonical 집합 위에서 결합**하며, raw
multiplicity가 가중으로 작용하도록 두지 않는다. 근거는 §1.2의 식별
문제다 — 방법별 중복 발생률 차이가 결합 가중에 유입되면 "pool 품질"과
"제출 형식"이 다시 섞여 분해 목적이 무너진다. 특정 factor에 더 큰 가중을
의도한다면 duplicate row가 아니라 §8의 `weights`로만 표현한다.

pool 크기는 방법의 산출물이므로 **기본 보고는 제출된 그대로
(as-submitted, dedup 후 canonical 집합 기준)** 이며 모든 표에
`n_factors_raw` / `n_unique_factors` / `duplicate_rate` /
`n_factors_dropped_by_gate`를 병기한다(실측 산출 필드명 —
`oos_pool_metrics`). 크기 효과의 분석은 다음 두 실험으로 분리한다:

* **1차 — rarefaction(무작위 부분표본)**: 각 pool에서 크기 k의 무작위
  부분집합을 R회 추출(k ∈ {10, 20, …}, R=100, seed 고정)해 Performance@k·
  Coverage@k·DE@k의 평균·분산 곡선을 얻는다. 품질 선택이 개입하지 않는
  순수 크기 통제이며, QD coverage에 이미 쓰는 rarefaction과 동일한 방법론을
  backtest로 확장한 것이다.
* **2차 — quality-selected subset ablation(별도 실험)**: 캘리브레이션 창
  기준 상위 k 선택 후 평가. 이는 크기 통제가 아니라 "선택 규칙의 효과"
  측정이며, 개별-지표 기준 선택이 결합-시너지형 pool에 갖는 구조적 불리함을
  명세에 기재한다.

---

## 6. 데이터 분할과 시간 무결성

### 6.1 분할의 역할 정의

**확정 split 채택 (C-0, 사용자 결정 2026-08-19)** — 본 문서는 프로젝트
공통 temporal split을 소비한다(정의 원본: `Vanilla_GP_v2.md` §6 ·
`GP_asb_design_v2.md`). 역할 매핑:

```
2015-01-01 ~ 2021-12-31   Mining window (= train)
                          — 탐색·fitness 산출. 내부 분할은 각 방법의 소관
2022-01-01 ~ 2023-12-31   Deployment calibration (= validation)
                          — downstream 전용 보정(부분표본 선택, 배치 파라미터,
                            부호 진단). candidate fitness 불개입, test 미참조
2024-01-21 ~ 2026-06-30   OOS test (동결)
                          — 최종 보고 전용. freeze 후 1회 평가
```

**판독 규칙 (사전 등록 — C-0와 동일)**: test 보고는 두 구간을 **병기**한다
— **Primary Full OOS** = 2024-01-21~2026-06-30(표본 확보용 주 구간),
**Strict Untouched Subset** = 2025-01-21~2026-06-30(번들 구성상 미접촉).
전반부(2024-01-21~2025-01-20)는 v1 development(구 test 2021–24) 관측과
겹치는 **부분 오염** 구간이므로 전체 test를 "완전 untouched"라 서술하지
않는다.

> **개정 이력**: 이전 판의 `2010–2019 / 2020 / 2021–2024` 표는 C-0 확정
> 이전의 legacy 타임라인이며 폐기한다. 구 `2021–2024`는 확정 체계에서
> **구 test**로 과거화되었고 train·validation 구간과 겹친다.

원칙: **선택은 calibration에서, 보고는 test에서.** test 구간에서의 어떤
파라미터·구성·부분집합 선택도 금지한다.

### 6.2 Purge / Embargo

경계 침범을 막기 위해, horizon h일의 forward 지표(label, 그리고 QD
**Performance-Response supplementary**의 multi-horizon 반응 — QD
Behavioral Core v2는 label-free이므로 core 4축은 해당되지 않는다,
`QD_Descriptors_v2.md` §9)를 계산할 때 **각 분할의 마지막 h 거래일은 다음
분할을 참조하지 않도록 절단(purge)**한다. 분할 간 embargo는 파이프라인이
산출하는 최대 horizon(현행 `qd.horizons` 최대값 = 20거래일)으로 설정한다. 적용 여부와 절단 일수는 manifest에
기록한다.

### 6.3 실행 시맨틱 표준화

Common 트랙의 체결은 `next_open`(t 신호 → t+1 시가)으로 통일한다. 이는
선견 편향 차단과 방법 간 비교 가능성을 위한 **의도적 표준화이며, 각 수식의
native 실행 시맨틱(예: delay-0 수식의 당일 체결 전제)을 덮어쓴다.** native
의도 타이밍은 메타데이터로만 보존한다.

---

## 7. Development / Post-freeze 확인 프로토콜

벤치마크 설계는 데이터와 상호작용하며 발전하므로, test 구간을 한 번도
참조하지 않은 설계란 존재하기 어렵다. ASB는 이를 은폐하지 않고 **단계
프로토콜로 관리**한다:

```
Phase D (development)   — 설계·수정 과정에서 test 구간 결과가 관찰된 단계.
                          이 단계의 모든 결과는 "development evidence"로 라벨.
      ↓  ASB-P1.0 freeze (본 문서 동결 + 프로토콜 버전 스탬프)
Phase C (confirmation)  — freeze 이후 처음 평가되는 대상에서 얻는 결과만
                          "confirmation evidence"로 인정.
```

**Confirmation evidence의 두 등급 (구분 의무)** — 강도가 다르므로 하나로
묶지 않는다:

| 등급 | 정의 | 비고 |
|---|---|---|
| **protocol-held-out confirmation** | freeze 후 처음 평가하는 method / seed / universe | 같은 test 구간을 설계 과정에서 반복 관찰했다면 **시간 홀드아웃 수준의 독립성은 아니다** |
| **temporal confirmation** (더 강함) | freeze 시점까지 전혀 관찰할 수 없었던 **새로운 시간 holdout** | §6.1의 Strict Untouched Subset이 여기 해당 |

confirmation evidence의 원천: freeze 이후의 신규 방법(예: Alpha101,
AlphaGen, AlphaQCM, QuantaAlpha), 신규 seed, 다른 universe(→
protocol-held-out), 그리고
**§6.1의 Strict Untouched Subset(2025-01-21~2026-06-30)**(→ temporal) —
이 구간은
번들 구성상 development 단계에서 계산 자체가 불가능했으므로 "새로운 시간
holdout"의 요건을 충족한다. 반대로 Primary Full OOS의 전반부
(2024-01-21~2025-01-20)는 부분 오염 구간이므로 그 구간만의 결과는
development evidence 취급을 벗어나지 못한다. 논문 서술에서 두 evidence class를 구분 표기하는 것을
의무로 한다. 이 구분은 약점의 고백이 아니라 벤치마크 신뢰성의 근거다.

---

## 8. 입력 계약 (범용성)

벤치마크의 범용성은 배치 규칙이 아니라 입구 규격에서 나온다.

**P1.0 계약 — Expression 입력(필수)**:

```
formula        qlib 표현식 문자열 (필수)
dsl_version    문법 식별자
direction      factor별 방향 (선택 — Track A에서는 metadata only, §3.3 해석 보조)
weights        factor별 가중 (선택 — Track C 전용)
native_spec    native 결합 명세 (선택 — Track C 활성 조건)
trajectory     탐색 궤적 (선택 — search-QD 분석 활성 조건)
category       mined | static_reference
```

**제출 direction·weights의 소비 규칙 (계약 — Track A 식별 논리의 핵심)**:

```
Track A:
  submitted direction → 사용하지 않음 (metadata only — §3.3의 카테고리 해석에만 참조)
  submitted weights   → 사용하지 않음
  raw_equal           → formula output의 native sign × 1/N_unique
  train_signed_equal  → sign(train IC) / |kept|      (§3.1·§3.2)

Track C:
  submitted direction / weights / native_spec 사용 가능 (명세대로)
```

Track A가 제출 가중을 쓰면 "모든 pool에 **동일한** 표준 배치"(§1.3)가
깨지고 §1.2의 분해 목적이 무너지므로, 이는 **금지**다. ⚠ 현행 구현은
`--weights`를 pool 결합 가중으로 소비하는 경로를 가지므로(pool
`weights_source = "input"`), Track A 실행 시 이 입력을 **무시하도록
강제**해야 한다(§13 체크리스트).

**제외의 층위 (계약 — §11.7과 정합)**: "제외"는 factor 단위와 run 단위가
다르다.

```
미해석 수식 / gate 탈락 factor  → pool 결합에서 제외 (사유·개수 기록)
gate 이후 빈 pool (run 단위)    → run 자체를 결과표에서 제거하지 않는다
                                 metrics = NaN
                                 evaluable = false
                                 reason    = "empty_pool_after_gate"
```

즉 factor는 제외하되 **run 행은 남긴다** — §11.6(음성 결과 동등 보고)·
§11.7(조용한 유실 금지)의 요구다.

**엔진 등가성 요건**: 복수 신호 엔진(자체 엔진 + qlib fallback)을 운용하는
한, 동일 연산자명이 상이한 시맨틱(순위 tie 처리, rolling 창 경계, ddof,
NaN 정책, min/max 오버로드, delay 시맨틱)을 가질 위험이 있다. **연산자
단위 parity 테스트 스위트**를 계약의 일부로 유지하며, fallback 경로로
평가된 factor는 `signal_engine` 필드로 식별한다.

**P1.1 로드맵 — Precomputed Signal 입력**: `(date, instrument, factor_id,
value, availability_timestamp)` 형식의 사전계산 신호 입력을 허용하면
DSL 비호환 방법(대체 데이터, 코드 생성 신호 등)까지 수용된다. 단
look-ahead 통제를 위해 availability timestamp를 필수로 하며, 수식 기반
분석(정적 검사, 복잡도류 descriptor)은 결손됨을 명세한다. P1.0의 차단
요건이 아닌 버전업 항목이다.

---

## 9. 결합 기여의 분리 — Lift와 Gap

Native와 Common의 성과 차이를 하나의 이름으로 부르지 않는다. 통제 수준에
따라 두 지표로 분리한다:

**Pure Combiner Lift** — 다음이 모두 동일할 때만 정의:
동일 pool(수식 집합), 동일 포트폴리오 규칙, 동일 비용, 동일 실행,
**동일 평가 구간, 동일 성과 지표**. 오직 결합 알고리즘만 교체한다.

```
Lift(method, rule, cost) = Perf(native combiner) − Perf(standard combiner)
```

해석: 결합 최적화가 pool 품질 위에 더하는 순수 기여. 결합-인지형 탐색을
하는 방법(RL의 시너지 보상 등)에서 특히 정보량이 크다. 권장 ablation:
동일 pool에 {raw_equal, train_signed_equal, native 결합} 3종을 적용하는
결합 사다리.

**Native Deployment Gap** — native 파이프라인이 입력 확장(기저 factor
추가), 선택, 비선형 모델링 등 결합 외 요소까지 포함할 때:

Track A에는 **표준 배치가 8개** 있으므로 스칼라 하나로 정의할 수 없다.
**구성·지표별 vector로 정의한다**:

```
Gap_{m,c,μ} = Perf_μ(native 전체 배치, method m)
            − Perf_μ(Track-A 구성 c,   method m)
   c ∈ 8구성,  μ = 성과 지표
```

**정의 조건 (필수)**: 동일 지표 μ·동일 평가 구간·동일 pool일 때만 수치
Gap을 계산한다. native가 롱온리 초과 AR이고 Track A가 시장중립
Sharpe처럼 **성과량이 다르면 감산 자체가 무의미**하므로 그 경우에는
**side-by-side 프로파일만 병기**한다(§4의 family 규율과 동일). 단일 대표
구성을 골라 Gap을 스칼라화하지 않는다 — 그것은 §1.3의 "단일 조건 고정
금지"에 반한다.

Gap은 복합 차이이므로 "이 방법의 가치는 결합기에 있다"는 식의 단일 요인
귀속을 금지한다. 분해가 필요하면 요소를 하나씩 이동시키는 계단식 ablation
으로만 주장한다.

---

## 10. Q4 통계 분석 계획

**분석 단위는 pool(run)이다.** 배치 구성은 pool의 반복 조건이므로 표본
수를 늘리지 않는다 — 10 pool × 8구성은 n=80이 아니라 n=10이며, 프로파일
(§4)은 pool 하나를 요약하는 특징 벡터다.

**Track 범위 (계약)**: **primary Q4 분석은 Track A만** 사용한다(공식
순위와 동일 — §0·§2.3). Track B(Anchor) 기반 연관 분석은 **supplementary
robustness / external-alignment 분석**으로만 보고하며 primary 결론을
번복하지 않는다 — 엔진·성과량이 다르므로(§2.2·§4) Track A 결과와 하나의
분포·하나의 결론으로 합치지 않는다.

**결과 변수는 family별로 정의한다**: 예측력(pool IC·RankIC·ICIR),
Common-LS(median Sharpe, IQR, PDR) — **primary**; Anchor(초과 AR, IR) —
**supplementary**. 질문도 family별로 구체화된다(예: primary "coverage는
시장중립 강건성과 연관되는가", supplementary "DE는 롱온리 IR과 연관되는가").

**교란 통제**: pool 관측은 IID가 아니다 — 같은 method의 seed들은 method
정체성을 공유한다. 최소 분석 세트:

1. pooled association (전체 상관 — 참고용)
2. **within-method association** (method 고정 후 잔여 상관 — method 교란 제거)
3. universe-stratified association
4. 탐색적 회귀: `Perf = β₀ + β₁·QD + γ_method + δ_universe + ε`
   (run 클러스터링 고려)

**추론 강도 규율**: 현 표본 규모에서는 전 결과를 기술통계로 보고한다.
연관성에 대한 공식 추론은 pool 관측이 수십 규모(methods × seeds ×
universes)에 도달한 뒤로 유보하며, 소표본 구간의 구간 추정치는 사용하더라도
"exploratory"로만 라벨한다. **보고 형식 (계약)**: 위 4번 회귀는 현
규모에서 **점추정치와 표본 수만 exploratory 라벨로 제시**하고 p-value·
유의성 판정·모형 선택 비교는 보고하지 않는다 — 회귀식을 명세에 두는 목적은
사전 등록된 통제 구조(method·universe 고정효과, run 클러스터링)를 고정하는
것이며 지금 단계에서 추론을 개시하는 것이 아니다.

---

## 11. 무결성 규칙

1. **전 구성 보고 의무** — 어떤 주장에도 해당 family의 전 구성 표가
   딸려간다. 개별 구성 인용 시 좌표(결합·규칙·비용) 명시.
2. **선택은 calibration, 보고는 test** (§6.1).
3. **판독 규칙 사전 등록** — "무엇이 나오면 무슨 결론"을 문서로 고정한다.
   **소급 적용 불가**: development evidence(§7 Phase D)에는 사후 적용할 수
   없으므로, **P1.0 freeze 이후 confirmation run을 실행하기 전에** 고정한다.
4. **gross/net 상시 분해** — **Track A**는 동일 rule·combiner의
   0bps/15bps pair로 비용 효과를 항상 분리한다. Track B(비대칭 5/15bps)·
   Track C는 이 pair 구조를 갖지 않으므로 이 규칙의 적용 대상이 아니다.
5. **방향 정책 준수** — §3.2의 부호 규칙 외의 방향 조정 금지.
6. **음성 결과 동등 보고** — 전 구성 손실인 pool도 동일 형식으로 기록한다.
7. **조용한 유실 금지** — 평가 불가·gate 탈락·빈 pool은 사유·개수와 함께.
8. **evidence class 표기** — development / confirmation 구분(§7)을 모든
   결과 표에 적용한다.

---

## 12. 의도적 배제와 한계

**배제(설계 결정)**:

* Native end-to-end 완전 재현 — §1.4의 정보 비공개 문제로 정의상 불가.
  배치층 정렬(Track B)과 결합 명세 재현(Track C)까지만.
* 학습형 결합의 Track A 편입 — 학습이 pool 결함을 보정해 pool 품질과
  결합 품질을 재혼합한다(§1.2). Track C 전용.
* 구성 집합의 무증거 확장 — 축 추가는 "pool 순위를 바꾼다는 증거"가 있을
  때만 버전업으로 수용한다.
* 종합 스칼라 점수 — §4.

**세부 계산 규약 (freeze 전 확정 — 재구현 가능성 확보)**:

| 항목 | 확정 규약 |
|---|---|
| LS-Q leg 산정 | quantile threshold(linear interpolation) 기반 membership. tie·퇴화로 leg 크기가 정확히 20%가 아닐 수 있고, overlap 셀은 양 leg에서 제거, 한쪽 leg 공백이면 그날 무포지션 (§2.1) |
| LS-K K 초과 | valid < 2K이면 `K ← floor(n_valid/2)`, 그래도 0이면 무포지션. 동수는 안정 정렬로 결정론적 (§2.1) |
| z-score zero-variance day | 일별 cross-sectional std < 1e-8이면 std를 1로 치환(ddof=0), 결측 셀은 z = 0 — `QD_Descriptors_v2.md`·OOS pool 규약과 동일 커널 |
| all-zero combined signal day | 유효 신호가 전무해 leg 구성이 불가하면 그날 weight 전부 0(무포지션)이며 `n_skipped_days` 진단으로 계수 |
| quality-selected subset(§5 2차) | 선택 지표 = **calibration 창의 pool-level 예측 지표(Mean IC)**, 동점은 `formula_id` 사전순 tie-break, 선택 규칙은 사전 등록 |
| rarefaction(§5 1차) | `k ≤ n_unique_factors`만 산출, `n_unique_factors < min(k)`인 pool은 rarefaction 미산출(NaN + 사유). 비복원·고정 seed |
| MDD | **양수 크기(magnitude)** 로 보고한다(`max_drawdown_magnitude` — 부호 없는 값) |
| AnnRet headline | Track A headline은 **산술 연환산 `AnnRet_arith` = mean(daily net) × 252**. `CAGR`은 병기 지표이며 headline이 아니다 |
| Track C `native_spec` | fitting window, refit cadence, seed, model state/input 의존성을 **명세에 기재**해야 Track C 평가가 성립한다(미기재 시 평가 불가로 기록) |

**한계(공개 항목)**:

1. 구성 집합 자체가 선택이다. 근거(참고연구 배치층 명세 + 자체 계약)를
   문서화할 뿐 자의성을 제거하지는 못한다.
2. PDR·IQR은 비독립 구성들 위의 기술 지표다(추론 금지).
3. 시장충격·호가스프레드·차입비용·공매도 제약은 모형화하지 않는다 —
   LS는 진단 포트폴리오다(§2.1).
4. Track B의 초과수익은 벤치마크 하락기에 확대된다(벤치마크 수익 병기 의무).
5. universe·benchmark가 참고연구와 다른 경우 Anchor 비교는 "동일 배치층,
   상이 universe"임을 명시한다.

---

## 13. 버전·동결·구현 지도

**버전 규율**: 본 명세는 아래 freeze 선행 조건을 충족한 뒤 **ASB-P1.0으로
동결한다**(현재 상태는 `ASB-P1.0-RC3`, pre-freeze). 동결 이후 스윕·평가
manifest에 `protocol_version = "ASB-P1.0"`을 스탬프한다. 구성·규칙 변경은 버전 증가와 변경 근거
문서를 동반하고, 버전 간 대조표(기존 pool 전체 재평가)를 남긴다.

**버전 명명의 층위 (계약)**: `protocol_version`은 **배치 프로토콜(본
문서) 전체의 버전**이고, 축별 규약 버전은 각 축 문서가 따로 갖는다 —
`oos_protocol_version`(oos_test_design §7), `qd_protocol_version`·
`descriptor_protocol_version`(qd_test_design §2.3, QD_Descriptors_v2).
서로를 포함하지 않는 **병렬 버전**이므로 manifest에는 해당되는 것을 모두
기록하고, 어느 하나가 바뀌면 그 축의 결과 의미가 달라진다는 해석을
동일하게 적용한다.

**freeze 선행 조건(구현 체크리스트)**:

| 항목 | 상태 |
|---|---|
| Track A 포트폴리오 규칙 2종·비용 스윕·엔진 고정 | 구현됨 (`backtest.selection/topk/rebalance_days/transaction_cost_rate`) |
| Track B qlib anchor + 초과수익 지표 | 구현됨 (`backtest.mode: qlib`, `AnnRet_excess/IR/MDD_excess`) |
| 스윕 러너(공식 평가 경로 재사용) | 구현됨 (`scripts/protocol_sweep.py`) |
| `train_signed_equal` combiner (+부호 정책 τ_sign) | **구현됨** (`runner.py:66-71` combiner 검증 + `pool_weights`의 directional filtering, `default.yaml:105-106` `backtest.combiner`/`backtest.sign_threshold: 0.0`) — 단 분모는 `|kept|`이고 코드 주석의 `/n` 표기는 stale(§3.1) |
| canonical `formula_id` dedup 적용(§5) | 미구현 (현행 pool 결합은 입력 목록 그대로 — `oos_test_design.md` §6 충족도와 동일 상태) |
| **Track A의 제출 `weights`/`direction` 무시 강제(§8)** | 미구현 — 현행은 `--weights`를 pool 가중으로 소비(`weights_source="input"`). Track A 실행 경로에서 차단 필요 |
| 실행 시맨틱 `next_open_oo` 고정(§2.1) | 구현됨 (`labels.execution_return`의 canonical enum; config에서 모드 고정 필요) |
| 빈 pool의 run-level placeholder(`empty_pool_after_gate`, §8) | 미구현 — 현행은 `len(pool_f) >= 1` 가드로 pool 행을 생성하지 않음(silent skip) |
| τ_sign sensitivity를 8-cell 집계에서 분리(§3.2) | 미구현 (스윕 러너의 집계 범위 규칙) |
| rarefaction 크기 정규화 | 미구현 (QD의 `rarefaction_coverage` 패턴 확장) |
| family별 프로파일 집계(PDR·IQR 등) | 미구현 (스윕 산출물 후처리) |
| purge/embargo 적용·기록 | 미구현 (코드에 해당 경로 없음) |
| 연산자 parity 테스트 스위트 | 부분(엔진 동등성 재현 테스트 존재, 연산자 단위는 미비) |
| `protocol_version` manifest 스탬프 | **배선 구현됨, 값 미설정** (`manifest.py:41`이 `protocol.version`을 스탬프, `default.yaml:100-101`은 `null` → 기록값 `"unversioned"`. freeze 시 `ASB-P1.0` 주입 필요) |
| C-0 split(§6.1) 적용·판독 규칙(Primary/Strict) 배선 | 미구현 (split 주입은 experiment config 소관, 이중 판독 집계는 후처리) |
| Track C native 결합 3종(선형/동적/모델) | 방법 편입 시점에 각각 |

**부록 — 근거 기록 포인터**: 설계 결정의 실증 근거(배치 조건이 pool 순위를
바꾸는 사례, 비용 분해, 결합기 비중립성 사례, 참고연구 배치층 명세 검증)는
`docs/experiments/`의 해당 실험 보고서(E1–E3)와 REPORT.md §8–10에 기록되어
있다. 본 문서는 규범 명세로서 그 기록에 의존하되 서술을 반복하지 않는다.
