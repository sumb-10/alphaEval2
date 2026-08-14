# AlphaSearchBench 전체 평가 프레임워크 구현 요청

현재 `AlphaEval` repository 안에 새로운 평가 프레임워크인 **AlphaSearchBench**를 구현해주세요.

AlphaSearchBench는 기존 AlphaEval 평가 코드를 수정해서 확장하는 프로젝트가 아니라,

> **alpha search/mining method가 생성한 formula와 alpha pool을 공통 기준에서 평가하기 위한 독립적인 benchmark/evaluation framework**

입니다.

최종적으로 다음 세 종류의 평가를 하나의 framework에서 수행하고 싶습니다.

1. **OOS Evaluation**

   * alpha signal 자체의 out-of-sample predictive generalization 평가

2. **QD Evaluation**

   * individual alpha의 behavioral descriptor
   * alpha pool의 behavioral diversity / density
   * search trajectory의 sampling distribution / coverage / transition dynamics 평가

3. **Backtest Evaluation**

   * 명시적인 portfolio construction 및 execution assumption 아래 실제 투자 성과 평가

그리고 이 세 evaluator 앞에는 공통적으로

4. **Formula / Signal Validity Gate**

가 존재해야 합니다.

전체 개념은 다음과 같습니다.

```text
Alpha Mining Result
(formulas / pool / weights / trajectory)
             │
             ▼
      Formula Loader
             │
             ▼
       SignalContext
 formula evaluation
 universe / label / benchmark
 train sign / normalization
             │
             ▼
       Validity Gate
             │
      ┌──────┼──────────┐
      ▼      ▼          ▼
     OOS     QD      Backtest
      │      │          │
      └──────┼──────────┘
             ▼
     Standardized Results
         + Manifest
```

---

# 0. 절대적인 작업 원칙

## 0.1 기존 AlphaEval 원본은 수정하지 마세요

가장 중요한 요구사항입니다.

기존 AlphaEval의 코드에서 활용할 수 있는

* formula evaluation
* IC / RankIC 계산
* z-score
* combination
* AlphaEval RRE
* PFS
* Diversity Entropy
* AlphaAgent Backtester
* TensorEvaluator
* FastICEvaluator

등의 아이디어와 구현은 충분히 참고하세요.

하지만 **기존 AlphaEval의 tracked source file은 수정하지 마세요.**

필요한 코드가 있다면:

1. 동작을 분석하고
2. 필요한 논리를 AlphaSearchBench 내부에 독립적으로 재구현하거나 port하고
3. provenance를 주석 또는 문서에 기록하세요.

최종 목표는 향후

```text
AlphaEval/AlphaSearchBench
```

디렉토리만 별도 repository로 떼어내더라도 최소한의 경로 수정만으로 독립 실행할 수 있는 구조입니다.

따라서 최종 AlphaSearchBench가 런타임에서 다음과 같은 AlphaEval 내부 모듈에 강하게 의존하는 구조는 피하세요.

```python
from backtest.modeltester import ...
from scripts.tensor_eval import ...
from Alphaagent.backtester import ...
```

초기 검증 과정에서 reference implementation과 비교하기 위한 import는 테스트 코드에서 허용하지만,

**production AlphaSearchBench runtime은 가능한 한 AlphaEval 내부 코드에 의존하지 않도록 구현하세요.**

Qlib 등 외부 dependency는 당연히 사용 가능합니다.

---

# 0.2 작업량이 크므로 반드시 Phase를 나누어 구현하세요

이 작업을 한 번에 구현하지 마세요.

각 Phase마다:

```text
구현
→ unit/smoke test
→ 결과 확인
→ 문제 수정
→ 해당 phase 완료 기록
→ 다음 phase
```

순서를 반드시 지키세요.

**이전 phase smoke test가 실패한 상태에서 다음 phase로 넘어가지 마세요.**

각 phase 종료 시 테스트 결과를 기록하세요.

---

# 0.3 TODO list를 만들고 지속적으로 갱신하세요

작업 시작 직후 다음 파일을 생성하세요.

```text
AlphaSearchBench/TODO.md
```

TODO는 최소한 다음 상태를 구분하세요.

```text
[ ] not started
[-] in progress
[x] completed
[!] blocked / issue
```

Phase별 세부 작업과 테스트까지 TODO에 기록하고,

각 phase가 끝날 때마다 업데이트하세요.

추가로

```text
AlphaSearchBench/docs/IMPLEMENTATION_PLAN.md
```

를 만들어 전체 architecture와 phase plan을 기록하세요.

---

# 0.4 기존 코드와 논문 정의를 구분하세요

AlphaEval 조사 결과,

**논문 정의와 공개 코드 구현이 여러 곳에서 다릅니다.**

따라서 AlphaSearchBench 내부에서는 다음 세 개념을 절대 혼동하지 마세요.

```text
legacy_alphaeval
paper_alphaeval
research_protocol
```

예를 들어:

```text
RRE_legacy
RRE_qd

PFS_legacy
PFS_paper_literal
PFS_qd_*
```

처럼 provenance를 명확히 남기세요.

AlphaEval 공개코드와 값이 다르다는 이유만으로 새로운 구현을 기존 코드에 맞춰 변경하지 마세요.

---

# 0.5 연구자가 아직 결정하지 않은 정의를 임의로 숨겨서 고정하지 마세요

다음과 같이 아직 연구적으로 선택의 여지가 있는 항목은 반드시 config에 노출하세요.

예:

* validity threshold
* volatility window
* volatility regime quantile
* liquidity regime threshold
* PFS mode
* PFS K
* PFS seed
* QD descriptor set
* PCA reference runs
* grid resolution
* high-quality threshold
* backtest execution mode
* transaction cost
* top/bottom percentage

코드 안에 magic number로 숨기지 마세요.

---

# Phase 0 — Repository audit + Scaffold

먼저 현재 환경과 repository를 조사하세요.

확인할 항목:

```text
Python version
qlib version
numpy
pandas
scipy
sklearn
pyarrow
joblib
yaml 관련 library
```

기존에 조사했던 다음 코드도 다시 읽으세요.

```text
backtest/modeltester.py
backtest/ictester.py
backtest/combo.py
backtest/noise_proc.py
Alphaagent/backtester.py

scripts/tensor_eval.py
scripts/fast_eval.py

gplearn/
AutoAlpha/
```

