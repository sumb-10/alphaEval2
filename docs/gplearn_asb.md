# AlphaSearchBench/gplearn_asb 구현 요청 — Validity-aware GP with Worst-Fitness Penalty

현재 AlphaEval repository에는 기존 `gplearn` 기반 GP alpha mining 구현이 존재합니다.

최근 AlphaSearchBench pilot 평가에서 기존 GP의 높은 in-sample |IC| winner 중 일부가 다음과 같은 pathology를 보였습니다.

* `Rsquare`, `Power`, `Div`, rolling operator 조합에서 대부분의 종목/날짜가 NaN 또는 non-finite가 됨
* 극소수 valid cross-section에서만 IC가 계산됨
* 일부 winner는 train |IC|가 매우 높았지만 OOS에서 `no_correlatable_day`
* 일부는 median valid stocks가 0~2개 수준
* GP가 세대를 거치며 이러한 sparse-validity region을 selection pressure로 증폭했을 가능성

하지만 **기존 GP baseline은 반드시 보존**해야 합니다.

따라서 원본 `gplearn/` 및 관련 runner/source는 수정하지 말고,

```text
AlphaSearchBench/gplearn_asb/
```

라는 별도 디렉토리에 **Validity-aware GP variant**를 구현해주세요.

이 variant의 핵심 목적은:

> Original GP의 search space, operator set, population mechanics, crossover/mutation, tournament selection 등을 최대한 그대로 유지하면서, mathematically invalid 또는 research-validity가 낮은 candidate가 높은 IC fitness를 받아 선택되는 loophole만 통제하는 것

입니다.

---

# 1. 가장 중요한 원칙

## 1.1 Original GP source는 절대 수정하지 마세요

기존:

```text
gplearn/
scripts/run_gp_mine.py
scripts/fast_eval.py
```

등은 reference로만 사용하세요.

필요한 구현은:

```text
AlphaSearchBench/gplearn_asb/
```

내부로 copy/port/reimplement하세요.

작업 전후 git diff를 비교해 AlphaSearchBench 밖의 기존 tracked source에 추가 변경이 없는지 확인하세요.

---

## 1.2 gplearn_asb는 별도 experimental variant입니다

연구 결과에서는 반드시 다음을 구분합니다.

```text
gp_original
gplearn_asb
```

그리고 gplearn_asb 내부에서도 constraint mode를 구분합니다.

```text
gplearn_asb_off
gplearn_asb_hard_penalty
gplearn_asb_strict_penalty
```

결과 파일, manifest, trajectory에 method/constraint mode를 반드시 저장하세요.

---

# 2. 핵심 변경: reject-and-drop 금지

이번 구현에서 **invalid candidate를 population에서 삭제하지 마세요.**

기본 방식은:

```text
candidate 생성
    ↓
signal evaluation
    ↓
validity evaluation
    ↓
valid?
   /   \
 yes    no
 ↓      ↓
|IC|   worst fitness
 ↓      ↓
population에는 둘 다 유지
        ↓
tournament selection에서 invalid candidate는 자연스럽게 불리해짐
```

입니다.

즉:

[
\boxed{
\text{invalid candidate}
\Rightarrow
\text{worst fitness penalty}
}
]

이지,

[
\text{invalid candidate}
\Rightarrow
\text{population에서 삭제}
]

가 아닙니다.

---

# 3. Population size를 항상 유지하세요

Original GP의 population mechanics를 최대한 보존하기 위해:

```text
Generation 0: N
Generation 1: N
Generation 2: N
...
```

가 유지되어야 합니다.

예를 들어 population_size=1000이면 strict validity mode에서도 항상 1000개 candidate가 population에 존재해야 합니다.

Invalid candidate도 population row에는 남아 있어야 합니다.

단 selection에서 fitness가 최하위이므로 부모가 될 확률이 매우 낮아집니다.

---

# 4. Resampling은 이번 기본 구현에서 사용하지 마세요

다음 방식은 기본 구현에서 금지합니다.

```text
invalid → 새 candidate 생성
```

