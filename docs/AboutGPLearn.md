# AboutGPLearn — AlphaEval의 gplearn 기반 Formula Alpha 마이닝

이 문서는 AlphaEval 저장소의 `gplearn.py` 및 `gplearn/` 패키지가 **어떻게 동작하는지**를 코드 레벨에서 설명한다.

---

## 0. AlphaEval 전체 구조에서의 위치

AlphaEval은 논문 *"AlphaEval: A Comprehensive and Efficient Evaluation Framework for Formula Alpha Mining"* 의 공식 구현이며, 크게 두 부분으로 나뉜다.

1. **Factor Mining Models** — 평가 대상이 되는 alpha 마이닝 알고리즘들 (gplearn, AutoAlpha, AlphaEvolve, Fama, AlphaAgent, AlphaGen, AlphaForge, AlphaQCM)
2. **AlphaEval Evaluation Framework** — `backtest/modeltester`에 있는 통합 평가 프레임워크

전체 파이프라인은 다음과 같다.

```
Qlib Market Data
      │
      ▼
[Factor Mining Algorithm]   ← 이 문서의 대상: gplearn (Genetic Programming)
      │  formula 문자열들 (예: "Div(Mean($close, 30), $volume)")
      ▼
Generated Formula Alpha Pool  (your.parquet: {formula, IC})
      │
      ▼
[AlphaEval Evaluation]  (backtest/modeltester)
      │
      ▼
mining method 간 성능 · alpha pool 특성 비교
```

즉 `gplearn.py`는 **파이프라인의 1단계(생성기)** 이고, 산출물은 "Qlib 표현식 문자열 + 그 IC"의 테이블이다. 이 산출물이 그대로 AlphaEval 평가 단계의 입력이 된다.

또한 README가 gplearn을 *"including Random Baseline"* 이라고 표기하는 이유도 구조상 명확하다. 세대 0(gen 0)의 population은 진화 없이 순수 랜덤으로 생성된 수식이므로, `--generations 1`로 돌리면 동일한 코드가 곧 **Random Baseline**이 된다. 진화를 켜면 GP 베이스라인, 세대 0에서 멈추면 랜덤 베이스라인이다.

---

## 1. 파일별 역할

| 파일 | 역할 |
| --- | --- |
| [`gplearn.py`](../gplearn.py) | 엔트리포인트. Qlib 초기화 → `SymbolicTransformer` 구성 → 결과를 parquet으로 저장 |
| [`gplearn/config.py`](../gplearn/config.py) | **탐색 공간 정의**. 사용할 Qlib 연산자(`functions_arity`), 입력 feature(`FEATURE_LIST`), rolling window 후보(`window_lengths`) |
| [`gplearn/_program.py`](../gplearn/_program.py) | **개체(individual) 표현**. 트리 생성/문자열화/실행/적합도, 그리고 crossover·3종 mutation |
| [`gplearn/genetic.py`](../gplearn/genetic.py) | **진화 루프**. `SymbolicTransformer`(sklearn 스타일 estimator)와 세대별 병렬 개체 생성 `_parallel_evolve` |
| [`gplearn/fitness.py`](../gplearn/fitness.py) | 원본 gplearn의 적합도 메트릭 모음. **이 fork에서는 사실상 `greater_is_better` 플래그 용도로만 쓰인다** (2.5절 참고) |
| [`gplearn/functions.py`](../gplearn/functions.py) | 원본 gplearn의 numpy 연산자 노드(`add`, `sub`, …). **연산자가 Qlib 문자열로 대체되었기 때문에 대부분 미사용(vestigial)** |
| [`gplearn/utils.py`](../gplearn/utils.py) | scikit-learn 유틸 복사본 (`check_random_state`, `_partition_estimators`) |
| [`backtest/ictester.py`](../backtest/ictester.py) | 적합도의 실제 계산 주체. 수식 문자열 → Qlib 조회 → 일별 cross-sectional IC 평균 |

원본 gplearn과 가장 크게 달라진 점은 **개체가 numpy 함수 트리가 아니라 "Qlib 표현식 문자열을 만들어내는 트리"** 라는 것이다. 개체의 평가는 numpy 연산이 아니라 **Qlib에 표현식을 던져 데이터를 받아오는 것**으로 이루어진다.

