# QD Test Design — Quality-Diversity 평가 프로토콜 (normative spec)

> 문서 성격: **설계서·사양서** — 본문은 계약(contract)을 선언하고, 현행
> 구현이 이를 얼마나 충족하는지는 각 절 말미의 annotation으로만 표시한다.
> **`ASB_design_v2.md`가 framework 계약 정본이며 축 공통 계약(identity·
> 직렬화, split·purge, undefined 규약, placeholder·reason taxonomy, pool
> 객체 2층, 판독 단위, evidence class)의 owner다** — 본 문서는 그
> 소비자다. 시리즈: `validity_gate_design.md` → `oos_test_design.md` →
> **본 문서**.
>
> **인용 규약**: 구 `ASB_design.md`(v1)는 폐기된 문서이므로
> **`[v1-hist]` = historical implementation evidence**(구 구현이 그렇게
> 동작했다는 증거)로만 인용하며 normative anchor로 쓰지 않는다. 계약
> 층위의 참조는 전부 `ASB_design_v2.md`다(v2 §14.2의 delta 표).
> Behavioral descriptor의 정의·수식·파라미터는
> **`docs/QD_Descriptors_v2.md` (Core v2, Frozen 2026-08-20)** 가
> normative source이며 본 문서는 이를 재정의하지 않는 소비자다.

**상태 어휘 (3값 + 1)** — 절별 annotation에 사용:

- **Implemented**: 현행 구현이 본 사양을 충족.
- **Proposed**: 본 문서가 채택한 사양이나 구현 변경 필요 ("미결정 제안"이
  아님).
- **Not implemented**: 사양은 정의됨, 대응 구현 전무.
- **Deferred parameter**: 사양(결정 절차·freeze 시점)은 본 문서가
  규정하되, **실제 값은 pre-test runbook / protocol manifest가 채우는
  파라미터** (§10.7의 Deferred 목록 참조 — \(K_j\), \(\tau_q\),
  budget cap, rarefaction \(n/R/\text{seed}\), bootstrap
  level/\(B_{boot}\)/seed, range-collapse \(\epsilon\), reference
  population rule). Proposed와 혼용하지 않는다 — Proposed는 값까지
  확정된 사양이다.

**Legacy는 status가 아니다** — 위 상태 체계의 네 번째 값으로 쓰지
않고, 해당 구성 요소에 `Implemented` + **classification tag =
legacy / non-normative**를 부여한다 (예: PCA projection 경로 — §3.2,
§10.8).

---

# 1. Overview, Scope & Evaluation Contract

## 1.1 파이프라인 내 위치와 목적

ASB 평가 축: **Validity → OOS → QD → Backtest**. QD Test는 mining
method가 제출한 alpha 집합에 대해 다음 세 질문에 답한다:

1. alpha들이 **어떤 behavioral region을 탐색**했는가,
2. 그 region들에서 **얼마나 좋은 alpha를 발견**했는가,
3. method별로 **얼마나 넓고 균형 있게** 탐색했는가.

## 1.2 기본 객체 — behavior와 quality의 분리

\[
\alpha \;\mapsto\; \big(\, b(\alpha),\; q(\alpha) \,\big)
\]

- \(b(\alpha) = [B,\ T_{common},\ A_L^Q,\ A_V^Q]\) — **QD Behavioral
  Core v2** (label-free·\(\pm S\) 불변; 정의는 QD_Descriptors_v2.md §11).
- \(q(\alpha)\) — OOS Test 축이 산출한 predictive quality (§5).

behavior 좌표에 quality가 스며들지 않고, quality 판정에 behavior가
개입하지 않는다 (QD_Descriptors_v2 §2 원칙 1과 동일 철학).

## 1.3 QD Test가 하지 않는 것

- behavioral descriptor의 **재정의** (QD_Descriptors_v2가 유일 source).
- mining fitness의 변경 — QD는 사후 평가 축이지 탐색 목적함수가 아니다.
- portfolio backtest의 대체 — 투자 성과는 Backtest 축 소관.

## 1.4 두 scope의 사전 구분

| | **Final-Pool QD** (§6) | **Search-QD** (§7) |
|---|---|---|
| 대상 | miner가 제출한 최종 pool의 factor | 탐색 과정의 all-candidates |
| 질문 | 제출물이 얼마나 다양·우수한가 | 탐색이 어떻게 진행됐는가 |
| primary split | VALID calibration → **TEST frozen 평가**(report window 2종 산출, **primary는 `primary_full`** — §2.4) | **VALID** (§7.2) |
| grid resolution | scope별 분리 가능 (§4.5) | 〃 |

## 1.5 용어표

| 용어 | 정의 |
|---|---|
| behavior space | core 4축이 만드는 좌표 공간 |
| niche / bin | frozen edge로 이산화된 behavior space의 셀 |
| occupancy | 한 bin에 ≥1개 alpha가 배치된 상태 |
| coverage | 점유 bin 비율 (§4.2 분모 규약) |
| quality overlay | bin·alpha에 quality를 결합한 판독 계층 |
| HQ alpha | \(q \ge \tau_q\)인 alpha (§5.3) |
| reference distribution | edge calibration에 쓰는 VALID 기준 분포 (§4.1) |
| rarefaction | 고정 n subsampling으로 표본 크기 보정 (§6.6, §7.5) |
| B_unique / B_attempt | **mining run 내 처음 관측된** distinct `evaluation_key` 수(실패 포함 — 물리적 cache miss가 아니다) / distinct `proposal_event_id` 수 (§7.3) |

---

# 2. Inputs, Eligibility, Identity & Split Discipline

## 2.1 입력 단위

alpha 1행 = { `formula`, `formula_id`(또는 `evaluation_key`),
**`factor_set_id`**(Final-Pool), `submission_id`,
`evaluation_context_id`, `split`, **`report_window_id`**(TEST 집계),
`descriptor_protocol_version`, `mining_run_id`, `mining_seed`,
`proposal_event_id`·`generation`/candidate index(Search-QD),
OOS quality metrics, Behavioral Core 4값 + intermediate }.

**용어 주의**: `run`은 문맥에 따라 mining run과 evaluation run을 모두 뜻할 수
있어 쓰지 않는다 — **`mining_run_id`**(탐색 실행)와
**`evaluation_run_id`**(ASB 평가 실행)를 구분하고, seed도
`mining_seed`·`pfs_seed`·`draw_seed`·`bootstrap_seed`로 분리한다
(`ASB_design_v2.md` §1.5).

**Final-Pool의 key는 `pool_id`가 아니라 `factor_set_id`다 (계약 —
`ASB_design_v2.md` §3.1 ②·§3.6)**: QD는 결합이 아니라 **제출된 factor
집합의 behavioral 다양성**을 측정하므로 identity가
**combiner-independent**여야 한다. `pool_id`는 combiner·resolved
weights를 포함하므로, Backtest Track A처럼 같은 집합에 combiner 2종을
적용하는 경우 하나의 제출물이 `pool_id` 2개를 낳아 **QD 행이 중복되거나
어느 combiner의 ID를 쓸지 모호해진다**. `pool_id`는 pool OOS·Backtest
construction 행의 key로만 쓴다.

## 2.2 Eligibility — scope별 계층 (normative)

eligibility는 단일 게이트가 아니라 **포함 계층**으로 정의한다:

\[
P_{\text{attempt}} \;\supseteq\; P_{\text{evaluated}}
\;\supseteq\; P_{\text{behavior}} \;\supseteq\; P_{\text{quality}}
\]

- \(P_{\text{attempt}}\): 모든 candidate proposal (dedup 전 시도 전체).
- \(P_{\text{evaluated}}\): 실제 unique evaluation을 시도한 후보 —
  **평가 실패도 포함**.
- \(P_{\text{behavior}}\): signal 평가 성공 + core 4종 **전부 finite**.
  partial-finite alpha는 `n_partial_descriptor` 진단으로 집계하고
  diagnostic 분석에만 사용 — 침묵 drop 금지.
- \(P_{\text{quality}}\): behavior eligible + (해당 split의) quality
  finite. quality 결측 alpha는 behavior-only 지표(coverage/entropy)에
  포함하고 quality overlay(HQ 등)에서 제외하며 `n_quality_missing`으로
  집계.

**scope별 적용**:

| scope | 규칙 |
|---|---|
| Final-Pool QD | **Validity Gate pass 필수** (validity_gate_design.md 소관) + 제출 pool의 dedup된 factor 전원 |
| Search-QD budget (§7.3) | \(P_{\text{evaluated}}\) — **invalid/failure도 소비한 search budget으로 계수** (탐색 효율 분석의 왜곡 방지) |
| Search-QD behavioral metrics | \(P_{\text{behavior}}\) |
| Search-QD quality/HQ metrics | \(P_{\text{quality}}\) |
| valid-only Search-QD | supplementary view (병기) |

Implementation status: **Proposed** — 현행은 PCA 비유한 행을
`projected=False`로 표시하고 세대별 `valid_candidate_rate`를
산출하는(trajectory.py:66-76) 수준으로, 위 계층의 관행적 선례이나
core-4 completeness와 계층 명문화는 신규.

## 2.3 Identity contract

