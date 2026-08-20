# QD_DESCRIPTORS v2 — Behavioral Descriptor 정의·근거·계산 규약

> **QD Behavioral Core v2 — Frozen 2026-08-20.**
> Primary core = { Signal Breadth (B), Common-Universe Signal Weight
> Turnover (T_common), Liquidity Characteristic Spread (A_L^Q),
> Volatility Characteristic Spread (A_V^Q) }.
> 이후 정의·파라미터 변경은 **새 protocol version**을 요구한다.
> 선정 근거 실측: `docs/experiments/2026-08-20_QD_descriptor_pilot_v3.md`.

---

# 1. Purpose & Scope

이 문서는 AlphaSearchBench(ASB) QD 축에서 사용할 **alpha behavioral
descriptor**의 규범적 정의를 담는다 — 무엇을 behavioral descriptor로
쓰는가, 왜 그렇게 정의했는가, 어떻게 계산하는가.

이 문서가 다루지 않는 것 (전부 `qd_test_design.md` 소관):

- quality metric 및 quality overlay (HQ coverage 등)
- QD aggregation — behavioral grid/bin calibration, coverage, occupancy
  entropy, pairwise QD map, nearest-neighbor 지표
- Final-Pool QD vs Search-QD 프로토콜, rarefaction, DE, PFS
- grid protocol identity 및 QD 결과 시각화

(본 문서의 이전 개정판에 있던 behavioral space 해석·niche grid 절은
위 구분에 따라 `qd_test_design.md`로 이동한다.)

Core v2는 **frozen specification**이다: §11의 수식·파라미터가 확정본이며,
공식 실험 간 비교 가능성을 위해 이후 변경은 새 protocol version으로만
가능하다.

---

# 2. Design Principles

1. **Label-free** — behavioral descriptor는 future return / validation /
   test label을 일절 사용하지 않는다. predictive quality(IC, Sharpe 등)는
   behavioral coordinate와 분리된 축이다.
2. **Raw signal 기반** — 모든 core descriptor의 **signal-side input은
   oriented signal이 아니라 raw \(S\)** 이며 `train_sign`(orientation)을
   입력으로 요구하지 않는다. \(B\)·\(T_{common}\)은 \(S\)와 universe만
   사용하고, \(A_L^Q\)·\(A_V^Q\)는 추가로 **label-free한 과거/당일
   characteristic**(ILLIQ20, VOL20)을 사용한다.
3. **Sign invariance** — global sign reversal \(S \rightarrow -S\)에 대해
   모든 core descriptor 값이 불변이다 (runtime test 대상, §11).
4. **Method-agnostic** — 동일한 signal을 내는 alpha라면 GP/RL/LLM 등
   생성 방법과 무관하게 동일한 descriptor 값을 갖는다.
5. **Distinct but potentially correlated** — 네 descriptor는 서로 다른
   행동 차원을 측정하지만 orthogonality를 주장하지 않는다. 실제 alpha
   population에서 특정 factor family가 여러 차원에 동시에 노출될 수 있고,
   이는 정의의 결함이 아니라 측정 대상의 성질이다 (§10).
6. **Intermediate 보존** — scalar와 함께 재계산·진단에 필요한
   intermediate(signed 값, persistence, 유효 일수, 제외 진단)를 저장한다.

---

# 3. Shared Signal / Universe Contract

## 3.1 PIT universe와 finite-valid mask

\(U_t^{PIT}\)는 point-in-time universe mask다 (지수 편입일·편출일 span
기반 — 생존 편향 없음; 구현: `alphasearchbench/data/universe.py`).

일자 \(t\)의 descriptor 계산용 valid stock 집합은 **finite-valid mask가
가장 먼저 정의된다**:

\[
U_t^{valid} = \{\, i \mid i \in U_t^{PIT},\; S_{i,t}\ \text{finite} \,\}
\]

degenerate/nonfinite cell은 모든 계산에 **앞서** 제외된다. 구현이 계산
편의상 결측 셀을 0으로 표현하더라도(z-score 패널의 결측→0), **0은
representation일 뿐 valid observation이 아니다** — B/T는 반드시
finite-valid mask 기반으로 집계한다.

## 3.2 Daily z-score (B·T 전용)

\(U_t^{valid}\) 위에서 cross-sectional z-score를 계산한다:

\[
z_{i,t} = \frac{S_{i,t}-\mu_t}{\sigma_t},
\qquad \mu_t, \sigma_t = \text{mean, std over } U_t^{valid},
\qquad \sigma:\ \texttt{ddof=0}
\]

std convention은 **ddof=0** (population std — 현행 `daily_zscore`
구현과 동일, `signal_context.py`). \(\sigma_t\)가 수치적으로 0에
가까우면(< 1e-8) 해당일은 degenerate day로 제외하고 진단을 남긴다.
§3.3의 intersection re-z-score와 §5의 \(C_t\) re-z-score도 동일하게
ddof=0을 사용한다.

**A^Q 계열은 z-score magnitude를 필요로 하지 않는다** — signal의
ordering과 quantile threshold만 사용한다 (§6.3). 따라서 z-score 규약은
B·T에만 적용된다.

## 3.3 Characteristic intersection과 re-z-score