왜냐하면 이 경우 validity-aware GP가 original GP보다 더 많은 formula evaluation budget을 사용하게 되고, search mechanics 자체가 크게 변하기 때문입니다.

이번 v0.1의 기본 목적은:

```text
Original GP mechanics
+
Validity-based fitness penalty
```

입니다.

향후 필요하면 `constraint_handling=resample`을 별도 experimental extension으로 추가할 수 있지만 이번 기본 비교에서는 사용하지 마세요.

---

# 5. Original GP와 동일하게 유지할 것

다음은 가능한 한 동일하게 유지하세요.

```text
terminal set
operator/function set
tree representation

population size
generations

tournament selection
crossover probability
mutation probabilities

parsimony
initialization logic
random seed handling

fitness IC definition
population evolution logic
```

이번 작업에서 바꾸는 것은 오직:

```text
candidate validity를 fitness ranking에 반영
```

입니다.

Mutation/crossover 자체를 개선하거나 `$factor`를 제거하는 등의 변경은 이번 범위가 아닙니다.

---

# 6. Constraint modes

최소 다음 세 모드를 지원하세요.

## mode = off

```text
validity가 selection에 영향을 주지 않음
fitness = original |IC|
```

이 모드는 original GP equivalence 검증용입니다.

---

## mode = hard_penalty

Hard invalid candidate만 worst fitness를 받습니다.

```text
hard invalid
→ worst fitness

그 외
→ |IC|
```

---

## mode = strict_penalty

Hard invalid + research threshold 실패 candidate가 worst fitness를 받습니다.

```text
hard invalid
OR
research validity threshold fail
→ worst fitness

otherwise
→ |IC|
```

---

# 7. Hard invalid 정의

다음은 반드시 hard invalid로 처리하세요.

```text
formula_eval_failed

evaluation window 전체에서 finite signal 없음

correlation 가능한 날이 0일

valid IC observations = 0
```

Hard invalid는 `mode=hard_penalty`와 `mode=strict_penalty` 모두에서 worst fitness를 받습니다.

---

# 8. Research validity threshold

현재 pilot에서 제안된 provisional threshold:

```yaml
min_mean_daily_coverage_ratio: 0.05
min_median_daily_n_valid: 30
min_valid_day_ratio: 0.90
```

를 example config에서 사용할 수 있게 하세요.

하지만 절대 코드에 hard-code하지 마세요.

예:

```yaml
validity:
  mode: strict_penalty

  min_mean_daily_coverage_ratio: 0.05
  min_median_daily_n_valid: 30
  min_valid_day_ratio: 0.90
```

threshold는 이후 multi-seed pilot에서 바뀔 수 있습니다.

---

# 9. Worst fitness semantics를 명확히 구현

현재 gplearn fitness direction과 selection semantics를 확인한 뒤 올바르게 구현하세요.

중요한 조건:

* invalid fitness를 `NaN`으로 두지 마세요.
* tournament comparison이 항상 deterministic하게 동작해야 합니다.
* invalid candidate는 모든 valid candidate보다 불리해야 합니다.

예를 들어 maximization이면:

```text
valid fitness:
    abs(IC)

invalid fitness:
    finite worst sentinel
```

또는 gplearn 내부 convention에 맞는 최악 fitness 값을 사용하세요.

무작정 `-inf`를 넣기 전에 기존 selection/parsimony 코드가 이를 안전하게 처리하는지 확인하세요.

---

# 10. Population에는 invalid candidate를 그대로 보존

모든 candidate에 다음을 기록하세요.

```text
formula
generation
candidate_id

raw_signed_train_IC
abs_train_IC

raw_fitness
effective_fitness

hard_invalid
research_invalid
validity_pass

invalid_reason
```

여기서:

```text
raw_fitness
```

는 validity penalty를 적용하기 전 원래 IC fitness이고,

```text
effective_fitness
```

는 selection에 실제 사용된 fitness입니다.

예:

```text
raw_fitness = 0.565
effective_fitness = WORST
research_invalid = true
```

가 가능해야 합니다.

이 구분은 매우 중요합니다.

---

# 11. Train data에서만 validity 계산