`submission_id`(D1), `factor_set_id`(D2), `pool_id`(D3),
`evaluation_context_id`(D5), `report_window_id`(D6), 그리고
`formula_id`·`evaluation_key`·`proposal_event_id`는 **ASB 공통 identity
계약의 소비자**로만 사용한다 — 모델은 **`ASB_design_v2.md` §3.1**,
**exact payload·enum·golden vector는 부록 A**가 정본이며 본 문서는
재정의하지 않는다.

**QD가 소비하는 dimension**:

| 용도 | identity |
|---|---|
| Final-Pool 행 | D1 × D5 × split × D6 × `factor_set_id` × `formula_id` |
| grid summary | 위 + `grid_id` × `qd_metric_id` |
| Search-QD budget | `proposal_event_id` / `evaluation_key` (§7.3) |
| rarefaction | `analysis_frame_id` / `draw_id` (§6.6) |

본 문서가 추가하는 identity 필드:

- `descriptor_protocol_version` — QD_Descriptors_v2의 protocol version.
- `qd_protocol_version` — 본 문서가 규정하는 집계 프로토콜 version.
- `grid_reference_id` — grid의 provenance 해시 (**normative**).
  직렬화는 ASB 공통 identity 계약과 동일하게 **RFC 8785 JCS** 를
  사용한다:

**exact payload는 `ASB_design_v2.md` 부록 A.8a가 정본**이며 본 문서는
재정의하지 않는다. QD가 알아야 할 요지:

  - **정렬된 `formula_id` 집합 포함**: 같은 `"official_reference"` 이름
    아래 constituent가 달라지는 것을 구조적으로 차단.
  - **`evaluation_context_id` 포함**: 동일 formula 집합도 market/평가
    기간이 다르면 descriptor 분포가 달라지므로.
  - **산출된 edge vector 포함**: id가 입력뿐 아니라 결과에 대한
    **검증 가능한 commitment**가 되도록 (frozen edge 해시 대조 — §10.2).

Implementation status: **Not implemented** (현행 manifest는
`reference_split`·`reference_runs`·`reference_basis`만 기록 —
ASB_design.md §8.4 [v1-hist]).

## 2.4 Split discipline (normative invariant)

\[
\boxed{
\begin{aligned}
&\textbf{VALID}: \text{grid/reference calibration, } \tau_q
\text{ freeze, hyperparameter selection 전용} \\
&\textbf{TEST}: \text{frozen specification으로 최종 평가만 — bin
edge/threshold/scaling 재적합 금지} \\
&\text{TEST에서 specification 선택 금지}
\end{aligned}}
\]

이 invariant는 §4(edges), §5(quality), §7(Search-QD split),
§10.7(gate)에서 구체화된다.

**Report window 규율 (계약 — v2 §3.3.3)**: TEST split 안에 두 보고 구간
(`primary_full` / `strict_untouched`)이 있고 **QD도 두 window를 모두
산출·저장**한다. 단:

* window는 **집계 슬라이스**다 — TEST signal panel과 TEST Validity Gate는
  **1회만** 수행하고, `factor_set_id`는 두 window에서 **동일**하다.
* 두 window는 **동일한 VALID-frozen artifact**(edge·\(\tau_q\)·
  `grid_reference_id`·`quality_reference_id`)를 소비하며 **window별
  재보정을 하지 않는다**.
* **window-local gate 재수행·factor selection 금지.**
  **예외 (명시)**: rarefaction의 `analysis_frame_id`는 **window를 포함**한다
  (§6.6) — behavior-eligible 집합이 window별 descriptor에서 결정되기
  때문이다. 이는 "window마다 factor를 골라 성능을 낫게 만드는" selection이
  아니라 **matched 비교를 위한 frame 정의**이며, 그래서 **window 간
  rarefaction 곡선 직접 비교가 금지**된다. base Final-Pool의 구성원
  (`factor_set_id`)과 gate 결과는 window와 무관하게 동일하다.
* **primary 분석은 Primary Full만**이다. Strict는 **사전등록된
  supplementary matched robustness panel**(evidence class는
  `ASB_design_v2.md` §3.8.1의 audit 결과를 따르며 **C-0에서는
  `protocol_held_out`** — "temporal"이라는 형용사를 붙이지 않는다)이며,
  **6 pairwise grids × Strict는 추가 co-primary가 아니고 primary
  multiplicity에 포함하지 않는다**(co-primary = Full의 6 grids, §6.8).
* window별 `n_days`·`n_valid_days`를 병기한다 — descriptor는 \(E_t\)
  평균이므로 **짧은 window에서 분산이 커진다**(해석 시 필수 caveat).
* window 슬라이싱이 "재평가 없음"으로 성립하려면 daily intermediate가
  저장돼야 한다 → **`qd_daily_descriptor_intermediates`**(§9.2a,
  Final-Pool 한정).

**Validity gate의 split 귀속 (계약 — v2 §3.5.2)**: validity는
split-local로 판정되므로 QD가 소비하는 gate도 단계별로 갈린다 —

| QD 단계 | 소비하는 gate |
|---|---|
| VALID reference population·edge·\(\tau_q\) calibration | **VALID** validity |
| TEST Final-Pool QD 평가 | **TEST** validity |
| Search-QD (primary = VALID, §7.2) | **VALID** validity |

TEST gate를 VALID calibration에 재사용하면 reference·\(\tau_q\)가 TEST
구간의 computability에 의존하게 되고(성능 기반 선택은 아니지만
TEST-dependent population selection이다), 반대로 VALID gate만 쓰면 TEST에서
계산 불가한 factor가 Final-Pool에 들어온다. 두 모집단의 차이는
`n_gate_only_valid`/`n_gate_only_test`/`n_gate_both`로 보고한다.

Implementation status: 하위 항목별로 분리한다(단일 절에 "부분"이라는
어휘를 쓰지 않는다 — §1의 3값 규율).

| 하위 계약 | 상태 |
|---|---|
| PCA fit이 valid-only (projection.py:4-5) | **Implemented** (tag: legacy) |
| search-QD 좌표의 test PCA 폴백 제거 (runner.py:414-415) | **Proposed** (§10.6 결함 1) |
| VALID/TEST split discipline의 코드 수준 강제 | **Not implemented** |
| report window가 재보정 없이 동일 artifact를 소비 (§2.4) | **Not implemented** |

---

# 3. Frozen Behavioral Space Construction

## 3.1 Behavioral Core source

\[
b(\alpha) = [\, B,\ T_{common},\ A_L^Q,\ A_V^Q \,]
\]

정의·파라미터·tie/endpoint 규약·intermediate 의무는 전부
**QD_Descriptors_v2.md §11 (Frozen 2026-08-20)** 를 따른다. 본 문서
어디에서도 이를 재정의하지 않으며, 모든 method(GP/RL/LLM)에 동일
contract를 적용한다.

## 3.2 Coordinate policy

- **PCA/latent projection을 primary behavioral space로 사용하지
  않는다.** raw interpretable 4축을 유지한다.
- method별·run별 normalization 금지 — 좌표는 method-neutral이어야 한다.
- test-based scaling 금지 (§2.4).

Implementation status: **Proposed** — 현행 파이프라인은
StandardScaler+PCA(2) 좌표(projection.py, runner.py:287-291)이며,
PCA 경로는 **legacy로 분리**하고 raw 4축 경로를 신설해야 한다 (§10.6).

## 3.3 Completeness

§2.2의 core-4 finite 규칙. partial descriptor alpha의 수와 사유
(`no_spread_signal`, degenerate 등 — QD_Descriptors_v2의 reason 체계)를
per-run 진단으로 보고한다.

## 3.4 Correlation policy

네 축은 **distinct but potentially correlated behavioral dimensions**
(QD_Descriptors_v2 §10 — L–V의 volume-family 실질 상관 실측). 따라서
4×4 Pearson/Spearman, effective-rank/condition 진단은 **redundancy
diagnostic**으로 상시 산출하되 **축 삭제·가중의 기준으로 사용하지
않는다**. orthogonality를 전제하는 서술 금지.

---

# 4. Reference Distribution, Binning & Grid Protocol

## 4.1 Reference population

**temporal calibration window**와 **reference alpha population**은
별개 개념이며 반드시 구분해 명시한다:

- temporal window: VALID split (C-0 확정 창의 validation 구간).
- reference population: edge calibration에 쓰는 alpha 집합 — 구성
  방식(어떤 run들의 어떤 scope), method-neutral 여부(pooled reference
  또는 fixed benchmark population), **dedup/weighting rule과 최소
  reference 표본 수**를 **사전등록**하고, §2.3의 `grid_reference_id`로
  해시 고정한다. **모든 method에 동일 edge를 적용한다.**
  **확정 (2026-08-21)**: `reference_population_policy = fixed_external`.
  비교 대상 method의 산출물을 합친 `pooled_benchmark`는 **primary에서 사용
  금지**다. corpus는 비교 대상과 독립된 **고정 formula 목록**으로 구성하고
  **VALID calibration 개시 전에** `reference_preimage_artifact` + content
  hash를 고정한다. 최소 표본 수를 충족하지 못하면 **pooled reference로 자동
  fallback하지 않고 calibration failure로 기록**한다.
  (corpus 구성·최소 표본 수의 **값**: Deferred — v2 §13.1.)