characteristic \(q\)(유동성/변동성 percentile)를 쓰는 descriptor는
교집합에서 계산한다:

\[
J_t = U_t^{valid} \cap \{\, i \mid q_{i,t}\ \text{finite} \,\}
\]

signal weight가 필요한 계산(진단용 A^W 포함)은 \(J_t\)에서 **다시
z-score(재중심화)** 한 뒤 L1 정규화한다 — \(\sum_{i \in J_t} z_i = 0\)이
보장되어 characteristic level이 누출되지 않는다. T_common도 공통
교집합에서 동일하게 재-z-score한다 (규약 통일).

## 3.4 최소 단면 크기 (frozen)

\[
\texttt{min\_cross\_section\_n} = 30
\]

\(|U_t^{valid}| < 30\) (T는 \(|C_t| < 30\), spread는 \(|J_t| < 30\))이면
해당일(쌍)을 제외하고 제외 건수를 진단으로 남긴다. 실측 비용: 731일 중
평균 14.0일 제외 (n<10 기준 대비 +4.1일) — §10.

## 3.5 train_sign 비의존

모든 core descriptor는 raw \(S\)에서 계산되고 \(\pm S\) 불변이므로
orientation 결정 경로(validity gate의 train-side IC)와 완전히 분리된다.
descriptor 계산 경로에 `train_sign` 입력을 두지 않는다
[구현 상태: Proposed — 현행 `QDDescriptorEvaluator.compute()`는
train_sign을 인자로 받음].

## 3.6 공통 저장 원칙

- `n_valid_days`, `n_degenerate_days`, `mean_n_valid`, `min_n_valid`
- descriptor별 유효 관측일 수, **제외 사유별 건수** (frozen 임계
  \(n < 30\) 기준; `excl_lt{2,10}`은 파일럿에서 쓴 선택적 민감도
  진단이며 production 계약이 아니다)
- descriptor별 계산 실패/분모 극소 플래그

v2 core descriptor는 모두 \([0, 1]\) 범위로 해석 가능하다.

---

# 4. Signal Breadth (B)

### 질문

> alpha의 signal mass가 유효 종목 전체에 넓게 분산되는가,
> 소수 종목에 집중되는가?

### 정의 (frozen)

\(U_t^{valid}\)에서 \(p_{i,t} = |z_{i,t}| / \sum_j |z_{j,t}|\)라 두고,

\[
N_{\mathrm{eff},t} = \frac{1}{\sum_i p_{i,t}^{2}},
\qquad
B_t = \frac{N_{\mathrm{eff},t}}{N_{\mathrm{valid},t}},
\qquad
\boxed{\, B = E_t[B_t] \,}
\]

### 근거

\(\sum_i p_i^2\)는 Herfindahl concentration이고 \(1/\sum p_i^2\)는
portfolio diversification의 inverse-Herfindahl / **effective number of
bets**와 동일한 수학적 구조다. 기존 portfolio concentration 개념을
factor signal mass에 이식한 것이다. 동치적으로
\(B_t = (E|z|)^2 / E[z^2]\) — 단면 signal magnitude의 concentration /
tail shape를 측정한다.

### 범위와 해석

\(0 < B \le 1\). \(B \to 1\): signal mass가 많은 종목에 균등 분산;
\(B \to 0\): 소수 종목에 집중. `Signal Coverage`(계산 가능한 종목 비율)와
다른 개념이다 — B는 **유효한 값들 중에서의** strength 집중을 잰다.

### 알려진 한계

- 실제 "활성 종목 수"가 아니라 signal distribution shape의 통계다.
- **search-space 의존**: bounded-output 연산자(ts-Rank, Rsquare 등)는
  구조적으로 B 상단에 놓인다 (실측: B 최고 0.74–0.77이 전부 해당 계열,
  최저 0.02는 nested variance 계열 — §10). cross-sectional rank
  연산자가 향후 search space에 추가되면 B가 상수로 퇴화하는지 재검토해야
  한다 (현행 GP/AlphaAgent space에는 cross-sectional 연산자 없음).
- economic style보다 output geometry에 가깝다.

### 저장 intermediate

`breadth_daily_mean`, `breadth_daily_std`, `breadth_n_days`,
`mean_n_eff`, `mean_n_valid`

---

# 5. Common-Universe Signal Weight Turnover (T_common)

### 질문

> alpha의 cross-sectional stock preference가 시간에 따라
> 얼마나 빠르게 변하는가?

### 정의 (frozen)

인접 거래일의 공통 유효 종목 집합에서 계산한다:

\[
C_t = U_{t-1}^{valid} \cap U_t^{valid}, \qquad |C_t| \ge 30
\]

양일의 signal을 **각각 \(C_t\)에서 re-z-score**한 뒤 L1 정규화한다:

\[
\tilde w_{i,s} = \frac{z^{C_t}_{i,s}}{\sum_{j \in C_t} |z^{C_t}_{j,s}|},
\quad s \in \{t-1, t\}
\]

\[
T_t = \frac{1}{2} \sum_{i \in C_t} |\tilde w_{i,t} - \tilde w_{i,t-1}|,
\qquad
\boxed{\, T_{\mathrm{common}} = E_t[T_t] \,}
\]