목적은 코드를 복사하는 것이 아니라 **동작과 interface를 파악하기 위함**입니다.

---

## 권장 디렉토리 구조

필요하다면 세부 구조를 조금 수정해도 되지만, 대략 다음과 같이 구성하세요.

```text
AlphaSearchBench/
│
├── README.md
├── TODO.md
├── pyproject.toml 또는 requirements 관련 파일
│
├── configs/
│   ├── default.yaml
│   ├── smoke.yaml
│   └── examples/
│
├── alphasearchbench/
│   │
│   ├── __init__.py
│   │
│   ├── config.py
│   ├── manifest.py
│   │
│   ├── data/
│   │   ├── signal_context.py
│   │   ├── qlib_provider.py
│   │   ├── universe.py
│   │   ├── labels.py
│   │   └── cache.py
│   │
│   ├── inputs/
│   │   ├── loaders.py
│   │   ├── schemas.py
│   │   └── trajectory.py
│   │
│   ├── validity/
│   │   ├── evaluator.py
│   │   └── metrics.py
│   │
│   ├── oos/
│   │   ├── evaluator.py
│   │   └── metrics.py
│   │
│   ├── qd/
│   │   ├── evaluator.py
│   │   ├── descriptors.py
│   │   ├── rre.py
│   │   ├── pfs.py
│   │   ├── diversity.py
│   │   ├── projection.py
│   │   ├── grid.py
│   │   └── trajectory.py
│   │
│   ├── backtest/
│   │   ├── evaluator.py
│   │   ├── simple.py
│   │   ├── qlib_native.py
│   │   └── metrics.py
│   │
│   ├── instrumentation/
│   │   ├── gplearn.py
│   │   └── autoalpha.py
│   │
│   ├── outputs/
│   │   ├── writer.py
│   │   └── schemas.py
│   │
│   └── cli.py
│
├── tests/
│   ├── unit/
│   ├── smoke/
│   ├── regression/
│   └── synthetic/
│
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── METRICS.md
│   ├── QD_DESCRIPTORS.md
│   ├── BACKTEST.md
│   ├── DATA_CONTRACT.md
│   └── REPRODUCIBILITY.md
│
└── out/
    ├── metrics/
    ├── daily/
    ├── trajectory/
    ├── manifests/
    ├── cache/
    └── plots/
```

모든 runtime output은 기본적으로

```text
AlphaSearchBench/out/
```

아래에 저장되게 하세요.

---

## Phase 0 Smoke Test

다음이 되는지 확인하세요.

```bash
python -m alphasearchbench --help
```

또는 이에 준하는 CLI.

또한:

* config load
* qlib initialization
* CSI universe load
* formula 한 개 평가

까지 smoke test를 만드세요.

예:

```text
tests/smoke/test_phase0_scaffold.py
```

Phase 0가 통과하기 전 다음 단계로 넘어가지 마세요.

---

# Phase 1 — Common SignalContext + Input Schema + Validity Gate

AlphaSearchBench 전체에서 OOS/QD/Backtest가 동일한 signal과 universe를 사용해야 합니다.

이를 위한 공통 계층을 구현하세요.

## SignalContext

최소한 다음을 담당해야 합니다.

```text
market
benchmark
train / valid / test split

point-in-time universe mask

raw feature panel
formula evaluation
signed / oriented factor signal

forward returns
benchmark returns
ADV20

daily cross-sectional z-score

pool combined signal
```

Formula를 평가하는 과정에서는 기존 `TensorEvaluator` 동작을 참고하되 AlphaSearchBench 내부에 독립적인 provider를 구현하세요.

---

# 절대로 silent fallback하지 마세요

현재 일부 AlphaEval 코드는 잘못된 formula를 `$close`로 fallback합니다.

AlphaSearchBench에서는 이를 금지합니다.

```text
formula evaluation failure
→ invalid factor
```

로 처리하세요.

반드시 error reason을 저장하세요.

---

# Train Sign

orientation은 반드시 train에서만 결정합니다.

```text
train_sign = sign(signed_train_IC)
```

valid/test에서 sign을 다시 추정하면 안 됩니다.

Evaluator 내부에서 test IC를 보고 방향을 결정하는 API 자체를 만들지 마세요.

가능한 interface:

```python
evaluate_factor(formula, train_sign)
```

signed train IC가 입력 결과 파일에 없으면 **train split에서 formula를 재평가하여 복원**할 수 있게 하세요.

---

# Validity Gate

최근 실측에서 높은 IC factor가 전체 universe의 **0.3% 정도의 cell에서만 유효**한 사례가 발견되었습니다.

따라서 validity는 매우 중요한 평가 계층입니다.

각 formula에 대해 최소한 다음을 계산하세요.

```text
valid
invalid_reason

n_total_days
n_valid_days
valid_day_ratio

mean_daily_n_valid
median_daily_n_valid
min_daily_n_valid

mean_daily_coverage_ratio
median_daily_coverage_ratio
p10_daily_coverage_ratio

const_day_ratio
inf_cell_ratio
nan_cell_ratio

formula_eval_failed
```

여기서

```text
daily_signal_coverage
=
n_valid_signal / n_universe
```

입니다.

주의:

**현재 단계에서 `mean_daily_n_valid < 30` 같은 임의 threshold를 코드에 박지 마세요.**

config에서 다음처럼 선택할 수 있게 하세요.

```yaml
validity:
  mode: report_only   # report_only | strict

  min_valid_day_ratio: null
  min_mean_daily_coverage_ratio: null
  min_median_daily_n_valid: null
```

구조적으로 correlation 계산이 불가능한 factor 등의 hard invalid만 기본적으로 제외하고,

research threshold는 이후 config에서 지정하도록 하세요.

---

## Phase 1 Smoke Test

Synthetic factor를 만들어 검증하세요.

최소한:

```text
정상 factor
constant factor
all-NaN factor
mostly-NaN factor
inf 포함 factor
evaluation error factor
```

를 사용하세요.

그리고

```text
tests/smoke/test_phase1_signal_validity.py
```

를 작성하세요.

추가로 기존 TensorEvaluator와 동일 formula 몇 개를 비교해 가능한 범위에서 numerical equivalence를 확인하세요.

---

# Phase 2 — OOS Evaluation Pipeline

OOS pipeline의 목적은 portfolio performance가 아니라 **signal 자체의 out-of-sample predictive ability**입니다.

기본 metric:

```text
Mean IC
Mean RankIC
ICIR
RankICIR
```