Validity filtering에는 절대로 valid/test 데이터를 사용하지 마세요.

Mining 과정은:

```text
search train window
    ↓
candidate signal
    ↓
train validity
    ↓
train IC
    ↓
effective fitness
```

만 사용합니다.

Validation/test coverage나 OOS IC는 mining이 끝난 뒤 AlphaSearchBench에서만 평가합니다.

---

# 12. Mining window와 ASB evaluation split을 분리

기존 GP mining period와 AlphaSearchBench의 train/valid/test split이 다를 수 있습니다.

예:

```text
mining window = 2010–2019
ASB train     = 2010–2016
ASB valid     = 2017–2019
ASB test      = 2021–2024
```

따라서 `gplearn_asb`에서는 명시적인:

```yaml
search:
  start_date: ...
  end_date: ...
```

를 사용하세요.

Mining validity와 train IC는 이 search window에서 계산합니다.

ASB의 evaluation split과 혼동하지 마세요.

---

# 13. Signed train IC를 반드시 보존

기존 run에서는 signed IC가 저장되지 않아 train_sign을 사후 복원해야 했습니다.

이번 구현에서는 모든 candidate에 반드시:

```text
signed_train_IC
abs_train_IC
train_sign
```

을 저장하세요.

```text
train_sign = sign(signed_train_IC)
```

입니다.

---

# 14. Validity diagnostics

각 unique candidate에 최소 다음을 저장하세요.

```text
formula

generation
candidate_id

signed_train_IC
abs_train_IC

raw_fitness
effective_fitness

hard_invalid
research_invalid
validity_pass
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

nan_cell_ratio
inf_cell_ratio
const_day_ratio
```

AlphaSearchBench validity schema와 column naming을 최대한 통일하세요.

중복된 validity implementation을 만들지 말고 가능하면 ASB public validity API를 재사용하세요.

---

# 15. 세대별 population-collapse diagnostic

Worst-fitness penalty를 쓰더라도 valid candidate가 지나치게 적으면 parent diversity가 감소할 수 있습니다.

따라서 각 generation에서 반드시 다음을 기록하세요.

```text
population_size

n_hard_valid
n_research_valid
n_invalid

hard_invalid_rate
research_invalid_rate
valid_candidate_rate

n_unique_valid
n_unique_total
```

특히:

[
ValidCandidateRate_g
====================

\frac{N_{valid,g}}{N_{population,g}}
]

를 핵심 metric으로 저장하세요.

---

# 16. Parent diversity도 기록

예를 들어 population=1000이어도 valid candidate가 20개뿐이면 tournament selection이 그 20개에 집중되어 diversity collapse가 발생할 수 있습니다.

가능하면 generation별:

```text
n_unique_parents_selected
parent_selection_entropy
top_parent_selection_share
```

도 저장하세요.

최소한:

```text
n_unique_parents_selected
```

는 구현하는 것을 권장합니다.

이 값은 validity penalty가 search diversity를 얼마나 줄이는지 판단하는 데 중요합니다.

---

# 17. Search trajectory logging — 필수

AlphaSearchBench Search-QD compatible trajectory를 저장하세요.

최소 schema:

```text
run_id
method
constraint_mode
seed

generation
idx_in_population

formula

signed_train_IC
abs_train_IC

raw_fitness
effective_fitness

hard_invalid
research_invalid
validity_pass
invalid_reason

mean_daily_coverage_ratio
median_daily_n_valid
valid_day_ratio

program_length
program_depth

operation
parent_idx
donor_idx

memo_hit
```

Invalid candidate도 반드시 trajectory에 남겨야 합니다.

삭제하면 GP가 invalid search region을 얼마나 탐색했는지 분석할 수 없습니다.

---

# 18. Generation-level statistics

각 generation마다 다음을 저장하세요.

```text
population_size

n_candidates
n_unique
n_unique_valid

hard_invalid_rate
research_invalid_rate
valid_candidate_rate

mean_signal_coverage
median_signal_coverage
median_n_valid

mean_raw_train_IC
best_raw_train_IC

mean_valid_train_IC
best_valid_train_IC

mean_effective_fitness
best_effective_fitness

n_unique_parents_selected
```