**Degenerate pair 제외**: 양일 중 하나라도 \(\sigma < 10^{-8}\)이거나
\(|C_t| < 30\)이면 해당 쌍을 제외하고 `n_pairs_used / n_pairs_skipped`를
기록한다.

### 근거와 채택 이유

portfolio literature의 \(\frac{1}{2}\sum|\Delta w|\) turnover와 동일한
L1 weight-change 구조를 실제 portfolio weight가 아닌 **standardized
factor-signal weight**에 적용한 것이다.

채택 근거 (파일럿 v3 확정): **universe entry/exit에 의한 기계적 turnover
channel을 정의상 제거하면서, 원래 signal temporal ordering은 거의
보존한다** (\(\rho(T_{\mathrm{common}}, T_{\mathrm{union}}) = 0.97\)).

**해석 정정 (중요)**: 과거의 "\(T_{union}\)–coverage 고상관 = universe
churn artifact"라는 설명은 폐기한다. T_common에서도 coverage와 −0.71
상관이 잔존하며, 상당 부분은 저커버리지·binary 계열 수식이 실제로 빠르게
변하는 신호라는 **실질 행동**이다 (§10).

### 범위와 해석

\(0 \le T_t \le 1\) — **정확한 bound**다: 양일 모두
\(\sum_i |\tilde w_{i,s}| = 1\)이므로 삼각부등식으로
\(\sum_i |\tilde w_{i,t} - \tilde w_{i,t-1}| \le 2\)이고, 상한은 전면
부호 반전 등에서 실제 도달 가능하다. \(T \to 0\): 종목 선호가 지속적
(실측 최저: triple-EMA 평활 수식 ≈ 0); \(T \to 1\): 빠른 재배치
(실측 최고 0.727: binary `Less(...)` 지표).

### 주의 — portfolio turnover와의 관계

`signal_weight_turnover`는 factor signal 자체의 temporal behavior이고,
backtest의 `portfolio_turnover`는 포트폴리오 구축 규칙·체결이 결정하는
운용 지표다. 같은 이름으로 사용하지 않는다.

### T_union · RRE의 지위

- \(T_{union}\)(합집합+결측 0, 기존 구현)은 **diagnostic**으로 병기 저장.
- `RRE_qd`는 \(T_{common}\)과 \(\rho = -0.95\)로 사실상 동일 정보이며
  rank 기반이라 \(\pm S\) 불변이 아니므로 (oriented 신호 소비) primary가
  아닌 **supplementary**로 유지한다 (§9). temporal primary는
  \(T_{common}\) 하나다.
- re-z-score와 단순 L1 재정규화 변형은 실측 \(\rho = 1.00\) — 정의는
  강건하며, re-z-score를 primary로 두는 이유는 §3.3 규약 통일이다.

### 저장 intermediate

`t_common_daily_mean/std`, `n_pairs_used`, `n_pairs_skipped`,
`T_union` (diagnostic)

---

# 6. Liquidity Characteristic Spread (A_L^Q)

### 질문

> alpha가 암시하는 long leg와 short leg가 liquidity characteristic에서
> 얼마나 멀리 떨어져 있는가?

## 6.1 Liquidity characteristic — ILLIQ20(min_obs=10) (frozen)

Amihud-style rolling illiquidity:

\[
ILLIQ20_{i,t} = \operatorname{mean}_{d \in [t-19,\,t],\ \text{obs}}
\frac{|r_{i,d}|}{DollarVolume_{i,d}}
\]

- \(r\)은 canonical `$close`의 close-to-close return (`$close`가
  수정주가임은 실측 확인: `$close = $adjclose × $factor`, 비율 상수 —
  corporate action이 |r|을 오염시키지 않음). 무채움 — 정지일은 결측.
- \(DollarVolume\) = `$amount` (거래대금). **amount ≤ 0 또는 결측인 날은
  관측에서 제외**하고, 20일 창에서 **유효 관측 ≥ 10** (min_obs=10)일
  때만 값을 정의한다 (10 vs 20 실측 무차이 \(\rho \ge 0.996\),
  커버리지 근소 우위로 10 채택 — §10).
- **full panel에서 rolling 후 split slice** (warmup 좌측 절단 방지).

## 6.2 PIT percentile (규약 freeze)

**PctRank 정의 (frozen)**: pandas `rank(axis=1, method="average",
pct=True)` — tie는 average rank, 정규화 분모는 **그날
characteristic-finite PIT 종목 수**

\[
N_t^{C} = \big|\{\, i \in U_t^{PIT} : C_{i,t}\ \text{finite} \,\}\big|
\]

(PIT universe 전체 수가 아님 — pandas rank는 non-NaN 개수로
정규화한다). liquidity와 volatility는 결측 구조가 다르므로
\(N_t^{L} \ne N_t^{V}\)일 수 있고, 각자의 \(N_t^{C}\)를 진단으로
저장한다. PctRank의 **가능한 전체 범위는 \([1/N_t^{C}, 1]\)이며, 양
endpoint는 해당 extreme value가 unique한 경우에만 달성된다** (예:
최댓값이 k개 tie면 그들의 pct = \(1 - (k-1)/(2N_t^{C}) < 1\)). tie가
있으면 실제 일별 support는 이 범위보다 좁다.