---

## IC

각 날짜 t에서

```text
PearsonCorr(
    oriented_alpha[t, :],
    forward_return[t, :]
)
```

를 계산합니다.

---

## RankIC

각 날짜 t에서 cross-sectional Spearman correlation을 계산합니다.

---

## ICIR

기본 정의:

```text
ICIR = mean(daily_IC) / std(daily_IC)
```

√252를 곱하지 않는 raw ICIR을 기본으로 하세요.

필요하면 별도 컬럼으로:

```text
ICIR_ann = ICIR * sqrt(252)
```

도 저장할 수 있게 하세요.

RankICIR도 동일합니다.

---

## Daily Series 저장

aggregate만 저장하지 말고 다음 raw series도 저장할 수 있게 하세요.

```text
date
formula_id
IC
RankIC
n_valid
coverage_ratio
```

이를 통해 metric 정의를 변경해도 formula를 다시 평가하지 않고 재집계할 수 있어야 합니다.

---

## Combined Alpha

pool combination은 component metric 평균이 아닙니다.

반드시 frozen weight로

```text
Z_i = daily_cross_sectional_zscore(alpha_i)

combined_signal
    = Σ_i weight_i * Z_i
```

를 만든 다음 combined signal 자체에서 IC/RankIC를 계산하세요.

Weights는 train에서 학습한 값을 그대로 사용합니다.

test에서 재최적화하면 안 됩니다.

---

## Label

OOS 기본 label:

```text
Ref($close, -1) / $close - 1
```

즉

```text
close_t → close_(t+1)
```

입니다.

test_end 이후 가격을 label 계산에 사용하는 현행 qlib extended-window 방식은 허용하되 manifest에 명시하세요.

```json
"label_uses_post_end_price": true
```

---

## OOS Output

최소:

```text
oos_factor_metrics.parquet

method
seed
formula
signed_train_IC
train_sign

IC
RankIC
ICIR
RankICIR
ICIR_ann
RankICIR_ann

valid
invalid_reason

signal coverage diagnostics...
```

Pool:

```text
oos_pool_metrics.parquet
```

---

## Phase 2 Smoke Test

Synthetic signal을 사용해:

```text
perfect positive signal → IC ≈ +1
perfect negative raw signal + train_sign=-1 → oriented IC ≈ +1
random signal → IC ≈ 0
constant signal → invalid
```

을 확인하세요.

Combined signal도 손계산 가능한 2-factor example을 테스트하세요.

---

# Phase 3 — QD Core Behavioral Descriptors

QD는 단순한 quality 평가가 아닙니다.

개별 alpha가 **어떤 시장 조건에서 어떤 behavior를 보이는가**를 descriptor로 나타냅니다.

Search-QD 기본 descriptor set은 계산비용을 고려해 다음으로 시작합니다.

```text
H  Information Horizon
V  Volatility Response
M  Market Direction Response
L  Liquidity Response
B  Activation Breadth
R  RRE
```

추가로 반드시:

```text
Signal Coverage
Signal Weight Turnover
Liquidity Footprint
```

도 raw descriptor로 저장하되,

기본 PCA core에 포함할지는 manifest에서 선택하도록 하세요.

---

# H — Information Horizon

다음 intermediate를 모두 저장하세요.

```text
IC_1d
IC_5d
IC_10d
IC_20d
```

forward return:

```text
close_(t+k) / close_t - 1
```

기본 scalar H는 configurable reducer로 구현하세요.

기본 후보:

```text
weighted_abs_ic_horizon

H =
Σ_h h * |IC_h|
/
Σ_h |IC_h|
```

분모가 너무 작은 경우 NaN 또는 invalid flag를 기록하세요.

raw IC들은 항상 보존하세요.

---

# V — Volatility Regime Response

benchmark는 market에 맞게 사용하세요.

예:

```text
CSI300  → SH000300
CSI500  → SH000905
CSI800  → SH000906
CSI1000 → SH000852
ALL     → SH000985
```

benchmark daily return의 rolling volatility를 사용하세요.

기본 window:

```text
20 trading days
```

단 config화하세요.

regime threshold는 반드시 **train split에서 계산하여 freeze**하세요.

기본:

```text
33.3% quantile
66.7% quantile
```

valid/test에서는 동일 threshold를 사용합니다.

high/low만 descriptor에 사용하고 mid는 기본적으로 제외하되 config로 변경 가능하게 하세요.

```text
IC_high_vol
IC_low_vol

V =
(IC_high_vol - IC_low_vol)
/
(|IC_high_vol| + |IC_low_vol| + eps)
```

모든 intermediate 값을 저장하세요.

---

# M — Market Direction Response

benchmark return:

```text
> 0 → up
< 0 → down
```

0은 기본 제외.

```text
IC_up
IC_down

M =
(IC_up - IC_down)
/
(|IC_up| + |IC_down| + eps)
```

---

# L — Liquidity Response

현재 `$amount`가 존재합니다.

```text
ADV20 = rolling_mean(amount, 20)
```

일별 cross-sectional liquidity percentile을 계산하세요.

기본은 high/low tercile을 사용하되 config화하세요.

```text
IC_liq_high
IC_liq_low

L =
(IC_liq_high - IC_liq_low)
/
(|IC_liq_high| + |IC_liq_low| + eps)
```

---

# B — Activation Breadth

20/20 quantile portfolio membership을 사용하면 거의 상수가 되므로 사용하지 마세요.

oriented daily z-score signal로:

```text
w_i ∝ z_i

p_i = |w_i| / Σ_j |w_j|

N_eff = 1 / Σ_i p_i²

Breadth = N_eff / N_valid
```

일별 계산 후 평균합니다.

---

# Signal Coverage

Activation Breadth와 구분하세요.

```text
SignalCoverage
=
mean_t (
  n_valid_signal(t) / n_universe(t)
)
```

* Coverage = factor가 값을 얼마나 넓은 universe에서 생성할 수 있는가
* Breadth = valid한 signal이 얼마나 넓게 weight를 분산시키는가

완전히 다른 개념입니다.

---

# Signal Weight Turnover

QD structural descriptor:

```text
0.5 * Σ_i |w_i(t) - w_i(t-1)|
```

여기서 w는 Breadth에서 사용한 z-score proportional weight입니다.

Backtest turnover와 이름을 명확히 분리하세요.

```text
signal_weight_turnover
portfolio_turnover
```