이를 이용해:

```text
generation ↑
train IC ↑ ?
coverage ↓ ?
invalid rate ↑ ?
parent diversity ↓ ?
```

를 분석할 수 있어야 합니다.

---

# 19. Invalid candidate의 raw IC를 버리지 마세요

이번 연구의 핵심 중 하나는:

> 높은 IC candidate가 실제로 validity loophole과 연결되는가?

입니다.

따라서 invalid candidate라도 원래 계산 가능했던 raw IC가 있다면 저장하세요.

예:

```text
formula X
raw abs IC = 0.565
coverage = 0.003
effective fitness = WORST
```

이렇게 해야 나중에:

```text
raw IC vs coverage
raw IC vs valid_day_ratio
raw IC vs complexity
```

를 분석할 수 있습니다.

---

# 20. Cache 구조

가능하면 다음을 분리하세요.

```text
formula evaluation cache
    ↓
signed IC
validity diagnostics
    ↓
constraint mode / threshold application
    ↓
effective fitness
```

즉 threshold가 바뀌더라도 signal과 validity statistics를 다시 계산하지 않도록 하세요.

Cache key에는 최소:

```text
formula
market
universe
search period
dataset identity
evaluation semantics version
```

를 포함하세요.

Threshold 자체는 derived decision이므로 diagnostics cache와 분리하는 것을 권장합니다.

---

# 21. Original GP equivalence

먼저:

```text
validity.mode = off
```

에서 gplearn_asb가 original GP와 가능한 한 동일하게 동작하는지 확인하세요.

동일 조건:

```text
dataset
market
search period
seed
population size
generations
function set
terminal set
tournament size
crossover/mutation probabilities
parsimony
```

에서 최소:

```text
initial population formulas
signed IC
raw fitness
generation 0 ordering
```

을 비교하세요.

가능하면 이후 generation 결과도 비교합니다.

차이가 있으면 이유를 `IMPLEMENTATION_NOTES.md`에 기록하세요.

---

# 22. Same-seed generation 0 equality

Validity penalty가 들어가기 전 generation 0 후보 자체는 original GP와 같아야 합니다.

따라서 regression test:

```text
same seed
same config

original initial population
==
gplearn_asb initial population
```

을 추가하세요.

Validity penalty 때문에 generation 1부터 evolutionary path가 달라지는 것은 정상입니다.

---

# 23. 실제 pathological formula regression

기존 AlphaSearchBench pilot에서 발견된 winner formula를 fixture로 사용하세요.

예:

```text
Rsquare(...)
Power($volume, $open)
WMA/Rsquare/Div/Slope 복합식
```

실제 정확한 formula는 pilot output에서 읽어오세요.

Expected:

```text
raw IC may be high

BUT
coverage extremely low
→ research_invalid = true
→ effective_fitness = worst
```

반면:

```text
Log($volume)
```

같은 정상 formula는:

```text
normal/high coverage
→ validity pass
→ effective_fitness = abs(IC)
```

이어야 합니다.

---

# 24. Threshold boundary tests

Synthetic tests로:

```text
coverage = 0.050 exactly
median valid n = 30 exactly
valid_day_ratio = 0.900 exactly
```

일 때 pass하도록 하세요.

Convention:

```text
value >= threshold
→ pass
```

입니다.

---

# 25. Population stability synthetic test

다음 테스트를 반드시 추가하세요.

```text
population size = 100

valid = 10
invalid = 90
```

이어도 다음 generation의 population size는:

```text
100
```

으로 유지되어야 합니다.

그리고:

```text
invalid individuals remain in population data
but have worst effective fitness
```

인지 확인하세요.

---

# 26. Penalty effectiveness test

Synthetic tournament population에서:

```text
valid candidate:
raw fitness = 0.02

invalid candidate:
raw fitness = 0.80
effective fitness = WORST
```

일 때 invalid candidate가 높은 raw IC 때문에 부모로 선호되지 않는지 검증하세요.

즉 selection은 반드시:

```text
effective_fitness
```