Implementation status: **Not implemented** — 현행은 run별로 자체
valid-PC 분포에서 bounds를 만들므로(±5% margin,
grid.py `from_reference`) method·seed 간 절대값 비교가 불가하다는
한계가 이미 문서화돼 있다(ASB_design.md §8.4 [v1-hist] "비교 가능성의 한계").
본 사양은 이를 공유 reference로 교체한다.

## 4.2 Edge calibration (frozen rule)

각 축 \(j\)에 대해 VALID reference distribution의 **robust range**를
freeze한다:

\[
[l_j, u_j] = [\, q_{0.01}(b_j^{ref}),\ q_{0.99}(b_j^{ref}) \,]
\qquad \rightarrow \qquad K_j\ \text{equal-width bins}
\]

- **quantile method freeze**: \(q_{0.01}/q_{0.99}\)는 linear
  interpolation(`np.quantile(..., method="linear")`) — A^Q leg 규약
  (QD_Descriptors_v2 §6.3)과 동일한 method 고정 규율.
- **bin boundary 규약**: bin \(k\)는 \([e_k, e_{k+1})\), 마지막 bin만
  \([e_{K-1}, u_j]\) (닫힘) — 현행 `assign`의
  searchsorted(side="right") + 내부 clip 동작과 일치(grid.py:60-63).
- pure quantile binning을 쓰지 않는 이유: reference population을
  강제로 uniform하게 만들어 분포 형상 정보를 지운다.
- **Coverage denominator 규약 (normative)**:

\[
\text{Coverage} = \frac{N_{\text{occupied, in-range}}}{K_x \cdot K_y}
\]

  under/overflow alpha는 coverage cell에 포함하지 않고(가상 추가
  niche로 만들지 않음) `overflow_ratio`로 별도 기록한다. **clipping
  금지.**
- **Range 붕괴 edge case**: \(u_j - l_j < \epsilon\)이면 임의의
  \([0,1]\) fallback을 쓰지 않고 **grid calibration failure + reason**
  으로 처리한다 (§10.2). \(\epsilon\): **Deferred parameter**.
- \(K_j\): **Deferred parameter** — 공식 VALID calibration 후 사용자
  gate에서 freeze. scope별(Final-Pool/Search-QD) 분리 가능 (§4.5).

Implementation status: 하위 항목 분리 — ① in-bounds 집계 +
`overflow_ratio` + no-clipping **골격은 Implemented**, ② raw 축 + 공유
robust-range edge + `grid_id`/`grid_reference_id`는 **Proposed**,
③ range 붕괴 시 calibration failure 처리는 **Not implemented**. 근거:
현행 `QDGrid`가 정확히
"in-bounds만 집계 + overflow_ratio + no-clipping" 철학이며
(grid.py:1-100: `assign`의 bin=-1 처리, `pool_metrics`의
`coverage = n_occ/n_total_bins`), 단 좌표가 PCA·bounds가 run별이므로
raw 축 + 공유 robust-range edge로의 교체는 **Proposed**.

## 4.3 Pairwise grids — 6개 전부

4축의 canonical pair는 정확히 \(\binom{4}{2} = 6\)개다:

\(B{\times}T,\ B{\times}A_L,\ B{\times}A_V,\ T{\times}A_L,\
T{\times}A_V,\ A_L{\times}A_V\)

**6개 전부 산출·보고한다 — cherry-picking 금지.** method-level 요약
규약은 §6.8 (co-primary views).

## 4.4 Full 4D representation

4D 좌표 자체는 보존하되 **Final-Pool에서 4D occupancy grid를
primary로 쓰지 않는다** — 예컨대 \(5^4 = 625\) bins에 pool 10개면
sparse-grid로 coverage가 무의미해진다. 따라서:

- **pairwise 2D discrete QD = primary** visualization/coverage.
- **continuous 4D distance = complementary** diversity diagnostic.

**4D NN normalization (채택 완료)**: 거리 계산은 **raw \([0,1]\)-계열
core 좌표를 normative primary로 사용한다**

\[
d(\alpha,\beta) = \Big(\sum_j \big(b_j^\alpha - b_j^\beta\big)^2\Big)^{1/2}
\]

VALID robust-range rescale \(\tilde b_j = (b_j - l_j)/(u_j - l_j)\)은
**sensitivity/diagnostic 전용**이다. 근거: 네 축이 의도적으로 \([0,1]\)
계열로 설계됐고, primary metric이 reference population에 필요 이상
종속되지 않게 한다. 이 선택의 변경은 **TEST 이전 user gate + qd
protocol version 변경**으로만 가능하다.

Implementation status: NN 계산기는 **Implemented**(grid.py
`nn_distances`, cKDTree)이나 현행 입력이 PCA/standardized 좌표
(pca2d_nn_\*, rawstd_nn_\* — ASB_design.md §8.5 [v1-hist])이므로 raw-좌표 4D
NN은 **Proposed**.

## 4.5 Resolution

Final-Pool과 Search-QD는 표본 크기가 다르므로 \(K_j\)를 scope별로
분리할 수 있다. 단 **각 scope 안에서는 method 간 동일**, VALID에서
사전 freeze, TEST 변경 금지.

---

# 5. Quality Axis & High-Quality Definition

## 5.1 Quality source

quality는 **OOS Test 축의 산출물을 소비**한다 (재계산·재정의 금지).
**quality_metric, quality_horizon, orientation 전부 OOS frozen
contract를 그대로 소비**하며, QD가 horizon을 새로 정하지 않는다:

\[
q(\alpha) = \text{MeanIC}_{h^*}(\alpha),
\qquad h^* = \text{OOS 사전등록 primary horizon}
\ (= \texttt{oos.horizons[0]},\ \text{suffix 없는 컬럼})
\]

- **Primary**: \(\text{MeanIC}_{h^*}\) (사전등록).
- **Secondary**: ICIR — **동일 horizon \(h^*\)**.
- Mean RankIC 등 나머지는 supplementary — primary 판정 번복에 사용
  금지 (oos 문서의 secondary 규율과 동일).

## 5.2 Orientation

behavioral descriptor는 \(\pm S\) 불변이지만 quality는 방향
민감하다. **OOS Test의 orientation contract(train-side sign, 정확히
1회 적용)를 그대로 소비**하며 본 문서에서 재정의하지 않는다. signed
IC를 쓰고, \(|IC|\)로의 임의 변환은 금지한다.

## 5.3 HQ threshold — \(\tau_q\)

\[
\tau_q = f\big(Q_{VALID}\big)\ \text{(사전등록 rule로 VALID에서 freeze)}
\qquad\Rightarrow\qquad
HQ_{TEST}(\alpha) = \mathbb{1}\big[\, q_{TEST}(\alpha) \ge \tau_q \,\big]
\]

- \(\tau_q\): **Deferred parameter** — VALID quality distribution 기반
  사전등록 rule(또는 사전등록된 절대 임계)로 freeze. **TEST에서 산출
  금지.**
- **공통 threshold 원칙 (normative)**: \(\tau_q\)는 **모든 비교
  method에 공통인 single frozen threshold**다 — method별 quantile
  threshold(예: 각자의 80퍼센타일)를 쓰면 HQ Coverage가 method 간
  비교 불능이 된다.
- **확정 (2026-08-21)**: `threshold_rule = {kind: quantile, q: 0.80,
  method: linear}`. 공통 **fixed-external** reference의 VALID quality
  분포에서 \(\tau_q\)를 실현하고 **모든 method에 동일 값**을 적용한다.
  method별 quantile과 TEST 재산출은 금지. **absolute threshold는 primary가
  아니라** 사전등록된 supplementary sensitivity가 필요한 경우에만 **별도
  ID**로 추가한다.
- quantile 기반 rule일 때는 **`quality_reference_id`** 를 둔다
  (§2.3의 `grid_reference_id`와 대칭). **exact payload는
  `ASB_design_v2.md` 부록 A.8a가 정본**이며 본 문서는 재정의하지 않는다.
  정책 요지만 남긴다: ① reference population 구성·dedup·weighting rule과
  **실현된 \(\tau_q\) 값**이 함께 commitment되어야 한다(rule만 담으면 같은
  ID가 서로 다른 \(\tau_q\)를 가리킨다 — `grid_reference_id`가 산출된 edge
  vector를 포함하는 것과 대칭), ② **사전등록된 절대 threshold를 쓰는
  경우에는 reference population이 불필요**하므로 관련 필드를 생략한다.
- **reference population 정책 2종 (배타 — 하나를 사전등록한다)**:

  | 정책 | 정의 | method-neutral |
  |---|---|---|
  | **fixed external reference** | 비교 대상 method와 무관한 고정 population(예: Alpha101 static reference, 이전 프로토콜 버전의 동결 집합) | **예** — 권장 |
  | **pooled benchmark reference** | 비교 대상 method들의 후보를 섞어 만든 population | **아니다** |

  pooled reference는 한 method의 품질이 전체 \(\tau_q\)를 밀어 올리는
  결합을 만들므로 **method-neutral이 아니다** — "method-neutral이어야
  한다"고 요구하면서 pooled를 허용하면 자기모순이다. pooled를 택하면
  **method-neutrality를 주장하지 않고** 결합 방향과 영향 범위를 사전등록에
  명시하며, \(\tau_q\) 기반 비교를 **supplementary로 강등**한다.