\[
q^L_{i,t} = 1 - \operatorname{PctRank}(ILLIQ20_{i,t})
\in [0,\ 1 - 1/N_t^{L}]
\]

즉 \(q^L\)의 가능한 범위는 \([0, 1 - 1/N_t^{L}]\)이고 (최저 유동성
종목이 unique할 때 \(q^L = 0\) 달성), \(q^V\) (§7.1)는 반전 없이
\([1/N_t^{V}, 1]\) — 두 characteristic의 endpoint가 \(O(1/N)\)만큼
비대칭이지만 \(N \approx 800\)에서 수치적으로 무시 가능하다. \(q^V\)도
동일 PctRank 계약을 공유한다.

percentile **모집단은 factor-valid subset이 아니라 PIT universe**이며,
그중 characteristic이 finite한 종목만 rank 대상이 된다 (따라서 분모는
\(N_t^{C}\) — 위 정의).

## 6.3 Leg 정의 — ASB backtest quantile selection rule의
characteristic-finite analogue (frozen)

**ASB backtest v0.1의 20/80 percentile-threshold selection rule**
(`alphasearchbench/backtest/simple.py:73-83`)을
**characteristic-finite intersection \(J_t\)** (§3.3)에 적용한다.
backtest 자체와 두 가지가 다름을 명시한다: ① backtest는 characteristic
결측 종목을 제거하지 않으므로 결측이 있으면 membership이 달라질 수
있고, ② **quantile cut \(Q_{0.2}, Q_{0.8}\)도 \(J_t\)에서 계산한다**
(backtest는 \(U_t^{valid}\) 전체에서 계산 — spread가 \(J_t\) 위에서
자기정합적으로 정의되도록 한 명시적 결정). characteristic이 전 종목에서
유효한 날에는 backtest membership과 정확히 일치한다:

\[
\text{top}_t = \{\, i \in J_t : S_{i,t} \ge Q_{0.8}(S_{J_t}) \,\},
\qquad
\text{bottom}_t = \{\, i \in J_t : S_{i,t} \le Q_{0.2}(S_{J_t}) \,\}
\]

- **Quantile method까지 freeze**: \(Q_p\)는 linear interpolation —
  `np.quantile(..., method="linear")` (구 numpy 인자명
  `interpolation="linear"`). 수학적 계약은 linear interpolation이며
  구현 버전이 바뀌어도 이 방법을 유지해야 아래 대칭성이 재현된다.
- overlap(퇴화 분포에서 양쪽에 속하는 셀)은 양 leg에서 제거.
- 어느 한 leg가 비면 그날 spread는 **미정의**(제외 집계, 임의 대체 금지).

**Tie-safe / \(\pm S\) 대칭성**: linear-interpolation quantile은
equivariant — \(Q_p(-v) = -Q_{1-p}(v)\) — 이고 비교가 inclusive이므로
\(S \to -S\)에서 top과 bottom이 **tie 포함 정확히 교환**된다. 별도
tie-breaking 정렬 규칙이 필요 없다. (파일럿 v3의 fixed-k argsort
membership은 근사였고 tie에서 \(\Delta \le 3.2 \times 10^{-3}\) 비대칭을
낳았다 — production 규약에서는 구조적으로 발생하지 않는다.)

## 6.4 정의 (frozen)

\[
X^L_t = \overline{q^L}_{\text{top}_t} - \overline{q^L}_{\text{bottom}_t}
\qquad (\text{leg 내 equal-weight 평균}),
\]

\[
\boxed{\, A_L^Q = E_t\left[\, |X^L_t| \,\right] \,}, \qquad
0 \le A_L^Q \le 1\ \text{(universal loose bound)}
\]

**Attainable maximum**: \(0 \le A^Q \le 1\)은 universal loose bound이며,
실제 도달 가능 최대는 **signal tie structure, overlap removal,
characteristic percentile support에 의존**한다 — 일반적으로 성립하는
1보다 작은 상수 상한은 없다. (leg는 20%보다 커질 수도 작아질 수도
있다: tie가 많으면 leg가 확대되고(§10.2-7), 반대로 중앙에 대량 tie가
걸리면 overlap 제거 후 양 leg가 20% 아래로 축소될 수 있다.) 참고로
파일럿 실측 최대는 0.71이었다.

### 금융적 의미와 근거

\(X^L\)은 alpha가 암시하는 **20/80 percentile-threshold로 정의된
top/bottom signal leg 사이의 liquidity-characteristic 차이**다
(leg 크기는 tie 구조에 따라 20%보다 크거나 작을 수 있다 — §6.3,
§10.2-7) — empirical asset pricing의 characteristic sorting /
holdings-weighted characteristic exposure 방법론을 alpha signal에
적용한 구조이며, liquidity proxy는 표준적인 Amihud illiquidity에
기반한다. leg 구성은 ASB backtest의 20/80 percentile-threshold
equal-weight long-short selection rule의 **characteristic-finite
analogue**(§6.3)이므로, 실제 backtest portfolio construction과 같은
경제적 객체의 characteristic spread를 잰다 — 단 characteristic 결측 시
membership이 실제 backtest와 달라질 수 있다(§6.3의 명시적 차이 2건).