---

# R — RRE_qd

AlphaEval legacy 구현을 그대로 사용하지 마세요.

QD용 RRE는 날짜 t와 t-1의 **공통 universe**를 먼저 구합니다.

```text
U_common = U_t ∩ U_(t-1)
```

그 common universe에서 signal을 다시 rank한 뒤

```text
p_t(i)
=
rank_t(i) / Σ_j rank_t(j)
```

로 정규화하세요.

그리고

```text
KL_t
=
Σ_i p_t(i) log(p_t(i)/p_(t-1)(i))

RRE
=
mean_t 1/(1+KL_t)
```

를 계산합니다.

반드시 `train_sign`을 적용한 **oriented signal**로 계산하세요.

추가로:

```text
mean_common_n
min_common_n
```

등도 기록하세요.

---

## Legacy RRE

필요하다면 기존 AlphaEval 코드를 재현하는

```text
RRE_legacy
```

도 별도로 구현할 수 있지만,

QD 기본 metric은

```text
RRE_qd
```

입니다.

둘을 같은 이름으로 부르지 마세요.

---

## QD Core Smoke Test

Synthetic tests:

```text
매일 rank가 동일
→ RRE ≈ 1

rank가 크게 뒤집힘
→ RRE 감소

uniform z-score-like signal
→ 높은 breadth

소수 종목에 집중
→ 낮은 breadth

full coverage
→ signal coverage ≈ 1

sparse signal
→ 낮은 signal coverage
```

H/V/M/L도 인위적인 synthetic factor를 만들어 방향성을 검증하세요.

---

# Phase 4 — QD Projection / Pool Metrics

개별 descriptor를 QD space로 투영합니다.

---

# Descriptor Set은 manifest로 선택

예:

```yaml
qd:
  descriptor_set:
    name: core
    columns:
      - horizon
      - volatility_response
      - market_direction_response
      - liquidity_response
      - activation_breadth
      - rre_qd
```

향후:

```text
core
core_plus_coverage
core_plus_pfs
extended
```

등을 쉽게 비교할 수 있어야 합니다.

---

# PCA 전에 diagnostics

반드시 저장하세요.

```text
Pearson correlation matrix
Spearman correlation matrix

variance
missing ratio
```

특히:

```text
RRE ↔ turnover
PFS_G ↔ PFS_t
Horizon ↔ turnover
Liquidity response ↔ liquidity footprint
```

를 확인할 수 있게 하세요.

---

# Fixed PCA

PCA/Scaler는 **validation descriptor만 사용하여 fit**합니다.

test descriptor를 fit에 넣으면 안 됩니다.

```text
reference validation descriptors
        ↓
StandardScaler.fit
        ↓
PCA.fit
```

그리고:

```text
valid
test
new methods
```

모두 동일 transform을 사용하세요.

저장:

```text
scaler
PCA
descriptor order
explained variance
reference run IDs
reference split
```

---

# Grid

고정 QD grid를 만드세요.

하지만 **quantitative analysis에서 outlier를 단순 clipping하지 마세요.**

fixed bounds 바깥의 점은 다음처럼 기록하세요.

```text
pc1_underflow
pc1_overflow
pc2_underflow
pc2_overflow

overflow_ratio
```

시각화에서만 선택적으로 clip 가능합니다.

---

# Pool-level QD Metrics

최소:

```text
QD Coverage
Global Occupancy Entropy
Occupied-bin Evenness

NN Distance in PCA 2D
NN Distance in standardized raw descriptor space

High-Quality Coverage

Rarefaction / expected coverage @ N
```

---

## QD Coverage

```text
occupied_bins / total_bins
```

---

## Global Occupancy Entropy

```text
H_global
=
-Σ p_i log p_i
/
log(N_total_bins)
```

---

## Occupied-bin Evenness

```text
H_even
=
-Σ p_i log p_i
/
log(N_occupied_bins)
```

N_occupied=1 예외를 안전하게 처리하세요.

---

## High-Quality Coverage

quality metric과 threshold는 config에서 받습니다.

예:

```yaml
quality:
  metric: IC
  threshold: 0.02
```

test 분포를 보고 threshold를 자동 결정하면 안 됩니다.

---

## Rarefaction

method 간 candidate 개수 차이에 의한 coverage bias를 통제합니다.

고정 N에서 R회 subsampling하여:

```text
E[coverage @ N]
std[coverage @ N]
```

를 계산하세요.

random seed를 명시적으로 사용하세요.

---

# AlphaEval Diversity Entropy

Pool-level metric으로만 사용하세요.

individual descriptor로 사용하면 안 됩니다.

두 종류를 구분하세요.

### AlphaEval_DE_legacy

기존 공개 코드의:

```text
daily z-score
NaN → 0
covariance
eigenvalue entropy
```

를 가능한 한 재현.

### DE_common_valid

먼저 validity gate를 통과한 factor만 사용하고,

모든 factor가 동시에 valid한 common cells에서 covariance를 계산합니다.

함께:

```text
n_common_cells
common_cell_ratio
```

를 저장하세요.

common ratio가 지나치게 낮더라도 임의로 pairwise DE로 바꾸지 마세요.

---

## 지금은 DE_pairwise를 production metric으로 구현하지 마세요

pairwise covariance는 pair마다 observation set이 달라 covariance matrix가 PSD가 아닐 가능성이 있습니다.

향후 필요하면 별도 experimental metric으로 연구할 수 있습니다.

---

## Phase 4 Smoke Test

Synthetic pool:

```text
동일 alpha 10개
→ DE ≈ 0

독립/직교 alpha
→ DE 높음

한 bin에 모든 QD point
→ coverage 낮음 / evenness 처리 확인

여러 bin에 균등
→ entropy 상승
```

fixed PCA reload 후 transform 값이 완전히 재현되는지도 확인하세요.

---

# Phase 5 — Search-QD / Trajectory Evaluation

Final-pool QD와 Search-QD는 **별개의 실험**으로 취급하세요.

---

## Final-Pool QD

측정 대상:

```text
최종적으로 선택된 alpha
```

---

## Search-QD

측정 대상:

```text
search 중 평가된 unique candidate
generation별 population
```

목적:

```text
sampling distribution
coverage
quality density
transition dynamics
mode collapse
```

---

# trajectory schema

최소:

```text
run_id
method
seed

generation
idx_in_population

formula
signed_train_IC
raw_fitness

operation
parent_idx
donor_idx

program_length
program_depth

memo_hit
```