- **복수 임계 (multi-threshold HQ)**: 더 엄격한 수준의
  quality-conditioned diversity가 필요하면 **별도 메커니즘을 만들지
  않고** 사전등록된 임계 집합 \(\{\tau_q, \tau_q', \dots\}\)를 VALID
  에서 함께 freeze하여 동일한 HQ 기계장치를 각 임계에서 평가한다
  (§6.4). 모든 임계는 위 공통성·`quality_reference_id` 규약을 따른다.
- threshold 미설정 상태에서 HQ 지표를 **0.0으로 기록하는 현행 동작은
  결함**이다 — 미설정이면 HQ 지표는 NaN + `hq_not_configured` 사유여야
  한다.

Implementation status: 세 층위를 구분한다 — ① hq 필터 자체는
**Implemented**(grid.py `hq_filter` — threshold None → 전부 False),
② runner가 이를 `hq_coverage=0.0`으로 기록하는 동작을 NaN +
`hq_not_configured`로 **교정**하는 것은 **Proposed**(기제는 있고 동작만
바꾼다), ③ VALID 분포에서 \(\tau_q\)를 **산출·freeze하는 경로와
`quality_reference_id`** 는 **Not implemented**(대응 구현 전무).
§10.8의 행 배치는 이 3분할을 따른다.

## 5.4 Cell-level quality

각 niche에 저장: `n_alpha`, `share`, `mean_quality`, `median_quality`,
`best_quality`, `HQ_count`, `HQ_share`, **`n_quality_eligible`**.

**결측 규약 (normative)**: 셀 내 quality-eligible alpha가 0개면
(`n_quality_eligible = 0`) `mean/median/best_quality`와 `HQ_share`는
**NaN + reason(`no_quality_eligible_in_cell`)** 이며 0으로 채우지
않는다. `HQ_count`는 0(정수 카운트)이되 share/평균 통계는 NaN이다.
eligible ≥ 1이고 임계 이상이 0개면 `HQ_count = 0`,
`HQ_share = 0.0`이 올바른 값이다 (§6.3과 동일 구분).

**quality 합계 \(\sum q\)는 primary로 사용하지 않는다** — count와
quality가 한 숫자에 섞인다. (QD-score의 지위는 §6.7.)

## 5.5 VALID/TEST 소비 invariant (반복 선언)

- **VALID**: quality metric 선정, \(\tau_q\) freeze, (있다면) quality
  normalization freeze.
- **TEST**: frozen metric과 \(\tau_q\) **적용만** — cell quality 산출,
  HQ 여부 산출. recalibration 일절 금지.

---

# 6. Final-Pool QD Metrics & Method-Level Comparison

## 6.1 Occupancy / Pairwise Coverage

각 pairwise grid \(g\)에서 §4.2의 분모 규약으로:

\[
\text{Coverage}_g = \frac{\#\{\text{occupied in-range cells}\}}
{K_x K_y}
\]

under/overflow 점은 **numerator에 기여하지 않으며**, 분모는 항상
고정 bin 수 \(K_x K_y\)다 (점 수가 아니다). `overflow_ratio_g`
(§6.2의 분모 규약) 병기.

## 6.2 Behavioral Evenness / Entropy

**분모 규약 (normative)** — 확률은 in-range 점 기준으로 정의한다:

\[
N_{in} = \sum_{c \in \text{grid}} n_c, \qquad
p_c = \frac{n_c}{N_{in}}
\]

\[
H_g = -\sum_c p_c \log p_c, \qquad
H_g^{norm} = \frac{H_g}{\log(K_x K_y)}, \qquad
\text{evenness} = \frac{H_g}{\log n_{occ}}
\]

- `overflow_ratio` 분모도 freeze:
  \(\text{overflow\_ratio} = N_{out} / N_{\text{behavior eligible}}\)
  (해당 scope에 투입된 \(P_{behavior}\) 기준 — §2.2).
- cell share 2종 구분: `share_inrange` \(= n_c/N_{in}\) (기본),
  필요 시 `share_all` \(= n_c/N_{\text{behavior eligible}}\) 병기.
- **Edge case 규약**:
  - \(N_{in} = 0\) → entropy/evenness **NaN + reason**
    (`no_inrange_points`).
  - \(n_{occ} = 1\) → \(H = 0\)이지만 \(H/\log n_{occ}\)는 0/0 —
    evenness는 **NaN + reason** (`single_occupied_cell`). ⚠ 현행
    구현은 이 경우 1.0으로 정의(grid.py:99)하므로 이 항목은 현행과
    **다른 Proposed** 규약이다 ("trivially even" 오독 차단).
  - 4D NN: eligible \(N < 2\) → **NaN + `insufficient_points`**
    (현행 `nn_distances`가 이미 동일 동작 — Implemented).

concentration 진단: `max_cell_share`, `top_k_cell_share`
(share_inrange 기준).

Implementation status: 산식·\(N_{in}=0\) NaN·NN 규약 **Implemented**
(grid.py `pool_metrics`/`nn_distances`), 분모 명문화·share 2종·
evenness NaN 규약·max/top-k share는 **Proposed**.

## 6.3 HQ Coverage

\[
\text{HQCoverage}_g = \frac{\#\{c : \exists\, \alpha \in c,\
q(\alpha) \ge \tau_q\}}{K_x K_y}
\]

연구 질문("고품질 alpha를 behavioral space 여러 곳에서 찾았는가")의
직접 지표. §5.3의 결함 수정을 전제한다.

**Undefined 규약 (normative)**: 해당 scope에 quality-eligible alpha가
**0개면**(\(|P_{quality}| = 0\), §2.2) HQCoverage는 **NaN + reason
(`no_quality_eligible_points`)** 다 — 0.0으로 기록하지 않는다.
"평가했으나 HQ가 하나도 없음"(→ 0.0이 올바른 값)과 "quality를 아예
평가할 수 없음"(→ NaN)을 혼동해서는 안 된다. eligible ≥ 1이고 임계
이상이 0개인 경우에만 0.0이다. \(\tau_q\) 미설정 시에는 §5.3에 따라
NaN + `hq_not_configured`.

## 6.4 Quality-conditioned diversity — multi-threshold HQ (선택)

더 엄격한 품질 수준에서의 diversity는 **별도 메커니즘 없이 §6.3의 HQ
기계장치를 사전등록된 복수 임계에서 평가**한다:

\[
\text{HQCoverage}_g(\tau) ,\qquad
\tau \in \{\tau_q,\ \tau_q',\ \dots\}\ \text{(전부 VALID freeze)}
\]

- **"pool 내 quality 상위 x%" 같은 상대 컷은 사용하지 않는다** — 두
  가지 이유로 금지된다: ① TEST 관측 분포에서 컷을 잡으면 §5.5의
  "TEST에서 threshold 산출 금지"를 위반하고, ② pool 내 상대 컷은
  method별로 실질 임계가 달라져 §5.3이 이미 금지한 "method별 quantile
  threshold"와 동일한 비교 불가능성을 재도입한다.
- 상대 x% 개념을 쓰려면 VALID reference 분포에서
  \(\tau_x = Q_{1-x}(Q_{VALID,ref})\)로 **freeze한 절대값**으로
  변환해 위 임계 집합에 넣는다 (§5.3의 `quality_reference_id` 규약
  공유).
- entropy 등 다른 지표를 HQ subset에서 산출할 때도 §6.2의 edge case
  규약(N_in=0, n_occ=1)과 §6.3의 undefined 규약을 그대로 적용한다.

## 6.5 Continuous 4D diversity

frozen raw 좌표(§4.4)에서 mean/median/min NN distance와 pairwise
distance 분포.

## 6.6 Pool-size correction

pool 크기가 method별로 다르면 **rarefaction(고정 n, R회 비복원,
고정 seed) 또는 fixed-n subsampling이 필수**다.

**Estimand 2종과 `k`의 의미 (계약 — v2 §7.3)**: **selected-k estimand**를
채택한다.

| estimand | analysis frame | 지위 |
|---|---|---|
| **Q4 matched** (`q4_matched`) | `TEST gate-pass ∩ QD behavior-eligible` | **Q4 primary estimand — 확정**(`ASB_design_v2.md` §3.7: `q4_estimand_status = selected_k`) |
| **Deployment sensitivity** | `gate-pass factor set` | 배포 관점 민감도. matched 비교용 아님 |

**확정 사항 (2026-08-21 — 정본은 v2 §3.7·§7.3)**:
`selection_mechanism = random_without_replacement`(무작위 부분집합 —
quality top-k 아님) · \(k^*\) = `min_{u∈U_primary} n_behavior_eligible^VALID(u)`
(**U_primary = registry의 planned slot 전원** — 성공 unit 목록이 아니다.
count 관측 후 제외 금지이며 **등재 조건에 실행 결과를 넣는 것도 같은
위반**이다. 모든 slot이 `resolved_unit`이 아니면 Q4 primary는
**`q4_primary_not_evaluable_incomplete_registry`**이고 성공 unit만 쓴 분석은
supplementary로만 보고한다 — 정본 v2 §7.3) · common support 하한 \(k_{\min,Q4} = 2\max(K_B,K_T)\) 미달 시
`not_evaluable_common_support` · TEST shortfall은 **k 축소 없이** NaN +
`insufficient_behavior_eligible_for_k` · \(R\)은 nested MCSE 기준
(`R_candidates = [50,100,200,500,1000]`, coverage
`MCSE ≤ max(0.05·SD, 0.005)`, median_sharpe `MCSE ≤ max(0.05·SD, 0.05)`,
1000까지 실패 시 `rarefaction_mc_not_converged`).
**Q4 confirmatory에는 \(k^*\) 하나만** 쓰고 curve의 k-grid는 별도
sensitivity다. R draw는 **evaluation unit 내부에서 먼저 집계**되며 독립
표본·bootstrap unit이 아니다.

`n_selected = k`이며 **`n_quality_eligible`·`n_active`는 축·구성별로 다를
수 있다**(허용) — HQ Coverage 같은 quality-conditioned metric에서
`quality_eligible < k`, `train_signed_equal`에서 `active < k`가 정상적으로
발생한다. 따라서 이를 **active-k 비교로 주장하지 않는다**. 병기 의무:
`n_selected`·`n_gate_pass`·`n_behavior_eligible`·`n_quality_eligible`·
`n_active`. pre-gate draw를 함께 보고하려면 결과명을 **`@k_sampled`** 로
구분한다.

**공통 draw 규약**: \(k\) 격자·\(R\)·`draw_seed`는 공통
`pool_rarefaction` namespace에서 freeze하고 **QD와 Backtest가 동일
`draw_id`의 selected membership을 소비**한다(payload는 v2 부록 A.8).
**`analysis_frame_id`의 `eligibility_protocol_versions`는
`{validity, behavior}` 2종으로 고정**되며(Q4 matched frame) **quality
version·\(\tau_q\)는 제외**된다 — random membership을 결정하지 않으므로
그 commitment는 `qd_metric_id`·`quality_reference_id` 소관이다.
`replicate_index`는 seed에 섞지 않고 `draw_id`의 별도 필드로 두며,
`draw_seed`는 v2 부록 A.8b의 파생 규칙(PCG64 · low53)을 따른다.
`analysis_frame_id`가 eligibility 단계·window·protocol version을 담으므로,
**matched frame이 window 의존**이라 Full과 Strict는 서로 다른 draw를 갖는다
→ 각 window 내부에서만 matched이며 **window 간 rarefaction 곡선 직접 비교는
금지**한다. behavior-eligible < k이면 해당 지표는 NaN + reason이다.

**Normative rule**: Coverage만이 아니라 **같은 fixed-n subsample
draw에서 모든 primary QD metric(Coverage/Entropy/HQ Coverage/
max·top-k share/NN)을 재계산**한다 — 모두 **sample-size
dependent**이기 때문이다.

**단조성에 대한 정확한 서술**: 표본 크기 증가에 따른 단조성은
**Coverage와 HQ Coverage에만** 성립한다(nested 표본에서 점유 셀 수가
감소할 수 없으므로 기대값이 단조 비감소). **Entropy/evenness·NN
거리·max-cell share는 단조성이 보장되지 않는다** — 반례: pool
\(\{A{:}50, B{:}1\}\)에서 \(n{=}2\) 표본 \(\{A,B\}\)의 \(H = 0.693\)
이지만 전량 \(n{=}51\)에서는 \(H = 0.097\)로 감소하고, pool
\(\{0.0, 0.1, 5.0\}\)의 평균 NN은 \(n{=}2\)에서 0.100, \(n{=}3\)에서
1.700으로 증가한다. 따라서 이들에 단조성 sanity check를 걸어서는
안 된다 (§10.5).

Implementation status: Coverage rarefaction은 **Implemented**
(grid.py `rarefaction_coverage` — fixed seed, 비복원,
E[coverage@n]+std); **동일 draw에서 나머지 지표 rarefy·run별 수행 →
method 집계 계층(§6.8)은 Proposed**.

## 6.7 QD-score의 지위 (검토 후 배치)

MAP-Elites 문헌의 표준 지표 \(\text{QDScore} = \sum_{c \in occupied}
q_c^{elite}\)를 **검토하였으나 primary로 채택하지 않는다.** 사유:

1. ASB quality(IC/ICIR)는 **음수 가능** — niche를 하나 더 발견했는데
   elite quality가 음수면 QD-score가 감소하는 역설.
2. quality의 zero-point/scale에 결과가 민감.
3. coverage와 quality가 한 숫자에 섞여 분해 불가 — ASB primary는
   분해 가능한 {Coverage, Entropy, HQ Coverage, cell-level quality}를
   유지한다.

supplementary로 사용하려면 **VALID에서 freeze한 quality
transformation**(예: 음수 처리 규칙)을 함께 사전등록해야 한다. 이
단락은 "빼먹은 것"이 아니라 명시적 검토·배치의 기록이다.

## 6.8 Method-level 판독 규약 (사전등록)

집계 계층 (normative):

\[
\text{alpha} \;\rightarrow\; \text{run/seed metric}
\;\rightarrow\; \text{method summary}
\]

- **method 전체에서 alpha를 먼저 pooling한 뒤 metric을 계산하는 것을
  금지한다** — run/seed별로 QD metric을 계산한 후 집계한다.
- method central estimate = **median across runs**, dispersion =
  **IQR**, CI = **bootstrap CI**. **bootstrap resampling unit =
  run/seed** — alpha나 rarefaction draw를 resample하지 않는다(run 내
  상관 무시로 CI 과소 추정). **확정 (2026-08-21)**: `confidence_level = 0.95`, `B_boot = 10000`,
  `bootstrap_method = percentile`. resampling unit은 **evaluation unit**
  (`D1 × D5 × D6 × factor_set_id`)이다 — `primary_full`과
  `strict_untouched`를 한 bootstrap sample에서 독립 관측처럼 합치지 않으며,
  **rarefaction draw와 deployment cell도 resampling unit이 아니다**.
  `bootstrap_seed`는 v2 부록 A.8b의 파생 규칙을 따른다.
- **paired statistic은 실험이 진짜 paired design일 때만** 사용한다 —
  GP seed 42와 LLM seed 42가 같은 random realization을 공유하지
  않으므로 seed 번호 일치는 pairing 근거가 아니다.
- rarefaction은 **run별로 수행한 뒤** method 수준에서 집계한다.
- **6 pairwise grids = co-primary views**: grid별 Coverage/Entropy/
  HQCoverage를 전부 보고한다. `mean_pairwise_coverage` 등 equal-weight
  평균은 **summary diagnostic 전용**이며 단일 composite를 primary로
  만들지 않는다 — 평균 하나가 서로 다른 behavioral relation을 다시
  숨기는 것을 차단한다.

Implementation status: **Not implemented** — 현행 파이프라인은 run
단위 산출까지만 존재.

---

# 7. Search-QD & Exploration Trajectory

## 7.1 Search population과 dedup

- 대상: trajectory의 all-candidates 중 **unique formula** (§2.2
  계층 적용 — budget은 \(P_{evaluated}\), behavioral은
  \(P_{behavior}\); valid-only 뷰는 supplementary 병기).
- **\(B_{unique}\)는 "cache misses"가 아니다** — 정본은 **mining run-local
  logical first-seen**(아래 계수 계약). 물리적 global cache miss로 정의하면
  다른 method가 먼저 캐시를 채웠다는 이유로 후속 method의 budget이 줄어
  평가 순서에 결과가 의존한다.
- **Dedup key 계약**: primary dedup key는 **ASB 공통 identity 계약의
  `formula_id`(canonical formula 기준 exact identity)** 이고, raw
  submitted string은 provenance로 보존한다 — 공백·표기 차이만 다른
  동일 canonical formula를 별개 후보로 세는 것을 차단하며, §7.7의
  cache identity(formula_id 기반)와 정합한다. **의존성 명시**:
  canonical `formula_id`는 공통 identity 계약에서 Proposed 상태
  (canonical renderer 필요 — `ASB_design_v2.md` §3.1.3)이므로, 그 구현
  전까지는 현행 **문자열 exact dedup을 근사로 병기**한다.
- ⚠ 현행 `qd.dedup != "exact"` 경로(runner.py:196-197)는 descriptor 행
  중복 → 병합 N×N, `n_factors_dropped` 음수를 낳는 기지 결함이다
  (ASB_design.md:706 [v1-hist]) — 비-exact(=dedup 해제) 경로는 제거 또는
  차단한다 (§10.6).

## 7.2 Split 규율 (normative)

- **Primary Search-QD trajectory와 method 비교는 VALID에서
  계산한다.** all-candidates 수천 개에 TEST quality를 계산하는 것은
  holdout을 후보 전체에 펼치는 것이며 이후 분석 선택 여지를 크게
  늘린다.
- TEST의 primary는 **frozen Final-Pool QD one-shot**이다 (§6).
- TEST all-candidate trajectory를 쓰려면 **사전 명시된 supplementary
  one-shot analysis로만** 허용한다.
- behavioral descriptor는 label-free지만 이 규율은 quality까지 포함한
  Search-QD 전체에 적용한다.
- **해석 한계 (필수 병기)**: Search-QD의 quality는 VALID에서
  계산되고 \(\tau_q\)도 VALID에서 freeze되므로(§5.3),
  \(\text{HQCoverage}(b)\) 등 Search-QD의 quality-conditioned 지표는
  **method 간 상대 비교**로만 읽어야 하며 **일반화(generalization)
  증거로 인용하지 않는다** — 일반화 판독은 TEST의 frozen Final-Pool
  QD 소관이다. quality reference가 pooled일 때의 method 간 결합은
  §5.3의 method-neutral 요구를 따른다.

Implementation status: **Proposed** — 현행 search-QD는 좌표에 valid
PCA를 쓰지만 split 규율이 명문화·강제되어 있지 않다.

## 7.3 Budget axis — 이원화 (normative)

\[
B_{\text{unique}} = \#\{\text{mining run 내 처음 관측된 distinct }
\texttt{evaluation\_key}\} \qquad (\textbf{primary budget axis})
\]

\[
B_{\text{attempt}} = \#\{\text{distinct } \texttt{proposal\_event\_id}\}
\qquad (\text{efficiency diagnostic})
\]

- **\(B_{unique}\)는 평가의 성공 여부와 무관하다** — 그 mining run에서
  **처음 관측된 `evaluation_key`**라면 평가가 실패해도 1을 소비한다. 실패
  formula를 다산하는 method에 budget을 공짜로 주지 않는다. (물리적 cache
  miss가 아니라 **run-local logical first-seen**이다 — 아래 계수 계약.)
- **계수 계약 (exact — v2 §3.1.2·§7.4)**: proposal 사건과 evaluation dedup
  단위를 분리한다.

```
B_attempt = distinct proposal_event_id 수
B_unique  = 동일 (mining_run_id × evaluation_context_id × split) 안에서
            **처음 관측된** distinct evaluation_key 수
evaluation_key = formula_id (canonicalize 성공) | raw_failure_key (실패)
필드: retry_of (retry 연결) · cache_hit (실측 진단 — 계수 정의에 미사용)
출력: proposal_ledger (PK = proposal_event_id)
```

  **\(B_{unique}\)는 물리적 global cache miss가 아니라 method/run-local
  logical first-seen이다** — 다른 method가 먼저 캐시를 채웠다는 이유로 후속
  method의 budget이 줄면 **평가 순서 의존성**이 생겨 method 비교가 실행
  순서에 좌우된다.

  구분 결과: syntax alias(`A+B` vs `Add(A,B)`) → 같은 `formula_id` →
  \(B_{unique}\) 1 / operational retry → `retry_of`로 1 / 서로 다른 탐색
  사건의 재제안 → proposal event 2, \(B_{unique}\) 1 / 교차 method 동일
  raw → `mining_run_id`가 계수 범위이므로 분리 / DSL version 상이 →
  `formula_id` 상이로 분리. canonicalize 실패도 1을 소비하며
  `raw_failure_key`가 서로 다른 실패를 분리하고 retry를 접는다.
- duplicate가 memo hit이면 실제 평가 비용이 없으므로 둘은 다르다.
  **trajectory의 x축은 \(B_{unique}\)** — generation 개념이 없는
  method(LLM 라운드 등)도 동일 축에서 비교된다.
- \(B_{attempt}\)·memo-hit ratio와 **yield 진단 5종**
  (`n_eval_success`, `n_eval_failure`, `valid_yield`,
  `behavior_eligible_yield`, `quality_eligible_yield` — §2.2 계층별
  통과율)은 **search efficiency diagnostic**으로 별도 보고한다 —
  duplicate·실패를 다산하는 method의 비효율을 보존한다.

Implementation status: 재료 **Implemented** — 현행
`search_budget`이 total/unique evaluations·memo_hit_ratio를 이미
산출(trajectory.py:28-42). generation → \(B_{unique}\) 축 전환은
**Proposed**.

## 7.4 Trajectory metrics

budget \(b\)까지: \(\text{Coverage}(b)\), \(\text{Entropy}(b)\),
\(\text{HQCoverage}(b)\), \(\text{BestQuality}(b)\),
\(\text{UniqueBehaviorCells}(b)\).

Implementation status: 하위 항목 분리 — ① 세대별 coverage/entropy/
overflow/new·cumulative bins/centroid displacement/quality 요약은
**Implemented**(trajectory.py:45-107), ② \(B_{unique}\) budget-axis화·
HQCoverage(b)·BestQuality(b)는 **Proposed**, ③ `proposal_ledger`와
run-local first-seen 계수는 **Not implemented**(§7.3).

## 7.5 Rarefaction — Search-QD에서는 supplementary

**Search-QD의 primary budget 비교는 random rarefaction이 아니라
동일 \(B_{unique}\) prefix**다 — 탐색 궤적에는 시간 순서가 있고
random subsample은 그 구조를 파괴한다. random rarefaction
\(QD_m(n)\)(R회, mean/std/CI, fixed seed, run별 수행 → method 집계)은
**sample-size sensitivity supplementary**로만 사용한다.

## 7.6 Transition / exploration 진단 (supplementary)

new-cell discovery rate, revisitation rate, cell transition matrix,
stagnation length, top-cell concentration over time.

Implementation status: new/cumulative bins·centroid displacement는
**Implemented**(trajectory.py), 나머지는 **Not implemented**.

## 7.7 Computation & Cache Contract — Search-QD feasibility (normative)

Search-QD는 후보 수천 개의 descriptor를 요구하므로 이 절은 구현
note가 아니라 **feasibility contract**다.

**계산 구조 (고정)**:

\[
\text{formula} \;\rightarrow\; \text{signal panel 1회 평가}
\;\rightarrow\; \{B,\ T_{common},\ A_L^Q,\ A_V^Q\}
\]

1. characteristic·percentile panel(ILLIQ20/VOL20/PIT percentile)은
   `evaluation_context`별로 **1회만 사전계산**한다.
2. unique formula마다 signal panel을 **1회** 평가하고, 같은 panel에서
   B/T/Spread 전부를 파생한다 — descriptor별 재평가 금지.
3. **dedup key(§7.1 — canonical `formula_id`, 미구현 구간은 문자열
   exact) 기준 중복은 재평가 금지**.
4. generation/round 진행에 따라 **incremental cache**를 사용한다.
5. cache identity는 최소:

\[
\texttt{formula\_id} + \texttt{evaluation\_context\_id} +
\texttt{split} + \texttt{descriptor\_protocol\_version}
\]

**비용 진단 출력 의무**: attempted candidates / unique formulas /
signal evaluations / cache hits / evaluation failures / wall clock /
descriptor compute time.

**Budget cap 규율**: 계산 상한(cap)은 **Deferred parameter** —
experiment runbook에서 method 공통값으로 사전등록한다. **cap 초과 시
일부 후보만 평가한 결과를 정상 Search-QD로 보고하는 것을 금지**한다:
`incomplete`로 표시하거나, 모든 method에 동일한 사전등록 sampling
rule을 적용한다.

Implementation status: **Not implemented** — 현행 all-candidates
경로는 PCA 좌표 조회 기반이라 이 contract가 필요 없었다. core 4종
계산기 신설과 함께 도입한다.

---

# 8. Supplementary QD & Diversity Diagnostics

primary core 밖의 기존 ASB QD 분석을 보존한다. 어느 것도 primary QD
score와 혼합하지 않는다.

## 8.1 Performance-Response

H/V/M/L(조건부 IC 계열)은 behavioral core가 아니라
**Performance-Response supplementary** (분류·정의는
QD_Descriptors_v2 §9).

## 8.2 Structural diagnostics

\(A^\rho\), \(A^W\), \(T_{union}\), RRE_qd, Signal Coverage,
Liquidity/Volatility Footprint, signed spread, persistence, leg
진단 — 전부 QD_Descriptors_v2 §9의 분류·정의를 소비.

## 8.3 DE (Diversity Entropy) — 2종 구분 유지

- `AlphaEval_DE_legacy`: 원조 재현(z-score NaN→0 flatten — 상장 이력
  차이가 DE를 부풀리는 문서화된 한계).
- `de_common_valid`: 공통 유효 셀 재계산(+`n_common_cells`,
  `common_cell_ratio`, `n_factors_used/dropped`, reason).

**DE는 signal-space diversity이며 grid entropy(behavior-space
occupancy)와 다른 지표**임을 명시한다. pairwise DE는 미구현(스펙 —
PSD 문제, diversity.py 헤더).

Implementation status: **Implemented** (diversity.py).

## 8.4 PFS — 3 mode 보존

`legacy_alphaeval` / `paper_literal`(기본) /
`relative_input`(**experimental**) — 각 mode의 정의, deterministic
seed(`sha256(market|split|noise|seed|draw|dataset|mode)`), K draws,
cache, output provenance를 유지한다 (pfs.py:1-102). ⚠ seed 키의
descriptor `seed` 컬럼 병합 충돌은 기지 결함 (§10.6).

Implementation status: **Implemented** (+결함 수정 Proposed).

## 8.5 VALID→TEST Behavioral Drift (신설 supplementary)

**Scope (§7.2와의 정합)**: drift는 **Final-Pool alpha를 대상으로
한다**. behavioral descriptor는 label-free이므로 TEST에서 behavior를
계산하는 것 자체는 leakage가 아니지만, all-candidates로 확장하려면
§7.2의 조건(사전 명시된 supplementary one-shot analysis)을 그대로
적용한다. 이 절은 **behavior 좌표만** 사용하며 TEST quality를
추가로 펼치지 않는다.

각 alpha에 대해 \(\Delta b_j = b_{j,test} - b_{j,valid}\):

- signed drift / absolute drift / descriptor별 method median drift
- valid↔test rank stability
- frozen-bin transition, under/overflow 발생

**원칙: drift가 커도 TEST edge를 재적합하지 않는다.** TEST overflow는
frozen VALID behavior space를 벗어난 **실제 behavioral shift라는
진단값**이지 보정 대상이 아니다.

Implementation status: **층위 구분 필수** — 현행 파이프라인이 저장하는
valid/test 쌍 + `drift_<core>` 컬럼은 **legacy v1 6축 descriptor의
drift**이며(구 `ASB_design.md` §8.3 — historical evidence), §3.2·§10.8에
따라 현행 primary 계산기는 여전히 구 6축/PCA다. 따라서:
**legacy v1 descriptor drift = Implemented (tag: legacy /
non-normative)** / **Core v2 4축 drift = Proposed**(core v2 production
계산기와 함께 신설) / frozen-bin transition·rank stability =
**Proposed**.

## 8.6 관계 분석

descriptor correlation, QD vs DE, QD vs PFS, QD vs OOS quality,
QD vs backtest performance — 전부 diagnostic 계층이며 primary QD
지표와 혼합 금지.

---

# 9. Outputs, Schema, Configuration & Reproducibility

## 9.1 Per-alpha table

identity(§2.3 필드 전부) + core 4값 + QD_Descriptors_v2 §11의
intermediate 의무 항목(signed/persistence/mass_covered/leg 진단/
\(N_t^C\)) + quality metrics(metric·horizon \(h^*\) 명기) + pairwise
grid 좌표(6쌍의 bin index) + under/overflow flags + supplementary
descriptors + validity flags.

**감사용 필수 컬럼 (§2.2·§5·§6 규약의 검증 가능성)**:

- **eligibility 계층 flag**: `is_behavior_eligible`(core 4종 finite),
  `is_quality_eligible`(quality finite) — \(P_{behavior}\)/
  \(P_{quality}\) 소속을 행 단위로 판정 가능하게 한다.
- **reason 컬럼**: descriptor 측(`no_spread_signal` 등 —
  QD_Descriptors_v2의 reason 체계)과 QD 측 undefined 사유
  (`no_inrange_points`, `single_occupied_cell`,
  `no_quality_eligible_points`, `no_quality_eligible_in_cell`,
  `hq_not_configured`, `insufficient_points`)를 값이 NaN인 지표와 함께
  보존한다 — **NaN을 0으로 대체한 흔적이 남지 않아야 한다**.
- HQ 판정 결과는 임계별로 저장한다 (`hq@tau_q`, `hq@tau_q'` — §6.4의
  multi-threshold).

## 9.2 Per-grid / per-method summary

**Logical primary key (계약 — 정본은 `ASB_design_v2.md` §10.2)**:

```
qd_grid_summary  PK = D1 × D5 × split × D6 × qd_protocol_version
                      × factor_set_id × grid_id × qd_metric_id
qd_method_summary PK = D5 × split × D6 × qd_protocol_version
                      × method × grid_id × qd_metric_id
```

`(pair × method × run)`만으로는 context·split·window·factor_set을 식별하지
못한다. **`grid_id`는 공간 geometry**(descriptor pair·axis order·resolution·
frozen edges·`grid_reference_id`)이고 **metric은 `qd_metric_id`** 가 담는다 —
둘을 한 ID에 섞으면 같은 grid geometry를 여러 metric에 재사용할 수 없다
(payload는 v2 부록 A.8).

**한 행 = 한 지표 (long-form 계약)**: `qd_grid_summary`의 PK에
`qd_metric_id`가 있으므로 **Coverage·Entropy/evenness·HQCoverage(임계별)·
max/top-k cell share를 한 행에 함께 담지 않는다** — 지표마다 1행이며 값은
`metric_value` + `metric_reason`(undefined 사유) 컬럼에 들어간다. 행 공통
denominator 진단(`overflow_ratio`, \(N_{in}\),
\(N_{\text{behavior eligible}}\), \(|P_{quality}|\))은 각 행에 반복
기재하거나 grid 단위 companion 행으로 둔다.

**cell 통계와 rarefaction은 별도 테이블이다** — grain이 다르므로 같은 표에
섞지 않는다:

```
qd_cell_metrics            PK = D1 × D5 × split × D6 × qd_protocol_version
                                × factor_set_id × grid_id × cell_index
   컬럼: n_alpha · share_inrange (필요 시 share_all) · n_quality_eligible
qd_cell_quality_metrics    PK = 위 + quality_metric × quality_horizon
                                × quality_reference_id × tau_q
   컬럼: mean/median/best_quality · HQ_count · HQ_share · reason
   ← quality identity를 PK에 넣지 않으면 secondary ICIR·복수 τ가 들어올 때
     같은 PK에 서로 다른 의미의 값이 충돌한다 (§5.4의 multi-threshold)
qd_rarefaction_draws / _metrics   §6.6 · v2 §10.2.3
```

method summary(§6.8)도 별도 테이블이며 동일 long-form 규약을 따른다.

## 9.2a Daily descriptor intermediates (신설 — window 슬라이싱의 전제)

report window가 **집계 슬라이스**로 성립하려면(§2.4) descriptor를 window별로
재평가하지 않고 **저장된 일별 중간값에서 재집계**할 수 있어야 한다.

```
qd_daily_descriptor_intermediates
PK = D1 × D5 × split × descriptor_protocol_version × formula_id × date
컬럼: B_t · T_common_t · A_L^Q_t · A_V^Q_t
      + leg 진단(n_top·n_bot·top_share·bottom_share·n_overlap_removed)
      + N_t^C · degenerate/제외 사유
```

* **window를 PK에 넣지 않는다** — daily는 split당 1회 생성되고 window는 그
  위의 날짜 필터다(v2 §10.2.2).
* **범위 한정 (계약)**: **Final-Pool 대상만**이다. Search-QD는 VALID 단일
  window이므로 저장 의무가 없다 — all-candidates × 전 거래일을 저장하면
  §7.7의 feasibility 계약과 충돌한다.
* 이 테이블이 없으면 Strict window 집계가 "재평가 없음"으로 성립하지
  않는다(§10.4의 acceptance 대상).

Implementation status: **Not implemented**.

## 9.3 Search trajectory table

\(B_{unique}\)(x축), \(B_{attempt}\), generation/round, unique count,
cumulative coverage, HQ coverage, best quality, rarefaction, §7.7
비용 진단.

## 9.4 Manifest (필수 기록)

descriptor_protocol_version / qd_protocol_version / calibration
period / reference population 구성 rule + `grid_reference_id`(해시) /
edge values \([l_j, u_j]\)와 \(K_j\) / range-collapse \(\epsilon\) /
quality metric + horizon \(h^*\) / \(\tau_q\)와 그 rule
(+quantile rule이면 `quality_reference_id`) / random seeds /
rarefaction \(n, R\), seed / bootstrap level·\(B_{boot}\)·seed /
Search-QD budget cap·sampling rule / software·data version.

## 9.5 Cache identity

§7.7의 4-요소 키를 최소로 하며, grid 산출물은 추가로
`grid_reference_id`에 종속된다.

## 9.6 Config keys

현행 `qd.*` 키(default.yaml:55-75 — descriptor_scope/horizons/
contrast/volatility/liquidity/horizon_reducer/descriptor_set 등)는
구 core(v1) 기준이다. 신규 키(behavioral core v2 선택, pairwise
grid, reference, quality/HQ, budget cap)는 구현 시 **Proposed**로
추가하고 legacy 키와의 관계를 LEGACY_INDEX에 기록한다.

---

# 10. Validation, Acceptance Criteria & Implementation Status

모든 항목에 Implemented / Proposed / Not implemented 3값 annotation을
적용한다 (§1의 상태 어휘). 값 미결 항목은 **Deferred parameter**로,
비규범 보존 경로는 **classification tag = legacy / non-normative**로
별도 표기하며 둘 다 status 값으로 쓰지 않는다.

## 10.1 Behavioral descriptor acceptance

QD_Descriptors_v2.md §11 검증 계약 그대로: ① \(\pm S\) runtime
invariance, ② **production-membership permutation-null B-coupling
회귀 (**Not implemented** — `QD_Descriptors_v2.md` §11의 "Pending"을 본
문서 상태 어휘로 정규화한 것이며, 정본의 acceptance 미완 사실은 동일하다),
③ hand-calculable 소형 케이스, ④ quantile
method="linear"·PctRank(method="average", pct=True) 고정 확인.

## 10.2 Grid acceptance

- 동일 입력 → 동일 bin (결정성).
- edge 경계값 테스트 (inclusive/exclusive 규약 고정).
- under/overflow 처리 테스트 + **no-clipping assertion**.
- **range 붕괴**: \(u_j - l_j < \epsilon\) → calibration failure +
  reason (fallback 금지) 테스트.
- TEST recalibration 금지 assertion (frozen edge 해시 대조).

## 10.3 Quality acceptance

OOS table과의 numerical parity, \(\tau_q\) freeze 확인(manifest 대조),
quality 결측 처리(§2.2-3), HQ 미설정 시 NaN+reason (§5.3 결함 수정).

## 10.4 QD metric hand tests

작은 toy pool로 Coverage/Entropy/HQCoverage/max-bin share를 수기
계산과 parity 확인. **undefined/edge case도 테스트에 포함**:
\(N_{in} = 0\) → NaN+`no_inrange_points`, \(n_{occ} = 1\) → evenness
NaN+`single_occupied_cell`, \(|P_{quality}| = 0\) → HQCoverage
NaN+`no_quality_eligible_points`, \(\tau_q\) 미설정 →
NaN+`hq_not_configured`, 셀 내 eligible 0 →
NaN+`no_quality_eligible_in_cell`, NN eligible \(N<2\) →
NaN+`insufficient_points`. 각 경우가 **0.0이 아닌 NaN**임을 assert.

## 10.5 Rarefaction

지표군에 따라 검사를 분리한다 (§6.6의 단조성 서술과 일치):

1. **전 지표 공통**: fixed seed 재현성, \(n = N\)일 때 full-pool
   결과와 **parity**.
2. **Coverage / HQ Coverage**: 표본 크기에 대한 **단조 비감소**
   sanity (nested 표본 기준 기대값).
3. **Entropy/evenness · NN · max-cell share**: 단조성 검사 금지 —
   대신 **finite 여부, 정의 range 내 여부(예: \(H^{norm} \in [0,1]\)),
   재현성**만 검사한다.
4. edge case: eligible \(N < n\)이면 rarefaction 결과는 NaN + reason
   (현행 `rarefaction_coverage`가 동일 동작).

## 10.6 Known implementation deviations (전부 repo 실측 확인, 추적 의무)

| # | 결함 | 근거 | 처리 |
|---|---|---|---|
| 1 | search-QD 좌표의 valid-PCA 결손 시 **test PCA 폴백** | runner.py:414-415 (ASB_design §4.4 [v1-hist]) | 제거 — §2.4 위반 |
| 2 | **PFS seed collision** — noise seed 키가 descriptor `seed` 컬럼과 병합 충돌 | ASB_design §9.3 [v1-hist] | 키 개명 |
| 3 | `qd.dedup != "exact"` 경로 — 병합 N×N, `n_factors_dropped` 음수 | ASB_design.md:706 [v1-hist] | 비-exact 경로 차단 (§7.1) |
| 4 | **HQ threshold null → hq_coverage 0.0 기록** | ASB_design §8.5 [v1-hist] | NaN+reason (§5.3) |
| 5 | `wall_clock_seconds` 항상 null | ASB_design §8.6 [v1-hist] | §7.7 비용 진단으로 대체 |
| 6 | `right_buffer_days`가 **캘린더 일수** → horizon 20 descriptor의 test 말미 관측 손실 | ASB_design.md:196,703 [v1-hist] | 거래일 기준으로 수정 |
| 7 | PCA/StandardScaler/PCA-NN/PCA-grid 산출물 | projection.py, runner.py:287+ | **legacy 분리** — primary 경로에서 제외 (§3.2) |
| 8 | budget ledger에 **proposal/evaluation 분리 부재** — 실패 합산·retry 중복 계수·평가 순서 의존성 | §7.3 (v2 §3.1.2) | `proposal_event_id` + `evaluation_key`(run-local first-seen) |
| 9 | rarefaction draw가 **축 간 미공유** + `k`의 의미 미확정 | §6.6 (v2 §7.3) | 공통 `draw_id` + **selected-k** estimand |
| 10 | **daily descriptor intermediate 미저장** → window 슬라이싱이 "재평가 없음"으로 성립하지 않음 | §2.4·§9.2a | `qd_daily_descriptor_intermediates`(Final-Pool 한정) |
| 11 | grid summary가 **context·split·window·factor_set을 식별하지 못함** | §9.2 | PK 명시 + `grid_id`/`qd_metric_id` 분리 |

## 10.6a 신규 계약의 acceptance test

1. **grid summary PK uniqueness** — 동일 (D1, D5, split, D6,
   `factor_set_id`, `grid_id`, `qd_metric_id`)에 두 행이 생기지 않고,
   **`qd_protocol_version`만 바꾸면 같은 PK가 나오지 않는지**.
2. **window slicing = 재평가 없음** — Strict 집계가
   `qd_daily_descriptor_intermediates`에서 **재집계만으로 재현**되고,
   `factor_set_id`가 두 window에서 동일하며 edge·\(\tau_q\)가 재보정되지
   않는지(§2.4).
3. **selected-k membership parity** — 동일 `draw_id`에서 QD와 Backtest의
   selected `formula_id` 목록이 **byte-for-byte 동일**하고,
   `n_selected = k`이며 `n_quality_eligible`·`n_active`는 다를 수 있음을
   확인(§6.6).
4. **budget ledger 4-case** — syntax alias / 재제안 / operational retry /
   교차 method 동일 raw가 각각 기대대로 계수되고 **평가 순서에 무관**한지
   (§7.3).
5. **grid/metric identity 분리** — 같은 `grid_id`가 서로 다른
   `qd_metric_id`에 재사용되는지(geometry 재사용 가능성 확인).
6. **`quality_reference_id` commitment** — 같은 rule·다른 실현
   \(\tau_q\)가 **다른 ID**를 갖는지(§5.3).

## 10.7 Frozen-test gate 체크리스트

최종 TEST 실행 전 다음이 **전부 freeze**되어야 한다:

descriptor version / reference population rule(+`grid_reference_id`) /
bin edges \([l_j,u_j], K_j\) / range-collapse \(\epsilon\) / pairwise
grids 구성 / quality metric + horizon \(h^*\) / \(\tau_q\)
(+`quality_reference_id`) / rarefaction rule(n, R, seed) / bootstrap
규약(unit=run, level, \(B_{boot}\), seed) / random seeds / output
schema / **method-level 판독 규약(§6.8)** / Search-QD budget cap과
sampling rule(§7.7).

하나라도 미freeze면 TEST 평가를 시작하지 않는다.

## 10.8 Implementation status 총괄

| 구성 요소 | 상태 |
|---|---|
| DE 2종, PFS 3-mode, **coverage-only rarefaction**(§6.6 — `rarefaction_coverage`), budget metrics(total/unique/memo), **legacy v1 descriptor drift 컬럼**(§8.5), per-alpha parquet 골격, generation trajectory | **Implemented** |
| raw-축 pairwise 6-grid, 공유 robust-range edge + `grid_reference_id`, **HQ 미설정 시 `hq_coverage` 0.0 → NaN+`hq_not_configured` 수정**(결함 4 — 기제는 존재, 동작만 교정), \(B_{unique}\) budget axis(§7.3), core v2 production 계산기(train_sign 제거 포함), raw 4D NN, method-level 판독 파이프라인, Search-QD cache contract, **full-metric same-draw rarefaction**(§6.6), **Core v2 drift + frozen-bin transition**(§8.5) | **Proposed** |
| transition matrix·revisitation·stagnation, **\(\tau_q\) 산출·freeze 경로**(VALID 분포 기반 rule 적용 — 대응 구현 전무), grid acceptance 테스트군, `quality_reference_id`, **`grid_id`/`qd_metric_id` 분리와 grid summary PK**(§9.2), **`qd_daily_descriptor_intermediates`**(§9.2a), **`report_window_id` 2 window 산출**(§2.4), **`proposal_ledger`와 run-local first-seen 계수**(§7.3), **`analysis_frame_id`/`draw_id` 기반 selected-k rarefaction**(§6.6) | **Not implemented** |
| PCA/StandardScaler/PCA-NN/PCA-grid | **Implemented** + tag: **legacy / non-normative** (§1 상태 어휘 — status가 아니라 classification tag; primary 경로에서 제외, §3.2) |
| \(K_j\), \(\tau_q\), budget cap, rarefaction \(k\) 격자/\(R\)/`draw_seed`, bootstrap level/\(B_{boot}\)/`bootstrap_seed`, range-collapse \(\epsilon\), reference population rule·최소 표본 수, **Q4 primary triple의 QD 측**(`grid_id`·`qd_metric_id`) | **Deferred parameter** (§1 어휘 — 값은 pre-test runbook/manifest) |

> **Deferred가 아닌 것 (확정됨)**: rarefaction estimand의 의미
> (**selected-k**, §6.6) · report window 적용 범위와 판독 지위(§2.4) ·
> reference population 정책 2종의 배타 선택 규칙(§5.3).