- \(A_L^Q \approx 0\): long/short가 liquidity 측면에서 유사
- \(A_L^Q \to 1\): long/short가 liquidity spectrum의 양 극단에 위치

### 알려진 한계

- 절댓값 때문에 liquid-long인지 illiquid-long인지는 primary 값에서
  소실된다 — signed intermediate로 보완 (아래).
- Amihud ILLIQ는 liquidity의 완전한 측정이 아니라 price-impact proxy이며
  size/trading characteristic과 연관될 수 있다.
- 다른 liquidity proxy를 쓰려면 새 protocol version과 manifest 기록이
  필요하고, 동일 실험 안에서 method별로 다른 proxy를 쓸 수 없다.

### 저장 intermediate (필수)

- signed 값 \(E_t[X^L_t]\) 와 **persistence**
  \(= |E_t[X^L_t]| \,/\, E_t|X^L_t|\)
  (1 ≈ 방향이 기간 내내 일관, 0 ≈ 강한 tilt지만 방향이 계속 뒤집힘).
  \(E_t|X_t| = 0\)이면 persistence는 **NaN + reason
  (`no_spread_signal`)** — 0/0을 임의 값으로 대체하지 않는다.
- `mass_covered` — \(A^Q\) 자체에는 weight가 없으므로 이는 추정량이
  아니라 **커버리지 진단**이다. 정의:
  \(E_t\big[\sum_{i \in J_t} |z_{i,t}| \,/\, \sum_{i \in U_t^{valid}}
  |z_{i,t}|\big]\) — 원래 \(U_t^{valid}\)의 \(|z|\) mass 중 \(J_t\)에
  남은 비율.
- **Leg 진단** (tie-heavy factor 감사, §10.2-7): `n_top`, `n_bot`와
  함께 \(J_t\) 대비 비율 `top_share` \(= n_{top,t}/|J_t|\),
  `bottom_share` \(= n_{bot,t}/|J_t|\) (절대 leg 크기만으로는 30%
  leg인지 60% leg인지 판단 불가), `n_overlap_removed`,
  `n_empty_leg_days`
- `days_used`, 제외 진단, `illiq_window=20`, `illiq_min_obs=10`,
  percentile universe/version, **일별 \(N_t^{L}\)**
  (characteristic-finite PIT 종목 수 — percentile 분모, §6.2)

---

# 7. Volatility Characteristic Spread (A_V^Q)

### 질문

> alpha가 암시하는 long leg와 short leg의 stock-volatility profile이
> 얼마나 다른가?

## 7.1 Volatility characteristic — VOL20 (frozen)

\[
r_{i,t} = \frac{Close_{i,t}}{Close_{i,t-1}} - 1
\qquad (\text{canonical } \$close,\ \text{수정주가 — §6.1과 동일}),
\]

\[
VOL20_{i,t} = \operatorname{Std}(r_{i,t-19:t}),
\qquad \texttt{min\_periods} = 20\ (\text{전량 관측 요구}),
\qquad \texttt{ddof=1}
\]

std convention은 **ddof=1** (pandas rolling 기본 — 파일럿 v3와 동일).
min_periods=W로 관측 수가 항상 20 고정이므로 ddof는 단조 스케일
\(\sqrt{n/(n-1)}\)일 뿐 **cross-sectional percentile — 따라서
\(A_V^Q\) 값 — 에는 영향이 없음을 실측 확인**(rank 차이 0.0). 명시는
저장 intermediate(VOL20 절대값)의 재현성을 위한 것이다.

full panel rolling 후 split slice. PIT percentile (§6.2의 PctRank
규약 공유 — rank(method="average", pct=True)):

\[
q^V_{i,t} = \operatorname{PctRank}(VOL20_{i,t}) \in [1/N_t^{V},\ 1],
\qquad N_t^{V} = \big|\{ i \in U_t^{PIT} : VOL20_{i,t}\ \text{finite} \}\big|
\]

**큰 \(q^V\) = 높은 변동성**이며, \(q^V = 1\)은 당일 최대 변동성 종목이
unique할 때만 달성된다 (tie면 \(< 1\) — §6.2의 endpoint 규약).

## 7.2 정의 (frozen) — 동일 \(A^Q\) family

leg 정의·quantile 규약·미정의 규칙은 §6.3과 완전히 동일하다.

\[
X^V_t = \overline{q^V}_{\text{top}_t} - \overline{q^V}_{\text{bottom}_t},
\qquad
\boxed{\, A_V^Q = E_t\left[\, |X^V_t| \,\right] \,},
\qquad 0 \le A_V^Q \le 1
\]

(universal loose bound — 도달 가능 최대는 §6.4와 동일하게 tie
structure·overlap removal·percentile support에 의존한다.)

### Window 선택 근거 (frozen: W=20)

20 trading days는 past-one-month daily volatility의 문헌적 convention이며
가장 높은 시간 해상도를 보존한다. 파일럿 v3 sensitivity:
\(W \in \{20, 60, 120\}\)의 ordering이 \(\rho = 0.87\)–\(0.98\)로
안정적이어서 20 선택의 자의성이 낮음을 확인했다 (§10). 60/120은
sensitivity 기록으로 보존한다.