---

## 2. 동작 원리

### 2.1 탐색 공간 (`config.py`)

```python
window_lengths = [5, 12, 30, 64]
FEATURE_LIST = ["$adjclose", "$amount", "$change", "$close", "$factor",
                "$high", "$low", "$open", "$volume", "$vwap"]
functions_arity = { "Abs": 1, ..., "Add": 2, ..., "Ref": 4, "Mean": 4, ... }
```

- **터미널(잎)**: Qlib 필드명 10개
- **연산자**: 총 29개
  - `arity == 1` (3개): `Abs`, `Sign`, `Log`
  - `arity == 2` (7개): `Add`, `Sub`, `Mul`, `Div`, `Power`, `Greater`, `Less`
  - `arity == 4` (19개): `Ref`, `Mean`, `Sum`, `Std`, `Var`, `Skew`, `Kurt`, `Min`, `Max`, `IdxMin`, `IdxMax`, `Med`, `Mad`, `Delta`, `Slope`, `Rsquare`, `Resi`, `WMA`, `EMA`
- 주석 처리된 연산자(`Not`, `And`, `Or`, `Cov`, `Corr`, `Quantile`)는 탐색 공간에서 제외되어 있다. `Cov`/`Corr`는 인자가 2개의 시계열 + window라 아래의 arity 규약으로 표현되지 않기 때문이다.