가능하면 run 종료 정보:

```text
final_pool
weights
```

도 저장하세요.

---

# 기존 AlphaEval source를 수정하지 않고 trajectory를 수집하세요

gplearn / AutoAlpha에 trajectory logging이 필요하다면

```text
AlphaSearchBench/instrumentation/
```

에 wrapper / monkey-patch / adapter를 두세요.

기존 gplearn/AutoAlpha source를 수정하지 마세요.

기존 run에 trajectory가 없으면 final_pool QD만 실행 가능하도록 graceful하게 처리하세요.

---

# Search-QD 계산 범위

모든 unique candidate에 기본적으로:

```text
H
V
M
L
B
RRE
Signal Coverage
```

를 계산합니다.

PFS는 계산비용 때문에 기본 Search-QD에는 포함하지 마세요.

---

# Generation Metrics

세대별:

```text
n_candidates
n_unique

mean quality
median quality

coverage
occupancy entropy
high-quality coverage

new occupied bins
cumulative occupied bins

PCA centroid
centroid displacement

descriptor distribution
valid candidate rate
```

을 계산하세요.

---

# Search Budget

method comparison에 반드시 저장하세요.

```text
total evaluations
unique evaluations
generations
population size
wall-clock time
memo hit ratio
```

GP와 AutoAlpha는 동일 generations/population이라도 실제 evaluation budget이 다를 수 있습니다.

따라서 budget-normalized comparison이 가능해야 합니다.

---

# Exact Deduplication

QD 분석의 기본은 formula string exact dedup입니다.

```text
duplicate formula
→ QD point는 1개
```

하지만 원래 population 기록은 삭제하면 안 됩니다.

둘을 분리하세요.

Near-duplicate correlation filtering은 기본적으로 적용하지 말고 optional analysis로 두세요.

---

## Phase 5 Smoke Test

작은 synthetic trajectory를 만들어:

```text
generation 0
generation 1
generation 2
```

에서 coverage가 증가하고 centroid가 이동하는 사례를 검증하세요.

trajectory가 없는 run도 final-pool QD가 정상 실행되어야 합니다.

---

# Phase 6 — PFS Extended QD

PFS는 계산비용 때문에 core Search-QD와 분리하세요.

기본 대상:

```text
final pool
selected candidates
```

입니다.

---

# 반드시 PFS mode를 분리하세요

현재 확인된 사실:

### AlphaEval 공개코드

```text
formula output 이후 noise
multiplicative:
S' = S * (1 + epsilon)

Pearson correlation
```

### AlphaEval 논문 표기

```text
raw feature tensor perturbation

S' = alpha(X + epsilon)

Spearman correlation

Gaussian:
sigma = corresponding market index daily volatility

Student-t:
df = 3
Gaussian과 동일 std

PFS = min(PFS_G, PFS_t)
```

하지만 논문은 heterogeneous raw feature X를 어떻게 normalize하는지 설명하지 않습니다.

따라서 최소한 다음 모드를 명시적으로 구분하세요.

```text
legacy_alphaeval
paper_literal
```

---

## legacy_alphaeval

공개 코드 재현용입니다.

이 결과는 연구용 PFS와 별도 이름으로 저장하세요.

---

## paper_literal

논문 문자적 정의:

```text
X + epsilon
```

을 적용하세요.

단 README/METRICS 문서에 반드시:

> raw heterogeneous feature scale normalization이 논문에 명시되어 있지 않으므로 literal implementation에는 scale ambiguity가 존재함

이라고 기록하세요.

---

# PFS_qd_relative

연구용 scale-aware perturbation은 좋은 아이디어지만 아직 perturbation semantics가 확정되지 않았습니다.

따라서 architecture는 반드시 pluggable하게 만드세요.

예:

```python
class PerturbationPolicy:
    perturb(panel, rng, config)
```

하지만 **Claude가 임의의 field-wise perturbation semantics를 production default로 확정하지 마세요.**

실험적인 `relative_input` policy를 구현하더라도:

```text
experimental
```

로 표시하고 기본 metric으로 사용하지 마세요.

---

# Deterministic Noise

모든 method가 동일 noise realization을 사용해야 합니다.

cache key:

```text
market
split
noise_type
seed
draw_id
dataset_version
perturbation_mode
```

`np.random.default_rng` 기반으로 결정론적으로 생성하세요.

모든 formula는 동일한 perturbed market tensor에서 평가되어야 합니다.

formula마다 새로운 noise를 만들면 안 됩니다.

---

# PFS Aggregation

PFS는 가능하면 **daily cross-sectional Spearman**으로 구현하세요.

```text
PFS_t
=
Spearman(
  original_signal[t, :],
  perturbed_signal[t, :]
)

PFS
=
mean_t PFS_t
```

flatten-all-cells 방식과 혼동되지 않게 구현 및 문서화하세요.

---

# K Draw

지원:

```text
K deterministic draws
```

저장:

```text
PFS_Gaussian
PFS_t
PFS_min

PFS_Gaussian_std_across_draws
PFS_t_std_across_draws

K
seed list
sigma
mode
```

---

## Phase 6 Smoke Test

최소:

```text
epsilon = 0
→ PFS = 1

same seed
→ exact reproducibility

different method / same market and seed
→ same perturbation tensor 사용

Gaussian/t scale check
Student-t df=3 check
```

---

# Phase 7 — Backtest: Simple Research Backtester

OOS label과 Backtest execution은 분리합니다.

OOS prediction target은 계속 close→next-close여도 됩니다.

Backtest는 실제 execution assumption을 명시합니다.

---

# Simple Research Portfolio

기본:

```text
top 20% long
bottom 20% short

equal weight

long gross = 0.5
short gross = 0.5

total gross = 1
net exposure = 0

daily rebalance
```

즉:

```text
Σ |w_i| = 1
Σ w_i = 0
```

top/bottom fraction은 config화하세요.

---

# Execution modes

최소한 다음을 지원할 수 있게 설계하세요.

```text
same_close
next_open_oo
next_open_oc
delayed_close_cc
```

기본 research backtest는:

```text
next_open_oo
```

를 권장합니다.

신호가 t close까지 정보를 사용한다면:

```text
signal observation : close t
entry              : open t+1
exit/rebalance     : open t+2
```

return:

```text
open_(t+2) / open_(t+1) - 1
```

