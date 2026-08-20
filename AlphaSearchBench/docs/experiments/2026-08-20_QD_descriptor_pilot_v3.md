# QD Primary Behavioral Core — descriptor 정의 검증 파일럿 v3 (evidence)

목적: `qd_test_design.md` 집필 전, Primary Behavioral Core 후보
{B, T, A_L, A_V}의 **정의 자체를 freeze할 실측 근거** 생산. 성능(IC/수익)
지표는 일절 계산하지 않는 순수 behavior 기술 — label-free·sign-invariant.
**최종 확정은 사용자 게이트** (§7).

## 1. 설계

* 컨텍스트: expB ASB eval manifest 재사용 (csi800, **valid 2017-2019만**
  사용; test split은 2020으로 축소해 동결 test 2024-01-21+ 비적재).
* 표본: final_pool unique 183 (GP pilot 132 + AlphaAgent expB LLM 51;
  usable 156 — LLM 26건 평가 실패는 §6).
* descriptor:
  * **B** = `activation_breadth` (기존 구현 재사용, inverse-Herfindahl).
  * **T_common** = 인접일 공통 유효셀에서 양일 **re-z-score 후 L1 정규화**,
    `0.5·Σ|Δw̃|` 평균 (L1-only 변형·T_union 병기, pair 진단 기록).
  * **characteristic tilt 후보 3종** (liq = Amihud ILLIQ20 percentile
    q∈[0,1] (1=유동), vol = VOL_W percentile (1=고변동), W∈{20,60,120},
    ILLIQ min_periods∈{10,20}):
    * `A^W = E_t|Σ w̃·(2q−1)|` — weighted tilt (intersection re-z-score)
    * `A^Q = E_t|q̄_top20%(S) − q̄_bot20%(S)|` — quantile characteristic
      spread (backtest `long_short_quantile=0.2` equal-weight L/S와 정합)
    * `A^ρ = E_t|Spearman(S, q)|` — rank alignment benchmark
* **B–tilt 기계적 결합의 permutation null**: characteristic을 일별로
  종목 간 permutation (K=3, seed 20260820, L20·V20) → `Corr(B, A^null)`.
  해석적 예측: null 하 `Var(X^W) = σ_c²·Σw̃² = σ_c²/(N·B)` — W만 B에 결합.
* 일별 최소 공통 종목 수 30 (exclusion rate {2,10,30} 기록).
* 실행: `scripts/qd_descriptor_pilot.py`, Slurm **890554** (COMPLETED
  26:12). 890549는 tie-assert 결함(§6)으로 실패, 890543(v2)·890492(v1)는
  판독 전 정의 개정으로 취소 — 결과 기반 재시도 아님.
* 산출: `out/qd_design_pilot/qd_descriptor_pilot_v3_valid.parquet`
  (수식별 signed/mass_covered/exclusion/null 포함).

## 2. 핵심 결과 — B–tilt null coupling (후보 판정)

| 후보 | Corr(B, A^null) L20/V20 | null 평균 | real 평균 | Corr(B, A^real) |
|---|---|---|---|---|
| A^W | **−0.82 / −0.81** | 0.048 | 0.284 | −0.48 / −0.28 |
| A^Q | **+0.07 / +0.17** | 0.030 | 0.308 | −0.39 / −0.25 |
| A^ρ | +0.11 / +0.11 | 0.033 | 0.388 | −0.41 / −0.27 |

B tercile별 null 평균 (L20): W **0.082 → 0.038 → 0.032** (low→high B) /
Q 0.027 → 0.027 → 0.034 / ρ 0.029 → 0.030 → 0.038.

**판정: A^W는 characteristic과 무관한 null에서도 B에 강하게 결합
(해석적 예측 그대로) → primary 탈락 근거. A^Q·A^ρ는 결합 없음.**
real 신호는 세 후보 모두 null 바닥의 ~7–12배로 실재. GP-only에서도 동일
(−0.75 / +0.05 / +0.02). **권고: A^Q primary, A^ρ supplementary, A^W는
진단 전용.**

## 3. 분포·판별력 (A^Q 기준)

| | GP (n=132) | LLM (n=24) |
|---|---|---|
| B | 0.25 [p25 0.09, p75 0.30], max 0.77 | 0.52 [0.33, 0.66] |
| T_common | **이봉**: 64개 ≤0.1 / 40개 >0.5 | 0.17 [0.09, 0.32] |
| L20_Q | 0.17 [0.11, 0.64] | 0.11 [0.09, 0.13] |
| V20_Q | 0.15 [0.08, 0.34] | 0.13 [0.10, 0.19] |

* **face validity**: L20_Q 최고 = `Min($amount,5)` 0.71(거래대금 factor —
  당연히 최대 liquidity tilt), 최저 = `Div($adjclose,$high)` 0.05
  (가격비율 — 중립). V20_Q 최고 = vol-of-vol 계열 0.43. B 최저 =
  `Var(Var($amount))` 스파이크 집중 0.02, 최고 = Rank/Rsquare 유계 출력
  0.77. T_common 최고 = `Less(...)` 이진 지표 0.727, 최저 = EMA 체인 ~0.
* T_common의 GP 이봉성(빈도 [64,10,5,3,3,8,26,6], bin 0.1 간격)은 binary
  지표 vs smooth factor의 실제 스타일 분리 — binning은 등간이 아니라
  분위/고정경계 설계 필요.
* signed 방향(참고): GP는 평균 liquid-long(+0.157)·highvol-long(+0.108)
  tilt, LLM은 거의 중립. persistence(|E[X]|/E|X|): L20 median 0.43
  (지속 43% / 진동 38%), V20 median 0.89.

## 4. 중복성