### 알려진 한계

- 절댓값으로 high-vol-long / low-vol-long 방향이 primary에서 소실 —
  signed intermediate로 보완.
- total volatility이며 idiosyncratic-volatility exposure와 동일하지 않다.
- liquidity와 volatility characteristic 자체가 시장에서 상관될 수 있다 —
  실측 판독은 §10 (특정 factor family의 실질 노출로 확인됨).

### 저장 intermediate (필수)

signed \(E_t[X^V_t]\), persistence(0/0 규약은 §6과 동일),
`mass_covered`, leg 진단(§6과 동일: `n_top`/`n_bot`/`top_share`/
`bottom_share`/`n_overlap_removed`/`n_empty_leg_days`), `days_used`,
제외 진단, `vol_window=20`, `vol_ddof=1`, return field/convention,
percentile universe/version, 일별 \(N_t^{V}\) (§6.2 — \(N_t^{L}\)와
다를 수 있음), sensitivity 산출 시 \(A_V^{Q,60}, A_V^{Q,120}\)

---

# 8. Why A^Q Was Selected

characteristic spread의 함수형으로 세 후보를 파일럿 v3에서 동시 대조했다
(모두 label-free·\(\pm S\) 불변):

| 후보 | 정의 | 결과 |
|---|---|---|
| \(A^W\) weighted tilt | \(E_t\|\sum_i \tilde w_i (2q_i - 1)\|\) | **primary 탈락** |
| \(A^Q\) quantile spread | \(E_t\|\overline{q}_{top} - \overline{q}_{bot}\|\) (\(Q_{0.8}/Q_{0.2}\) threshold legs) | **primary 채택** |
| \(A^\rho\) rank alignment | \(E_t\|\rho_S(S, q)\|\) | robust supplementary |

판정 근거 (permutation null test — characteristic을 일별로 종목 간
치환해 \(c \perp S\)인 null 생성):

1. **\(A^W\)는 null에서도 B와 −0.82/−0.81 (L/V) 상관** — 해석적 예측
   \(\mathrm{Var}(X^W \mid w) = \sigma_c^2 \sum \tilde w^2 =
   \sigma_c^2 / (N \cdot B)\) 그대로. 즉 signal이 집중될수록(낮은 B)
   characteristic과 무관해도 tilt가 기계적으로 커진다. 이는 caveat가
   아니라 측정 실패이므로 primary에서 탈락한다.
2. **\(A^Q\)는 null coupling이 없고** (+0.07/+0.17), real 신호는 null
   바닥의 약 10배 (0.31 vs 0.030). **파일럿의 fixed-k 정의에서는** null
   분산이 leg 크기(\(0.2N\))에만 의존하고 B와 무관한 구조다 —
   production threshold 정의에서는 leg 크기가 고정되지 않으므로(아래
   전이 주의) 이 논거를 그대로 확장하지 않는다.
3. \(A^\rho\)도 null coupling이 없으며 (+0.11), **전체 단면의 monotonic
   characteristic association**을 측정하므로 \(A^Q\)와 다른 관측 대상을
   제공한다 — robustness supplementary로 유지한다.
4. \(A^Q\)는 **ASB backtest의 economic object**(quantile 0.2
   equal-weight long-short portfolio)의 selection rule과 정렬된
   characteristic spread다 (characteristic-finite analogue — §6.3) —
   경제적 해석이 가장 직접적이다. \(A^\rho\)와의 정확한 구분은
   magnitude 보존 여부가 아니다(\(A^Q\)도 leg 내부 magnitude를 버리고
   membership만 사용한다): **\(A^\rho\)는 전체 단면의 monotonic
   association을, \(A^Q\)는 tail long/short leg의 characteristic
   spread를 측정하며 후자가 ASB portfolio selection rule과 직접
   대응**한다는 점이 우위의 근거다.

**Evidence → production 정의의 전이 주의**: 파일럿 v3의 \(A^Q\)
membership은 fixed-k argsort 근사였고, frozen production 정의는
inclusive quantile threshold(§6.3)다. tie-heavy factor에서는 두 정의의
leg 크기가 크게 다르므로(§10.2-7), **null coupling ≈ 0이라는 판정을
production 정의에서 자동으로 성립한다고 가정하지 않는다** — 구현
acceptance에서 production membership으로 permutation-null 회귀
테스트를 반드시 재수행한다(§11 검증 계약 ②).

상세 수치·재현: `docs/experiments/2026-08-20_QD_descriptor_pilot_v3.md`,
`out/qd_design_pilot/qd_descriptor_pilot_v3_valid.parquet`.

---

# 9. Supplementary / Deprecated Descriptor Classification

**"삭제"가 아니라 역할 변경이다** — 아래 지표는 모두 계속 계산·저장할 수
있으나 primary behavioral coordinate로 사용하지 않는다.