입니다.

---

# same_close는 legacy / optimistic mode

```text
close_(t+1)/close_t - 1
```

은 t close information으로 t close 체결을 가정하므로 현실적인 기본 설정으로 사용하지 마세요.

명확히:

```text
legacy / optimistic
```

으로 표시하세요.

---

# Turnover

두 값을 모두 저장하세요.

```text
turnover_l1
=
Σ_i |w_i(t) - w_i(t-1)|

turnover_oneway
=
0.5 * turnover_l1
```

transaction cost 계산에는 어떤 정의를 사용하는지 manifest에 기록하세요.

---

# Cost

hard-code하지 마세요.

```yaml
backtest:
  transaction_cost_rate: ...
```

Daily:

```text
gross_return
transaction_cost
net_return
```

을 모두 저장하세요.

---

# Performance Metrics

최소:

```text
AnnRet_arith
CAGR
Sharpe
MDD

mean_daily_turnover_l1
mean_daily_turnover_oneway

annualized_turnover_l1
annualized_turnover_oneway

total_transaction_cost
gross cumulative return
net cumulative return
```

---

## AnnRet_arith

AlphaEval 논문 비교용:

```text
mean(daily_return) * 252
```

---

## CAGR

```text
(1 + cumulative_return)^(252/n) - 1
```

---

## Sharpe

```text
mean(daily_net_return)
/
std(daily_net_return, ddof=1)
*
sqrt(252)
```

기본 risk-free rate 0.

configurable interface를 열어두세요.

---

## MDD

결과 파일에서는 **positive magnitude**로 통일하세요.

manifest에 convention을 기록하세요.

---

# Daily Backtest Output

반드시 저장 가능해야 합니다.

```text
date
gross_return
cost
net_return
turnover_l1
turnover_oneway
long_count
short_count
gross_exposure
net_exposure
cumulative_return
```

---

## Phase 7 Smoke Test

손계산 가능한 작은 4~5종목 × 5일 데이터로:

```text
weights
return
turnover
cost
CAGR
AnnRet_arith
Sharpe
MDD
```

를 직접 계산한 expected value와 비교하세요.

특히:

```text
full portfolio flip
→ turnover_l1와 turnover_oneway 확인
```

을 테스트하세요.

---

# Phase 8 — Qlib Native Backtest

현재 환경에서 다음 API가 존재하는 것은 이미 확인되었습니다.

```python
from qlib.backtest import backtest
from qlib.backtest.exchange import Exchange
from qlib.contrib.strategy import TopkDropoutStrategy
```

하지만 TopkDropoutStrategy는 long-only이므로 연구용 long-short에는 맞지 않습니다.

AlphaSearchBench 내부에서 필요한 adapter/strategy를 구현하세요.

기존 AlphaEval 코드는 수정하지 마세요.

---

# 가장 중요한 Timestamp Audit

`deal_price="open"`이라는 사실만으로 next-open execution이 보장된다고 가정하지 마세요.

반드시 toy example을 통해 다음 네 시점을 출력하고 확인하세요.

```text
signal timestamp
decision timestamp
order timestamp
execution timestamp
```

우리가 원하는 next-open O→O는:

```text
t close signal
    ↓
t+1 open execution
    ↓
t+2 open rebalance
```

입니다.

Qlib이 실제로 이 lag를 지키는지 테스트로 증명하세요.

---

# qlib mode

가능하면:

```yaml
backtest:
  mode: qlib
  deal_price: open
  open_cost: ...
  close_cost: ...
  min_cost: ...
  limit_threshold: ...
```

를 지원하세요.

suspension / limit-up/down / transaction cost 등의 Qlib 기능을 활용하세요.

---

## Phase 8 Smoke Test

다음이 필수입니다.

```text
tests/smoke/test_phase8_qlib_timestamp.py
```

작은 날짜 범위에서:

```text
signal t
order t+1
execution open t+1
```

이 맞는지 로그로 검증하세요.

simple next_open_oo와 qlib native가 friction을 끈 상태에서 개념적으로 비슷한 결과를 내는지도 비교하세요.

---

# Phase 9 — Integration CLI + Outputs + Manifests

최종적으로 사용자가 다음과 비슷하게 실행할 수 있어야 합니다.

CLI 형태는 현재 repository 스타일을 보고 자연스럽게 설계하세요.

예:

```bash
python -m alphasearchbench evaluate \
  --config configs/experiment.yaml \
  --input path/to/miner_result.csv
```

개별 mode:

```bash
python -m alphasearchbench oos ...
python -m alphasearchbench qd ...
python -m alphasearchbench backtest ...
```

도 가능하면 좋습니다.

---

# Standard Output

최소 다음 파일을 생성하세요.

```text
out/metrics/
  validity_factor_metrics.parquet

  oos_factor_metrics.parquet
  oos_pool_metrics.parquet

  qd_factor_descriptors.parquet
  qd_pool_metrics.parquet

  backtest_factor_metrics.parquet
  backtest_pool_metrics.parquet
```

Daily:

```text
out/daily/
```

Trajectory:

```text
out/trajectory/
```

Manifest:

```text
out/manifests/
```

Projection:

```text
scaler.pkl
pca.pkl
qd_manifest.json
```

---

# Manifest

반드시 provenance를 저장하세요.

최소:

```text
AlphaSearchBench git commit
Python version
Qlib version
numpy/pandas/scipy/sklearn version

dataset path
dataset version/hash

market
benchmark

method
seed

train/valid/test dates

label definition
execution definition

train sign rule

validity config

descriptor set
regime thresholds

PFS mode
PFS seeds

PCA reference runs
PCA reference split

grid bounds
bin edges

backtest config

formula count
unique formula count

timestamp
```

---

# Cache Key

cache를 잘못 재사용하면 큰 문제가 됩니다.

최소 다음이 key에 포함되어야 합니다.

```text
formula
market
universe identity/hash

start/end
split

label
horizon

train_sign

dataset version

perturbation mode
perturbation seed/draw

normalization version
```

---

# Phase 9 Integration Smoke Test

작은 smoke config를 만드세요.

예:

```text
market = csi300
formula = 3~5개
short date range
```

다음 전체가 한 명령으로 실행되어야 합니다.

```text
load
→ signal
→ validity
→ OOS
→ QD
→ simple backtest
→ result parquet
→ manifest
```

그리고 다시 실행했을 때 deterministic 결과가 나와야 합니다.