를 사용해야 합니다.

---

# 27. 우리가 비교할 핵심 세 조건

최종적으로 같은 experiment config에서:

## A. Original GP

```text
gp_original
fitness = |IC|
```

## B. Hard Penalty

```text
gplearn_asb
constraint_mode = hard_penalty
```

## C. Strict Penalty

```text
gplearn_asb
constraint_mode = strict_penalty
```

를 비교할 수 있어야 합니다.

---

# 28. 공정 비교 조건

세 실험에서 반드시 동일:

```text
dataset
market
universe

search period

population size
generations

initial seed

function set
terminal set

tournament size
crossover
mutation

parsimony

raw IC definition
```

입니다.

변하는 것은:

```text
effective fitness validity penalty
```

뿐이어야 합니다.

---

# 29. Evaluation budget

Worst-fitness penalty는 candidate를 resample하지 않으므로 original GP와 동일한 candidate count를 유지하는 것이 원칙입니다.

따라서 동일:

```text
population × generations
```

조건에서 evaluation budget이 가능한 한 동일해야 합니다.

그래도 cache/memo hit 차이는 생길 수 있으므로:

```text
total_evaluations
unique_evaluations
memo_hits
wall_clock
```

을 저장하세요.

---

# 30. AlphaSearchBench와 연결

gplearn_asb 결과는 별도 변환 없이 AlphaSearchBench의 표준 input schema로 읽을 수 있어야 합니다.

최종 run 이후 반드시:

```text
Validity
OOS
Final-Pool QD
Search-QD
Simple Backtest
```

를 수행할 수 있게 하세요.

---

# 31. 핵심 연구 가설

## H1 — Original GP loophole exploitation

세대가 진행될수록 original GP에서:

```text
raw train IC ↑
signal coverage ↓
invalid rate ↑
```

가 나타나는가?

---

## H2 — Worst-fitness penalty 효과

Strict penalty가:

```text
high raw IC
+
extreme low coverage
```

candidate를 selection에서 제거하는가?

---

## H3 — OOS generalization

Validity-aware GP가 original GP보다:

```text
best raw train IC
```

는 낮아져도:

```text
valid candidate rate
validation IC
test IC
test RankIC
```

가 개선되는가?

---

## H4 — Diversity cost

Worst-fitness penalty 때문에:

```text
valid parent pool 감소
→ search diversity 감소
```

가 발생하는가?

이를:

```text
n_unique_valid
n_unique_parents_selected
Search-QD coverage
NN distance
```

등으로 평가합니다.

---

# 32. 중요한 해석 원칙

Validity-aware GP가 더 좋다고 미리 가정하지 마세요.

가능한 결과는 모두 열어둡니다.

```text
A. OOS 개선
B. OOS 변화 없음
C. diversity collapse
D. valid candidate 부족
E. train IC만 하락
F. pathological alpha만 제거되고 search quality는 동일
```

어떤 결과든 그대로 보고하세요.

---

# 33. 작업 Phase

## Phase A — Audit

기존 GP:

```text
entrypoint
genetic loop
fitness direction
parallel evaluation
cache
random seed
selection
```

을 확인합니다.

TODO와 implementation plan 생성.

---

## Phase B — Original-equivalent copy

`gplearn_asb`를 만들고:

```text
constraint_mode = off
```

에서 original GP와 equivalence 확인.

---

## Phase C — Validity diagnostics only

Validity statistics를 계산하고 저장하지만 selection에는 아직 적용하지 않습니다.

---

## Phase D — Hard worst-fitness penalty

Hard invalid → worst effective fitness.

Population에서는 삭제하지 않습니다.

---

## Phase E — Strict worst-fitness penalty

Research validity fail → worst effective fitness.

Population에서는 삭제하지 않습니다.

---

## Phase F — Trajectory / population diagnostics

Generation metrics와 parent diversity logging을 완성합니다.

---

## Phase G — Regression / Synthetic tests

다음 확인:

```text
off ≈ original GP

same seed initial population equality

pathological formula:
raw IC high
but worst effective fitness

normal formula retained

population size remains constant

threshold boundary tests

selection uses effective fitness
```