> **`arity == 4`의 의미 (이 fork의 핵심 관용구)**
> 4는 "인자 4개"가 아니라 **rolling 연산자 표식(sentinel)** 이다. 실제로는
> `연산자(하위트리 1개, window_lengths에서 뽑은 정수 1개)` — 즉 **유효 arity는 2**이며,
> 두 번째 인자는 진화 대상 하위트리가 아니라 `[5, 12, 30, 64]`에서 뽑힌 상수다.
> 그래서 코드 전반에 `2 if functions_arity[node] == 4 else functions_arity[node]` 패턴이 반복된다
> ([`_program.py:277`](../gplearn/_program.py#L277), [`:419`](../gplearn/_program.py#L419), [`:379`](../gplearn/_program.py#L379), [`:608`](../gplearn/_program.py#L608)).
> 덕분에 window가 임의 수식으로 오염되지 않고 항상 유효한 정수 window가 보장된다.

### 2.2 개체 표현: flattened prefix(전위) 리스트

개체는 트리를 전위 순회로 펼친 **파이썬 리스트** 하나다 ([`_program.py:176-251`](../gplearn/_program.py#L176-L251)).

```python
['Div', 'Mean', '$close', 30, '$volume']
        └── Div( Mean($close, 30), $volume )
```

- 연산자 = `functions_arity`에 있는 문자열
- feature = `$`로 시작하는 문자열
- window = 정수

`build_program`은 `terminal_stack`으로 "각 노드가 아직 채워야 하는 슬롯 수"를 추적하며 트리를 자란다. 여기서 arity=4 규약이 다음과 같이 처리된다 ([`_program.py:237-248`](../gplearn/_program.py#L237-L248)).

```python
terminal_stack[-1] -= 1
while terminal_stack[-1] == 0 or terminal_stack[-1] == 3:
    if terminal_stack[-1] == 0:
        terminal_stack.pop()            # 노드 완성
    else:                               # 4 → 3 : rolling 연산자의 window 슬롯
        program.append(random.choice(window_lengths))
        terminal_stack.pop()
    ...
```

rolling 노드는 카운터 4로 시작하고, 하위트리 하나가 완성되면 3이 되어 **즉시 window 상수를 붙이고 닫힌다**. 카운터가 3이 되는 경우는 rolling 노드밖에 없으므로 이 분기는 안전하다. 같은 논리가 `validate_program`에서는 `== 2` 체크로 나타난다(그쪽은 window 정수까지 리스트에서 소비한 뒤 검사하므로 4→3→2) ([`_program.py:253-264`](../gplearn/_program.py#L253-L264)).

초기화 방식은 원본 gplearn과 동일한 **ramped half-and-half**: `init_method='half and half'`이면 개체마다 `grow`/`full`을 50:50으로 선택하고, `max_depth`를 `init_depth=(1,4)` 범위(실제로는 1~4)에서 뽑는다.

### 2.3 트리 → Qlib 표현식 문자열

`__str__`([`:266`](../gplearn/_program.py#L266))과 `execute`([`:395`](../gplearn/_program.py#L395))는 동일한 스택 알고리즘으로 전위 리스트를 중위 표기 문자열로 조립한다. 슬롯이 하나 남으면 `", "`, 다 채워지면 `")"`를 붙이는 방식이다.

`['Div', 'Mean', '$close', 30, '$volume']`의 조립 과정:

| 처리한 노드 | 처리 후 `apply_stack` | 누적 `expression` |
| --- | --- | --- |
| `Div` | `[2]` | `Div(` |
| `Mean` (4→2로 환산) | `[2, 2]` | `Div(Mean(` |
| `$close` | `[2, 1]` | `Div(Mean($close, ` |
| `30` | `[1]` (Mean 닫고 pop) | `Div(Mean($close, 30), ` |
| `$volume` | `[]` (Div 닫고 pop) | `Div(Mean($close, 30), $volume)` |

이 문자열이 그대로 **Qlib expression engine에 넘어가는 최종 alpha 수식**이다. 그래서 이 프로젝트의 alpha는 별도 파서 없이 Qlib으로 재현·평가할 수 있고, AlphaEval 평가 단계와 자연스럽게 연결된다.

### 2.4 개체 실행 (`execute`)

```python
data = D.features(instruments, [expression], start_time, end_time, freq)
return data.squeeze().to_numpy()
```

- Qlib에서 (instrument × datetime) 패널을 받아 1차원으로 flatten 한다.
- 표현식이 Qlib에서 실패하면 **예외를 삼키고 `$close`로 대체**한다 ([`_program.py:463-471`](../gplearn/_program.py#L463-L471)). 즉 잘못된 수식은 크래시 대신 "close 가격"이라는 무의미한 factor로 취급되어 낮은 적합도를 받고 자연 도태된다.
- 여기에는 진짜 `X` 행렬이 없다. `X_shape = (len(y), len(FEATURE_LIST))`로 형태만 유지되고, `n_features`는 터미널을 랜덤 추출할 때의 인덱스 범위로만 쓰인다.

### 2.5 적합도 = |IC| (가장 중요한 개조 지점)

```python
def raw_fitness(self, X_shape, y, sample_weight):
    y_pred = self.execute(X_shape)                     # 길이 검증용으로만 사용
    if len(y) != len(y_pred): raise ValueError(...)
    raw_fitness = ICBacktester(self.__str__(), start, end, instruments, freq).calculate1()
    return abs(raw_fitness)
```

([`_program.py:527-554`](../gplearn/_program.py#L527-L554))

`ICBacktester.calculate1()`([`ictester.py:66-82`](../backtest/ictester.py#L66-L82))이 하는 일:

1. factor 데이터 = `D.features([수식])`
2. label 데이터 = `Ref($close, -1)/$close - 1` (익일 수익률)
3. inner join + dropna 후, **날짜별로 cross-sectional Pearson 상관** 계산
4. NaN 비율이 50%를 넘으면 `0.0` 반환 (degenerate factor 방어)
5. 아니면 일별 IC의 **시계열 평균**을 반환

그리고 `raw_fitness`는 `abs()`를 취한다 → **IC의 부호는 무시**된다. factor에 -1을 곱하면 부호가 뒤집히므로 예측력의 크기만 보는 것이 타당한 선택이다.

여기서 반드시 짚어야 할 두 가지:

- **`fitness.py`의 메트릭 함수들은 실제로 호출되지 않는다.** `metric="pearson"`은 `_fitness_map`을 통해 `_Fitness` 객체로 변환되지만, 이 객체는 `greater_is_better`(argmax 방향)와 `sign`(parsimony 패널티 부호)에만 쓰인다. 실제 적합도 수치는 전부 `ICBacktester`가 만든다.
- **`sample_weight` / `max_samples` / OOB는 무력화되어 있다.** `raw_fitness`가 `sample_weight`를 무시하므로, 서브샘플링을 켜도 in-sample과 OOB 적합도가 같은 값이 된다. 기본값 `max_samples=1.0`에서는 OOB 계산 자체가 생략된다.

또한 **한 개체를 평가할 때 Qlib 조회가 2회 이상 발생**한다 (`execute`에서 1회, `ICBacktester.__init__`에서 factor·label 각 1회). 이 부분이 런타임의 지배적 비용이며, `genetic.py:149-152`가 개체별 소요 시간을 출력하는 이유이기도 하다.

### 2.6 진화 루프 (`BaseSymbolic.fit`)

[`genetic.py:290-589`](../gplearn/genetic.py#L290-L589). 표준 GP 루프이며, 정답 label `y`는 estimator 생성 시 한 번만 계산해 둔다 ([`:235-243`](../gplearn/genetic.py#L235-L243)).

```python
y = D.features(instruments, ["(Ref($close, -1) - $close) / $close"], ...)
```

(= `ICBacktester`의 label과 동일한 익일 수익률)

세대별 흐름:

```
for gen in range(generations):
    parents = None (gen 0) 또는 이전 세대 population
    seeds = random_state.randint(...)              # 개체별 재현성 보장
    population = Parallel(n_jobs)(_parallel_evolve(...))   # 개체 생성 + 적합도 평가
    fitness_ = raw_fitness_ - parsimony_coefficient * len(program) * sign
    self._programs.append(population)
    조상 pruning (low_memory=False면 미사용 부모를 None으로)
    run_details_ 기록 / best_fitness >= stopping_criteria 면 early stop
```

`_parallel_evolve`([`genetic.py:39-159`](../gplearn/genetic.py#L39-L159))에서 개체 하나가 만들어지는 과정:

1. **선택**: `_tournament()` — population에서 `tournament_size=20`개를 무작위 추출해 `fitness_`가 가장 좋은 개체를 부모로 채택
2. **유전 연산**: `random_state.uniform()`을 누적확률 `method_probs`와 비교해 하나를 선택
   | 연산 | 기본 확률 | 설명 |
   | --- | --- | --- |
   | Crossover | 0.9 | 부모의 임의 서브트리를 두 번째 토너먼트 승자(donor)의 서브트리로 교체 |
   | Subtree Mutation | 0.01 | "headless chicken" — 새 랜덤 트리를 만들어 그 서브트리를 이식 |
   | Hoist Mutation | 0.01 | 서브트리 안의 더 작은 서브트리를 끌어올려 대체 (bloat 억제) |
   | Point Mutation | 0.01 | 노드 단위 교체. 연산자는 **같은 arity 그룹** 내에서 교체 |
   | Reproduction | 나머지 0.07 | 무변형 복제 |
3. **적합도 평가**: `program.raw_fitness_ = program.raw_fitness(...)` → 2.5절의 Qlib IC

`get_subtree`([`_program.py:576-613`](../gplearn/_program.py#L576-L613))는 원본 gplearn의 90:10 가중치 대신 **연산자 노드에만 확률을 부여**한다. 따라서 절단점이 항상 연산자이고, 잘려나가는 슬라이스는 항상 완결된 서브트리다 → **crossover 결과가 구조적으로 항상 유효**하다. window 정수는 상위 rolling 노드의 슬롯으로 카운트되므로 서브트리에 함께 실려 간다.

### 2.7 최종 선택: hall_of_fame → 상관도 제거 → n_components

`SymbolicTransformer`(= `TransformerMixin`) 경로 ([`genetic.py:550-580`](../gplearn/genetic.py#L550-L580)):

1. 마지막 세대에서 적합도 상위 `hall_of_fame`개를 뽑는다
2. 각 개체를 `execute`해 factor 값 행렬을 만든다 (여기서도 Qlib 조회가 개체당 1회 더 발생)
3. 개체 간 `|corrcoef|` 행렬을 계산하고 대각을 0으로 만든다
4. **가장 상관이 높은 쌍에서 적합도가 낮은 쪽을 제거**하는 과정을 `n_components`개가 남을 때까지 반복
5. 결과가 `self._best_programs`

이것이 gplearn 계열이 "서로 중복되지 않는 alpha pool"을 만드는 방식이며, AlphaEval이 평가하는 **Diversity** 축과 직접 대응된다. 즉 mining 단계에서 이미 1차 decorrelation이 적용된 pool이 평가 단계로 넘어간다.

### 2.8 엔트리포인트 (`gplearn.py`)

```python
qlib.init(provider_uri="path/to/your/qlib_data", region="cn")   # 반드시 import보다 먼저
from gplearn.genetic import SymbolicTransformer
from gplearn.config import functions_arity, FEATURE_LIST

qlib_config = {"data_client": D, "instruments": D.instruments(market="all"),
               "start_time": args.start_time, "end_time": args.end_time, "freq": "day"}

transformer = SymbolicTransformer(
    population_size=..., hall_of_fame=..., n_components=..., generations=...,
    function_set=functions_arity.keys(),
    metric="pearson", parsimony_coefficient=0.0,
    qlib_config=qlib_config, feature_names=FEATURE_LIST, random_state=42)

records = [{"formula": str(prog), "IC": prog.fitness_} for prog in transformer._best_programs]
pd.DataFrame(records).to_parquet("your.parquet")
```

- `qlib.init()`이 import보다 먼저 오는 것은 실수가 아니다. `genetic.py`/`_program.py`의 `qlib_config` **기본 인자값이 모듈 import 시점에 `D.instruments(market="all")`를 평가**하기 때문이다. 순서를 바꾸면 import 단계에서 깨진다.
- `parsimony_coefficient=0.0` → 길이 패널티 없음 → `fitness_ == raw_fitness_ == |IC|`. 따라서 저장되는 `IC` 컬럼은 **정확히는 |IC|** 이다.
- `market="all"` 전체 종목을 쓰므로 `ICBacktester`의 CSI300 기본값 경로는 타지 않는다.
- 출력은 `{formula, IC}` 두 컬럼의 parquet — 이것이 AlphaEval 평가 단계(`backtest/modeltester`, `backtest/test.ipynb`)의 입력이다.

---

## 3. 원본 gplearn과의 차이 요약

| 항목 | 원본 gplearn | AlphaEval fork |
| --- | --- | --- |
| 연산자 | numpy 함수 객체 (`_Function`) | **Qlib 연산자 문자열** (`config.functions_arity`) |
| 터미널 | `X`의 컬럼 인덱스 + 상수 | **Qlib 필드명 문자열** + rolling window 상수 |
| 개체 평가 | 메모리상 numpy 트리 실행 | **Qlib expression engine 조회** |
| 적합도 | `fitness.py`의 pearson/spearman/MSE 등 | **일별 cross-sectional IC의 평균의 절대값** (`ICBacktester.calculate1`) |
| rolling window | 없음 | `arity=4` 규약으로 `[5,12,30,64]`에서 추출 |
| `fit()` 시그니처 | `fit(X, y)` | `fit(sample_weight=None)` — 데이터는 `qlib_config`에서 옴 |
| `transform` | `transform(X)` | `transform1()` / `fit_transform1()` |
| 서브트리 선택 | 연산자 90% / 터미널 10% | **연산자 100%** |
| 제공 estimator | Regressor / Classifier / Transformer | **`SymbolicTransformer`만 구현** |

---

## 4. 실행 시 알아야 할 것

### 4.1 실행 전 수정이 필요한 부분

1. **Qlib 데이터 경로**: `path/to/your/qlib_data` 플레이스홀더를 **두 곳** 모두 바꿔야 한다 — [`gplearn.py:11`](../gplearn.py#L11) 과 [`backtest/ictester.py:10`](../backtest/ictester.py#L10). 후자를 놓치면 적합도 계산 시점에 깨진다.
2. **`fit()` 호출 누락**: 현재 [`gplearn.py`](../gplearn.py)는 `SymbolicTransformer`를 생성한 뒤 곧바로 `transformer._best_programs`에 접근한다. `_best_programs`는 `fit()` 안에서만 설정되므로 **그대로 실행하면 `AttributeError`가 난다.** 진화를 실행하려면 생성 직후 학습을 호출해야 한다.

   ```python
   transformer = SymbolicTransformer(...)
   transformer.fit()              # ← 필요
   programs = transformer._best_programs
   ```
3. **출력 경로**: `to_parquet("your.parquet")`도 플레이스홀더다.
4. **실행 위치**: `_program.py`가 `from backtest.ictester import ICBacktester`를 하므로 **저장소 루트에서 실행**해야 한다.

### 4.2 성능 관련

- `n_jobs`가 기본값 `1`이고 `gplearn.py`가 이를 지정하지 않으므로 **완전 직렬 실행**이다. 비용의 대부분이 Qlib I/O이므로 `n_jobs`를 올리는 것이 가장 효과가 크다 (`gplearn.py:2-3`의 주석 처리된 `cpu_count` 오버라이드가 그 시도의 흔적이다).
- 총 평가 횟수 ≈ `population_size × generations`. README 예시(`1000 × 5`)면 5,000개 수식 × 각 2~3회 Qlib 조회다.
- `ICBacktester`는 개체마다 **label 데이터를 새로 조회**한다. label은 불변이므로 캐싱하면 조회량이 크게 줄어든다.
- `stopping_criteria`는 `SymbolicTransformer` 기본값이 `1.0`이라 `|IC| >= 1.0`이 되어야 early stop한다 — 실질적으로 발생하지 않으므로 항상 `generations`만큼 돈다.

### 4.3 코드상 주의할 동작

- **point mutation의 터미널 교체가 feature 이름이 아니라 정수 인덱스를 넣는다** ([`_program.py:741-753`](../gplearn/_program.py#L741-L753)). `build_program`은 `self.feature_names[terminal]`로 `"$close"`를 넣지만, point mutation은 `random_state.randint(self.n_features)`가 만든 정수를 그대로 대입한다. 그 결과 `Add($close, 3)`처럼 feature가 숫자 리터럴로 바뀐 수식이 생성된다. 또 이 분기는 rolling 노드의 **window 슬롯도 교체 대상**으로 보기 때문에 `[5,12,30,64]` 밖의 window(0~9)가 나올 수 있다. Qlib에서 파싱은 되므로 크래시는 없고 적합도로만 걸러진다 — 다만 point mutation이 의도한 "터미널 → 다른 터미널" 교체보다 훨씬 파괴적으로 동작한다는 뜻이다. `p_point_mutation=0.01`이라 영향 범위는 작다.
- **`__all__`과 실제 구현 불일치**: `genetic.py`의 `__all__`은 `SymbolicRegressor`, `SymbolicClassifier`를 포함하지만 이 fork에는 `SymbolicTransformer`만 정의되어 있다. 나머지를 import하면 실패한다.
- **`functions.py`는 거의 죽은 코드**다. `_function_map`은 프로그램 생성에 쓰이지 않고, `genetic.py`가 가져가는 것은 `_Function`(타입 체크)과 `sig1`(`transformer` 파라미터용)뿐이다.
- **실패한 수식이 조용히 `$close`로 대체**된다 ([`_program.py:463`](../gplearn/_program.py#L463), [`ictester.py:50`](../backtest/ictester.py#L50)). 로버스트하지만, 얼마나 많은 후보가 실제로 파싱 실패했는지는 로그(`"... can not be executed."`)를 세어봐야 알 수 있다.

---

## 5. 한 장 요약

```
config.py           탐색 공간: Qlib 필드 10개 · 연산자 29개 · window {5,12,30,64}
   │
_program.py         개체 = 전위 리스트 ['Div','Mean','$close',30,'$volume']
   │  build_program   ramped half-and-half로 랜덤 트리 생성 (arity=4 → rolling+window)
   │  __str__         → "Div(Mean($close, 30), $volume)"  ← 최종 alpha 수식
   │  raw_fitness     → ICBacktester.calculate1() → |일별 cross-sectional IC 평균|
   │
genetic.py          세대 루프: tournament(20) 선택
   │                 → crossover .9 / subtree .01 / hoist .01 / point .01 / reproduce .07
   │                 → 적합도 평가 → 다음 세대
   │  fit() 말미      hall_of_fame 상위 → |상관| 높은 쌍에서 열등한 쪽 제거 → n_components
   │
gplearn.py          _best_programs → {formula, IC} DataFrame → parquet
   │
backtest/modeltester   AlphaEval 평가 (predictive power / stability / robustness / diversity ...)
```

핵심 문장 하나로 줄이면: **이 fork는 gplearn의 GP 엔진(트리 표현·토너먼트 선택·crossover/mutation·hall of fame decorrelation)을 그대로 쓰면서, 개체의 "실행"과 "적합도"만 Qlib 표현식 조회와 IC 계산으로 갈아끼운 것**이다.