---

# Phase 10 — Regression / Synthetic / Documentation

마지막 phase에서는 단순히 코드가 실행되는 것을 넘어 수학적으로 올바른지 검증하세요.

---

# Synthetic Tests

최소 다음을 포함하세요.

### OOS

```text
perfect predictor → IC 1
inverse predictor + train_sign -1 → oriented IC 1
random predictor → IC≈0
```

### RRE

```text
identical rank every day → RRE≈1
```

### PFS

```text
epsilon 0 → PFS≈1
```

### Diversity

```text
identical factors → DE≈0
orthogonal factors → DE 높음
```

### Backtest

손계산 가능한 portfolio.

### Reproducibility

```text
same formula
same config
same seed
→ exact same output
```

---

# AlphaEval Regression Test

소수 formula에 대해 기존 AlphaEval implementation과 비교하세요.

다만 이름과 의미를 구분하세요.

비교 대상:

```text
IC
RankIC
RRE_legacy
PFS_legacy
AlphaEval_DE_legacy
```

새 research metric이 legacy와 다르다고 실패로 판정하면 안 됩니다.

---

# Original AlphaEval 보존 검사

작업 마지막에 반드시 확인하세요.

**AlphaSearchBench를 만들기 전부터 존재하던 tracked file이 작업 과정에서 수정되지 않았는지 확인하세요.**

가능하면 이를 검사하는 test/script도 만드세요.

예:

```text
scripts/check_original_untouched.py
```

또는 git diff 기반 검사.

AlphaSearchBench 이외의 original source modification이 있다면 원상복구하세요.

---

# Documentation

최소 다음 내용을 문서화하세요.

## README.md

* AlphaSearchBench란 무엇인가
* 설치
* quick start
* input/output
* OOS/QD/Backtest 개요

## docs/METRICS.md

모든 metric의 수식.

특히:

```text
IC
RankIC
ICIR
RRE_qd
PFS modes
DE
QD Coverage
Entropy
NN Distance

AnnRet_arith
CAGR
Sharpe
MDD
Turnover
```

## docs/QD_DESCRIPTORS.md

각 behavioral descriptor의:

```text
정의
수식
해석
calibration split
known limitations
```

## docs/BACKTEST.md

```text
signal timing
execution timing

same-close
next-open O→O
next-open O→C
delayed-close

gross exposure
transaction costs
turnover
```

## docs/DATA_CONTRACT.md

input formula/result/trajectory schema.

## docs/REPRODUCIBILITY.md

```text
seed
cache
manifest
versioning
```

---

# 중요한 연구적 구분

최종 코드와 문서 전체에서 다음 개념들을 명확히 구분하세요.

```text
Signal Coverage
≠
Activation Breadth
≠
QD Coverage
```

그리고:

```text
AlphaEval DE
=
signal-space statistical diversity

QD Coverage
=
behavior-space coverage
```

입니다.

둘을 같은 diversity라고 설명하지 마세요.

또한:

```text
Final-Pool QD
≠
Search-QD
```

입니다.

Final-Pool QD는

> 최종적으로 무엇을 남겼는가

를 평가하고,

Search-QD는

> 어떤 behavior space를 탐색했고 search distribution이 어떻게 움직였는가

를 평가합니다.

---

# 권장 최종 평가 구조

최종적으로 다음 구조가 성립해야 합니다.

```text
                 Alpha Search Method
                         │
                         ▼
                 Candidate Formulas
                         │
                         ▼
                  Validity Gate
                  /            \
             valid             invalid
               │                  │
               │             diagnostics
               │
       ┌───────┼─────────┐
       ▼       ▼         ▼
      OOS      QD      Backtest
       │       │         │
       │       │         ├─ Simple
       │       │         └─ Qlib Native
       │       │
       │       ├─ Final Pool QD
       │       └─ Search Trajectory QD
       │
       ▼
 Standardized Benchmark Results
       │
       ▼
 Manifest + Reproducible Artifacts
```

---

# 최종 완료 조건

단순히 파일이 만들어졌다고 완료 처리하지 마세요.

다음 조건이 전부 만족되어야 합니다.

1. `AlphaSearchBench/` 밖의 기존 AlphaEval source가 수정되지 않았음.
2. AlphaSearchBench production runtime이 가능한 한 AlphaEval 내부 source import에 의존하지 않음.
3. Phase별 smoke test가 전부 통과함.
4. synthetic numerical tests가 통과함.
5. legacy AlphaEval regression test가 의도된 metric에서 통과함.
6. 작은 smoke experiment가 end-to-end로 실행됨.
7. OOS / QD / Backtest output parquet이 생성됨.
8. manifest가 생성됨.
9. 동일 config + 동일 seed 재실행이 deterministic함.
10. README와 metric documentation이 완성됨.
11. TODO.md의 모든 완료 항목이 실제 테스트 결과와 일치함.

---

# 작업 방식

먼저 `TODO.md`와 `docs/IMPLEMENTATION_PLAN.md`를 만들고 Phase 0부터 시작하세요.

각 Phase에서는 반드시:

```text
1. TODO에서 해당 phase를 in-progress로 변경
2. 구현
3. 테스트 작성
4. smoke test 실행
5. 실패하면 수정
6. 테스트 결과 기록
7. 완료 후 [x]
8. 다음 phase
```

순서를 지키세요.

작업 중 새로운 문제나 기존 설계와 충돌하는 사실을 발견했다면 이를 조용히 우회하지 말고

```text
AlphaSearchBench/docs/IMPLEMENTATION_NOTES.md
```

에 기록한 뒤, 가능한 경우 config 또는 명확한 interface로 해결하세요.

연구적 의미를 바꾸는 결정을 임의로 내리지 마세요.

다만 단순 구현 세부사항 때문에 작업을 중단할 필요는 없습니다. 합리적인 engineering decision은 문서화한 뒤 진행하세요.

**계획만 작성하고 끝내지 말고, Phase 0부터 최종 integration까지 실제 구현과 테스트를 순차적으로 수행해주세요.**

## 부록 — AlphaSearchBench v0.1 설계 확정 및 보류 사항

구현 과정에서 연구적 정의를 임의로 변경하지 않도록, 현재까지 확정된 사항과 아직 실험적으로 남겨둘 사항을 다음과 같이 구분합니다.

## A. v0.1에서 확정하여 구현할 사항