---

## Phase H — First comparison pilot

동일 조건으로:

```text
gp_original
gplearn_asb hard_penalty
gplearn_asb strict_penalty
```

를 최소 1 seed 실행하세요.

---

# 34. Pilot 결과표

최소 다음을 비교하세요.

```text
method
constraint_mode

population size

best raw train IC
best valid train IC

hard invalid rate
research invalid rate
valid candidate rate

mean signal coverage
median valid n

n_unique formulas
n_unique valid formulas

n_unique parents selected

total evaluations
unique evaluations

final pool size
final pool unique size

OOS IC
OOS RankIC
OOS ICIR

simple backtest Sharpe
CAGR
MDD

Search-QD coverage
NN distance
```

---

# 35. 결과 보고서

다음 파일을 작성하세요.

```text
AlphaSearchBench/gplearn_asb/REPORT.md
```

최소 포함:

## Original equivalence

Validity off에서 original과 얼마나 동일한가.

## Penalty implementation

Worst-fitness 값을 어떻게 정의했는지.

Population size가 보존되는지.

## Validity behavior

Pathological winner가 어떻게 처리되는지.

## Search behavior

Invalid rate와 parent diversity가 generation에 따라 어떻게 변화하는지.

## Pilot comparison

```text
Original
vs
Hard Penalty
vs
Strict Penalty
```

## Limitations

특히:

```text
provisional validity thresholds
single-seed pilot
possible diversity collapse
runtime/cache differences
```

를 명시하세요.

---

# 36. 디렉토리

권장:

```text
AlphaSearchBench/
└── gplearn_asb/
    ├── README.md
    ├── TODO.md
    ├── IMPLEMENTATION_PLAN.md
    ├── REPORT.md
    │
    ├── configs/
    │   ├── default.yaml
    │   ├── smoke.yaml
    │   └── experiments/
    │
    ├── gplearn_asb/
    │   ├── __init__.py
    │   ├── genetic.py
    │   ├── evaluator.py
    │   ├── fitness.py
    │   ├── validity.py
    │   ├── trajectory.py
    │   ├── cache.py
    │   └── cli.py
    │
    ├── tests/
    │   ├── unit/
    │   ├── smoke/
    │   └── regression/
    │
    └── out/
```

구조는 기존 ASB와 자연스럽게 연결되도록 조정할 수 있습니다.

---

# 37. 최종 완료 조건

다음이 모두 충족되어야 합니다.

1. Original GP source 추가 수정 없음
2. 독립 `gplearn_asb` 생성
3. constraint off에서 original equivalence 확인
4. hard penalty 구현
5. strict penalty 구현
6. invalid candidate 삭제 없음
7. population size 고정
8. selection은 effective fitness 사용
9. raw/effective fitness 둘 다 저장
10. train-only validity
11. signed train IC 저장
12. candidate validity diagnostics 저장
13. generation validity statistics 저장
14. parent diversity diagnostics 저장
15. Search-QD-compatible trajectory 저장
16. pathological formula regression 통과
17. normal formula regression 통과
18. threshold boundary tests 통과
19. same-seed initial population 비교
20. Original/Hard/Strict 1-seed pilot 실행
21. AlphaSearchBench OOS/QD/Backtest 연결
22. REPORT.md 작성
23. original source integrity 검사 통과

---

# 작업 시작

먼저:

```text
AlphaSearchBench/gplearn_asb/TODO.md
AlphaSearchBench/gplearn_asb/IMPLEMENTATION_PLAN.md
```

를 만들고 Phase A부터 순차적으로 진행하세요.

각 Phase는:

```text
구현
→ unit/smoke test
→ 실패 수정
→ 결과 기록
→ 다음 Phase
```

순서를 지키세요.

**이번 구현의 기본 constraint handling은 반드시 `worst-fitness penalty`입니다. Invalid candidate를 drop하거나 자동 resample하지 마세요.**

**계획만 작성하고 끝내지 말고 original-equivalent copy → penalty implementation → trajectory logging → 1-seed comparison pilot까지 실제로 수행해주세요.**