| 지표 | 분류 | 사유 |
|---|---|---|
| \(A^\rho\) (rank alignment) | supplementary | null-bias 없음; **전체 단면의 monotonic association**을 측정 (\(A^Q\)의 tail-focused spread와 관측 대상이 다름) — robustness 대조용 |
| \(A^W\) (weighted tilt) | diagnostic 전용 | B와 기계적 null coupling (§8) |
| \(T_{union}\) | diagnostic | universe churn channel 포함 — \(T_{common}\)과 0.97 |
| `RRE_qd` | supplementary (temporal) | \(T_{common}\)과 −0.95 동일 정보 + \(\pm S\) 비불변 |
| Liquidity Footprint \(\sum\|w\| q^L\) | structural diagnostic | \(\|w\|\)-가중 **노출 위치**이지 long-short **spread**가 아님 — backtest object와 불일치, primary 질문이 다름 |
| Volatility Footprint \(\sum\|w\| q^V\) | structural diagnostic | 상동 |
| Signal Coverage | structural / validity diagnostic | 경제적 sparsity 외에 warm-up/NaN/연산 가능성 혼재, Validity Gate coverage와 중복 |
| Information Horizon (H) | **Performance-Response** | future-return IC 사용 |
| Volatility Response (V) | Performance-Response | 상동 (market-regime 조건부 IC) |
| Market Direction Response (M) | Performance-Response | 상동 |
| Liquidity Response (L) | Performance-Response | 상동 (liquidity-cell 조건부 IC) |

## Performance-Response Descriptor (정의 유지)

기존 정의를 그대로 유지하되 behavioral 축이 아닌 별도 분류로 저장한다:

\[
H = \frac{\sum_h h |IC_h|}{\sum_h |IC_h|}, \quad
V = D(IC_{high\ vol}, IC_{low\ vol}), \quad
M = D(IC_{up}, IC_{down}), \quad
L = D(IC_{liq\ high}, IC_{liq\ low})
\]

\[
D(a,b) = \frac{a-b}{|a|+|b|+\epsilon}
\]

분모가 threshold 미만이면 scalar 해석을 강제하지 않고 `*_denom_small`
진단을 남긴다. Performance-Response는 behavioral coordinate로 사용하지
않는다 (predictive quality와 behavioral 좌표의 분리 — §2 원칙 1).

---

# 10. Empirical Validation & Known Limitations

## 10.1 파일럿 v3 실측 (정의 선정 근거)

> **주의**: 본 절의 \(A^Q\) empirical values와 correlation은 파일럿
> v3의 **fixed-k membership 근사**에서 산출된 descriptor-selection
> evidence이며, frozen production quantile-threshold specification의
> 최종 numerical validation 결과가 아니다. Production membership
> validation은 §11 acceptance test ②에서 수행한다 (Status: Pending).

컨텍스트: csi800, valid 2017-2019 (expB ASB eval manifest 재사용),
final_pool unique 183 (GP 132 + LLM 51; usable 156 — LLM 26건은 기지의
파서 비호환). 상세: `docs/experiments/2026-08-20_QD_descriptor_pilot_v3.md`.

**분산성·판별력** (A^Q 기준):

| | GP (n=132) | LLM (n=24) |
|---|---|---|
| B | 0.25 [p25 0.09, p75 0.30], max 0.77 | 0.52 [0.33, 0.66] |
| T_common | 이봉: 64개 ≤0.1 / 40개 >0.5 | 0.17 [0.09, 0.32] |
| A_L^Q | 0.17 [0.11, 0.64] | 0.11 [0.09, 0.13] |
| A_V^Q | 0.15 [0.08, 0.34] | 0.13 [0.10, 0.19] |

face validity: A_L^Q 최고 = `Min($amount,5)` 0.71 (거래대금 factor),
최저 = 가격비율 0.05; A_V^Q 최고 = vol-of-vol 계열; B 최저 = nested
variance(스파이크 집중), 최고 = bounded-output 연산자; T 최고 = binary
지표 0.727, 최저 = triple-EMA ≈ 0 — 각 descriptor가 의도한 behavior를
실제로 포착한다.

**Redundancy** (4×4 Spearman): B–T 0.29, B–L −0.39, B–V −0.25,
T–L −0.55, T–V −0.58, L–V 0.60 (전부 |ρ| < 0.8).

**L–V 상관의 원인 특정**: Pearson은 0.85로 높지만, 고 spread 클러스터
(\(A_L^Q \ge 0.5\)) 49개가 전부 `$amount`/`$volume` 포함 수식(거래활동
factor family)이며
**클러스터 밖(n=94)에서는 Pearson 0.09 / Spearman −0.14로 사실상
독립**이다. 즉 두 descriptor 정의가 중복된 것이 아니라 특정 alpha
family가 실제로 liquidity와 volatility에 동시 노출된 것 — 두 축 유지가
타당하며, 네 축은 **distinct but potentially correlated behavioral
dimensions**로 서술한다 (orthogonality 주장 금지). L–V pair의 실질
행동 상관은 redundancy diagnostics에서 명시적으로 해석한다.

## 10.2 알려진 한계

1. **B의 search-space dependence** — bounded-output 연산자가 B 상단을
   차지한다. cross-sectional 연산자 도입 시 재검토 (§4).
2. **T–coverage 실질 상관 (−0.71)** — 저커버리지·binary 계열이 실제로
   빠르게 변하는 신호라는 행동적 사실. T_common의 채택 근거는 churn
   channel의 정의상 제거이지 이 상관의 제거가 아니다 (§5).