다음은 AlphaSearchBench의 기본 contract이므로 그대로 구현합니다.

* **평가 파이프라인 분리**

  * OOS: `IC`, `RankIC`, `ICIR`, `RankICIR`
  * QD: behavioral descriptors + final-pool/search diversity
  * Backtest: portfolio construction + execution + trading performance
* 모든 평가 앞에 **Validity Gate**를 둡니다.
* Alpha 방향은 오직 train에서
  `train_sign = sign(signed_train_IC)`으로 결정하고 valid/test에서 재결정하지 않습니다.
* Pool weights도 train에서 결정한 값을 valid/test에서 freeze합니다.
* OOS 기본 label은 `close_t → close_(t+1)`입니다.
* PCA/Scaler는 **validation descriptors만 사용하여 fit**하고 test는 transform만 수행합니다.
* **Final-Pool QD와 Search-QD는 별도 분석**으로 취급합니다.
* 잘못된 formula의 `$close` 등으로의 silent fallback은 금지합니다.
* QD point는 기본적으로 exact formula 기준으로 deduplicate합니다.
* 모든 stochastic component는 seed를 명시적으로 고정합니다.
* 최종 scalar뿐 아니라 raw/intermediate metric도 함께 저장합니다.
* 모든 주요 정의와 parameter는 manifest/config에 기록합니다.

### QD Core Descriptor

v0.1의 기본 QD descriptor는 다음으로 고정합니다.

```text
H = Information Horizon
V = Volatility Response
M = Market Direction Response
L = Liquidity Response
B = Activation Breadth
R = RRE_qd
```

다음 structural descriptor도 항상 계산하여 저장합니다.

```text
signal_coverage
signal_weight_turnover
liquidity_footprint
```

단, 이들을 PCA core에 포함할지는 config에서 선택할 수 있게 합니다.

### RRE_qd

QD용 RRE는 다음 정의를 사용합니다.

* `train_sign`을 적용한 oriented signal 사용
* 날짜 `t`, `t-1`의 공통 universe `U_t ∩ U_(t-1)` 사용
* 공통 universe 위에서 rank와 probability normalization을 다시 계산
* 이후 KL divergence와 RRE 계산

기존 AlphaEval 구현은 `RRE_legacy`, 연구용 구현은 `RRE_qd`로 구분합니다.

### 기본 Regime

v0.1 default는 다음으로 둡니다.

```text
Volatility:
benchmark 20-day rolling volatility
train tercile 기준
low vs high 비교

Market Direction:
benchmark return > 0 / < 0

Liquidity:
ADV20 = Mean(amount, 20)
일별 cross-sectional tercile
low vs high 비교
```

값은 config에서 변경 가능하게 합니다.

### Backtest

기본 research backtest는 다음으로 고정합니다.

```text
top 20% long
bottom 20% short
equal weight

long gross  = 0.5
short gross = 0.5
total gross = 1
net exposure = 0
```

기본 execution은:

```text
signal      = close t
entry       = open t+1
rebalance   = open t+2
execution   = next_open_oo
```

Turnover는 둘 다 저장합니다.

```text
turnover_l1     = Σ|Δw|
turnover_oneway = 0.5 × Σ|Δw|
```

Performance는 최소 다음을 저장합니다.

```text
AnnRet_arith = mean(return) × 252
CAGR
Sharpe
MDD
```

---

## B. 구조는 확정하지만 최종 연구 정의는 보류할 사항

### PFS

다음 namespace와 architecture는 지금 확정합니다.

```text
PFS_legacy
PFS_paper_literal
PFS_research
```

또한 deterministic noise, Gaussian / Student-t(df=3), 동일 perturbation의 method 간 공유, K-draw 지원 구조를 만듭니다.

다만 **`PFS_research`에서 raw feature를 정확히 어떻게 perturb할지는 아직 확정하지 않습니다.**

예:

```text
X + ε
X × (1 + ε)
field-wise scale-aware perturbation
```

중 무엇을 최종 research metric으로 사용할지는 pilot 결과를 보고 결정합니다.

따라서 `PerturbationPolicy`를 교체 가능한 구조로 만들고, experimental policy를 production default로 임의 지정하지 마세요.

### Diversity Entropy

v0.1에서는 다음만 구현합니다.

```text
AlphaEval_DE_legacy
DE_common_valid
```

`DE_common_valid`에는 반드시

```text
n_common_cells
common_cell_ratio
```

도 함께 저장합니다.

**Pairwise DE는 v0.1 공식 metric으로 사용하지 않습니다.**

Pairwise covariance는 pair마다 서로 다른 observation set을 사용해 PSD 문제가 생길 수 있으므로, 필요하면 pilot 이후 별도 research metric으로 검토합니다.

---

## C. 지표는 구현하되 threshold/세부값은 pilot 이후 결정할 사항

다음은 framework에서 계산 및 config interface는 제공하되 현재 숫자를 고정하지 않습니다.

* Validity threshold

  * minimum valid stocks
  * minimum signal coverage
  * minimum valid-day ratio
* QD grid resolution / PC bounds
* High-Quality Coverage threshold
* Transaction cost rate
* `PFS_research` perturbation policy
* Pairwise/alternative DE
* Horizon scalar reducer의 최종 선택

Validity Gate의 기본은:

```yaml
validity:
  mode: report_only
```

로 두고, 다음 validity statistics는 항상 저장합니다.

```text
valid_day_ratio
mean_daily_n_valid
median_daily_n_valid
mean_daily_signal_coverage
median_daily_signal_coverage
p10_daily_signal_coverage
const_day_ratio
nan_cell_ratio
inf_cell_ratio
```

Horizon 역시 다음 raw 값은 고정적으로 저장합니다.

```text
IC_1d
IC_5d
IC_10d
IC_20d
```

v0.1 default scalar는 weighted absolute horizon을 사용할 수 있지만 reducer는 configurable하게 유지합니다.

---

## 구현 원칙 요약

AlphaSearchBench v0.1에서는 **metric의 의미와 데이터 흐름은 명확하게 고정**하되,

```text
validity threshold
grid size
HQ threshold
PFS research perturbation
pairwise DE
```

처럼 실제 데이터와 pilot 결과를 확인해야 합리적으로 결정할 수 있는 항목은 config 또는 experimental extension으로 남겨두세요.

특히 **PFS research perturbation과 pairwise DE를 Claude가 임의로 공식 metric으로 확정해서는 안 됩니다.**