* 4×4 Spearman (Q 시나리오): B–T 0.29, B–L −0.39, B–V −0.25, T–L −0.55,
  T–V −0.58, **L–V 0.60**. 전부 |ρ|<0.8 — 4축 유지 가능.
* **L–V는 Pearson 0.85로 높지만 원인이 특정됨**: L20_Q≥0.5 클러스터
  49개(전원 $amount/$volume 포함 — 거래활동 factor family)가 두 tilt를
  동시에 올림. **클러스터 밖(n=94)에서는 Pearson 0.09 / Spearman −0.14로
  사실상 독립.** 즉 정의적 중복이 아니라 실질 행동(volume 계열은 실제로
  두 특성 모두에 기울어짐) — 두 축 유지 타당. 네 축은 orthogonal이
  아니라 **distinct but potentially correlated behavioral dimensions**로
  서술하며, L–V pair의 실질 상관은 pairwise QD map·4D redundancy
  diagnostics에서 명시적으로 해석한다(PCA는 primary QD에서 폐기됨 —
  QD_Descriptors_v2.md §1).
* T_common ↔ stored `rre_qd`: **−0.95** (n=156 join) — RRE와 동일 정보
  재확인 → RRE는 supplementary로 이동, T_common이 대체.
* **정정(중요)**: T↔coverage −0.71이 common-universe에서도 잔존.
  이전의 "union+zero churn 오염" 해석은 부분만 옳음 — 상당분은
  저커버리지·binary 계열 수식이 실제로 빠르게 변하는 실질 연관.
  T_common 채택 근거는 "churn 채널의 원리적 차단 + ordering 보존
  (T_union과 0.97)"으로 서술해야 한다.

## 5. 사양 파라미터 실측

* **A_V window**: 20/60/120 ordering 안정 (Q: ρ 0.87–0.98; 평균
  0.198/0.184/0.163) → W=20 freeze의 자의성 낮음.
* **ILLIQ min_periods 10 vs 20**: ρ≥0.996, days_used 차이 3일 — 무차이.
* **min_cross_section_n=30**: 제외일 평균 14.0/731 (n<10 대비 +4.1일),
  days_used 평균 642, mass_covered 평균 0.924 — 30 채택 비용 미미.
* T_common re-z-score vs L1-only: ρ=1.00 — 정의 강건(re-z-score를
  primary로 두는 근거는 Σw̃=0 보장이라는 원리성).

## 6. 무결성·실패

* expB B 재계산 == 저장 `valid_activation_breadth` (n=24, max|Δ|=0) —
  컨텍스트 재현 정확.
* sign-invariance assert (S→−S): B/T/W/ρ 전부 통과. **A^Q는 tie-heavy
  수식 2개(IdxMin/IdxMax 계열)에서 Δ≤3.2e-3 비대칭 — 이는 파일럿의
  근사 membership(`k=int(0.2n)` argsort fixed-k)이 만든 아티팩트이며
  허용 오차가 아니다.** production 규약(QD_Descriptors_v2.md §6.3:
  backtest quantile-threshold membership, Q=linear interpolation,
  inclusive 비교, overlap 제거)에서는 quantile equivariance
  Q_p(−v)=−Q_{1−p}(v)로 ±S에서 두 leg가 tie 포함 정확히 교환되므로
  **구조적으로 발생 불가**. 890549 실패는 이를 strict assert로 뒀던
  스크립트 결함(정의 문제 아님).
* eval_error 26건 = 전부 LLM: bare_field_name 24($ 접두 없는 expB 표기 —
  ASB 자체 평가에서도 동일하게 탈락했던 수식들과 일치), qlib_native
  TypeError 2. 새로운 실패 아님.

## 7. 사용자 게이트 — **전건 확정 (2026-08-20 사용자 승인)**

1. ✅ tilt primary = **A^Q** (A^ρ supplementary, A^W 진단 전용 강등).
   확정 명칭: **Liquidity / Volatility Characteristic Spread**
   (Alignment·Tilt Strength 명칭 폐기).
2. ✅ A_V window = **20** freeze (60/120은 민감도 기록 보존).
3. ✅ min_cross_section_n = **30**.
4. ✅ ILLIQ min_periods = **10** — 표기는 **ILLIQ20(min_obs=10)**.
5. ✅ core = {B, T_common, A_L^Q, A_V^Q} = **QD Behavioral Core v2,
   Frozen 2026-08-20** (이후 변경은 새 protocol version 요구); 기존
   IC 기반 4종(horizon/volatility/market/liquidity response)은 삭제하지
   않고 Performance-Response supplementary로 이동; RRE·A^ρ·A^W·T_union은
   supplementary/diagnostic. frozen spec 전문: `docs/QD_Descriptors_v2.md`.
   다음 단계(`qd_test_design.md` 목차)는 사용자가 별도 진행.

## Caveats

1. LLM usable n=24 소표본 — LLM 분포 수치는 참고용.
2. 컨텍스트가 expB manifest(2017-2019 valid) 기준 — GP v2 공식 창
   (2015-2021)과 다름. 이 파일럿은 descriptor **정의 선정의 근거**이며
   공식 benchmark calibration이 아니다. 공식 컨텍스트에서 재수행할
   것은 **binning calibration과 최종 reference distribution 산출뿐**
   (descriptor 재선정 아님 — qd_test_design.md 소관).
3. permutation null은 characteristic의 일별 분포만 보존(섹터 구조 파괴) —
   결합 채널 검증 목적에는 적합하나 null 절대값 자체의 해석은 제한적.
4. A^Q의 top/bot 20%는 equal-weight — backtest와 정합이지만 signal
   magnitude 정보는 membership에만 반영됨(의도된 설계).