3. **LLM 표본 소규모** — usable n=24; LLM 분포 수치는 참고용.
4. **파일럿 context ≠ 공식 benchmark calibration** — 파일럿(2017-2019
   valid)은 **descriptor 정의 선정의 근거**이며, behavioral bin
   calibration과 최종 reference distribution 산출은 공식 GP v2 temporal
   context에서 별도로 수행한다 (`qd_test_design.md` 소관 — 재수행
   대상은 calibration이지 descriptor 재선정이 아니다).
5. **semantic style 미구분** — momentum vs reversal, price- vs
   volume-driven, sector/style exposure 등은 v2 core가 직접 구분하지
   못한다. future extension 후보이며 primary v2에 포함하지 않는다.
6. **짧은 split 불안정성** — scalar만 보지 않고 유효 일수·일별
   표준편차·quantile·제외 진단과 함께 해석한다.
7. **Tie-heavy factor의 leg 확대** — inclusive threshold membership은
   tie가 많은 signal(binary 지표 등)에서 leg가 20%를 크게 초과할 수
   있다 (예: 값 1이 30%인 binary 신호, N=800 → legs 240/560; 파일럿
   근사 fixed-k는 항상 160/160). 이는 backtest v0.1 selection rule을
   그대로 물려받은 성질로 결함이 아니지만, **tie-heavy factor의
   \(A^Q\)는 "tail spread"가 아니라 사실상 전체 단면 대비**가 된다는
   해석 한계와, leg 크기가 signal family와 연동되므로 production
   membership에서 null coupling 회귀를 재확인해야 한다는 요구(§8)를
   낳는다. leg 진단 일체(`n_top`/`n_bot`/`top_share`/`bottom_share`/
   `n_overlap_removed`/`n_empty_leg_days` — §6.4)를 저장한다.

---

# 11. Frozen Specification Summary

**QD Behavioral Core v2 — Frozen 2026-08-20. 이후 변경은 새 protocol
version을 요구한다.**

| Descriptor | 수식 (일별 → \(E_t\)) | Frozen parameters |
|---|---|---|
| **Signal Breadth** \(B\) | \(N_{\mathrm{eff},t}/N_{valid,t}\), \(N_{\mathrm{eff}} = 1/\sum p^2\), \(p = \|z\|/\sum\|z\|\) | z-score on \(U^{valid}\) (ddof=0, §3.2), min_cross_section_n=30, degenerate day 제외 |
| **Common-Universe Signal Weight Turnover** \(T_{common}\) | \(\frac{1}{2}\sum_{C_t}\|\tilde w_t - \tilde w_{t-1}\|\) | \(C_t\)에서 양일 re-z-score(ddof=0) → L1 (§5), \(\|C_t\| \ge 30\), degenerate pair 제외 |
| **Liquidity Characteristic Spread** \(A_L^Q\) | \(E_t\|\overline{q^L}_{top} - \overline{q^L}_{bot}\|\) | ILLIQ20(min_obs=10), amount≤0 마스킹, \(q^L = 1-\mathrm{PctRank}\) (PctRank = rank(method="average", pct=True), 분모 \(N_t^{L}\) = characteristic-finite PIT 종목 수 — endpoint는 unique extreme일 때만 달성, §6.2), legs = backtest 20/80 threshold의 \(J_t\)-analogue (§6.3), \(Q\) = linear interpolation, overlap 제거, leg 결손 일 미정의, \(\|J_t\| \ge 30\) |
| **Volatility Characteristic Spread** \(A_V^Q\) | \(E_t\|\overline{q^V}_{top} - \overline{q^V}_{bot}\|\) | VOL20 (min_periods=20, ddof=1, 수정주가 close-to-close), \(q^V = \mathrm{PctRank}\) (분모 \(N_t^{V}\), 큰 값 = 고변동), legs 상동 |

공통: PIT universe, finite-valid mask 선행 (§3.1), label-free,
raw signal(train_sign 비의존), \(S \to -S\) 불변,
signed·persistence(0/0 → NaN + reason)·mass_covered·leg 진단
(`n_top`/`n_bot`/`top_share`/`bottom_share`/`n_overlap_removed`/
`n_empty_leg_days`)·제외 진단 intermediate 필수 저장.
\(0 \le A^Q \le 1\)은 universal loose bound이며, attainable maximum은
signal tie structure·overlap removal·characteristic percentile
support에 의존한다 (§6.4 — 일반적으로 성립하는 1 미만의 상수 상한은
없다).

검증 계약 (구현 acceptance): ① \(\pm S\) runtime invariance test
(절댓값 지표 불변 + signed 정확 반전), ② **permutation-null B-coupling
회귀 테스트를 production membership(quantile-threshold)으로 재수행**
[Status: **Pending**] — 파일럿 evidence는 fixed-k 근사였으므로
\(A^Q\)의 null coupling ≈ 0을 production 정의에서 재확인 (§8; core
정의의 재개봉이 아니라 frozen 정의의 acceptance 미완을 뜻한다),
③ hand-calculable 소형 케이스, ④ quantile method="linear" 및
PctRank(method="average", pct=True) 고정 확인. 상세 acceptance 기준과
grid/집계 프로토콜은 `qd_test_design.md`에서 정의한다.
