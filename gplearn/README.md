# gplearn (AlphaEval fork)

AlphaEval의 formula alpha mining baseline 중 가장 기본이 되는 구현. 표준 **유전 프로그래밍(Genetic Programming)** 으로 Qlib 표현식 alpha를 탐색한다. README 상단에 언급된 **Random Baseline**도 이 코드로 만든다(→ 1.4절).

- 엔트리포인트: [`../gplearn.py`](../gplearn.py)
- 코드 레벨 상세 분석: [`../docs/AboutGPLearn.md`](../docs/AboutGPLearn.md)
- 이 구현을 계층화한 변형: [`../AutoAlpha/README.md`](../AutoAlpha/README.md)

원본 프로젝트는 Trevor Stephens의 [gplearn](https://github.com/trevorstephens/gplearn)(BSD 3-clause)이며, 이 fork는 **개체의 실행과 적합도를 Qlib 표현식 조회 + IC 계산으로 교체**한 것이다.

---

## 1. 알고리즘

### 1.1 무엇을 탐색하는가

개체(individual)는 **Qlib 표현식 문자열을 만들어내는 트리**다. 내부적으로는 전위(prefix) 리스트로 저장된다.

```
['Div', 'Mean', '$close', 30, '$volume']   →   "Div(Mean($close, 30), $volume)"
```

탐색 공간은 [`config.py`](config.py)가 정의한다.

| 구성요소 | 값 |
| --- | --- |
| feature (터미널) | `$adjclose $amount $change $close $factor $high $low $open $volume $vwap` (10개) |
| 단항 연산자 (arity 1) | `Abs Sign Log` (3개) |
| 이항 연산자 (arity 2) | `Add Sub Mul Div Power Greater Less` (7개) |
| rolling 연산자 (arity 4) | `Ref Mean Sum Std Var Skew Kurt Min Max IdxMin IdxMax Med Mad Delta Slope Rsquare Resi WMA EMA` (19개) |
| rolling window | `[5, 12, 30, 64]` |

> `arity == 4`는 "인자 4개"가 아니라 **rolling 연산자 표식(sentinel)** 이다. 실제로는 `연산자(하위트리, window상수)` 2슬롯이고, 두 번째 인자는 진화 대상이 아니라 위 4개 값 중 하나가 들어간다. 그래서 코드 곳곳에 `2 if functions_arity[node] == 4 else ...` 패턴이 나온다.

초기 개체는 원본 gplearn과 같은 **ramped half-and-half**로 생성된다. 개체마다 `grow`/`full`을 50:50으로 고르고 최대 깊이를 `init_depth=(1,4)` 범위에서 뽑는다.

### 1.2 적합도 = |IC|

```python
raw_fitness = ICBacktester(수식, start, end, instruments, freq).calculate1()
return abs(raw_fitness)
```

([`_program.py:527-554`](_program.py#L527-L554) → [`../backtest/ictester.py:66-82`](../backtest/ictester.py#L66-L82))

1. factor = `D.features([수식])`
2. label = `Ref($close, -1)/$close - 1` (익일 수익률)
3. **날짜별 cross-sectional Pearson 상관**을 구해 시계열 평균 → IC
4. NaN 비율이 50%를 넘으면 `0.0` 반환 (degenerate factor 방어)
5. 절대값을 취한다 → **IC 부호는 무시**된다 (factor에 -1을 곱하면 부호가 뒤집히므로 크기만 본다)

> 중요: [`fitness.py`](fitness.py)의 pearson/spearman/MSE 함수들은 **실제로 호출되지 않는다.** `metric="pearson"`은 `greater_is_better`(argmax 방향)와 `sign`(길이 패널티 부호)만 제공하고, 적합도 수치는 전부 `ICBacktester`가 만든다.

### 1.3 진화 루프

[`genetic.py:290-589`](genetic.py#L290-L589). 표준 GP 루프다.

```
세대 0 : 랜덤 개체 population_size개 생성 → 전부 |IC| 평가
   │
   │ ┌── 세대 g ────────────────────────────────────────────────────┐
   │ │ 개체 하나를 만들 때마다:                                      │
   │ │   ① tournament_size개를 무작위 추출해 최고 적합도 개체를 부모로 │
   │ │   ② 확률에 따라 유전 연산 1개 적용                             │
   │ │   ③ 결과 개체의 |IC| 평가                                     │
   │ │ 이를 population_size번 반복해 세대를 완전히 교체               │
   │ └──────────────────────────────────────────────────────────────┘
   ▼
마지막 세대 → 상위 hall_of_fame개 → 서로 |상관|이 높은 쌍에서 열등한 쪽 제거
            → n_components개 = 최종 alpha pool
```

유전 연산과 기본 확률:

| 연산 | 기본 확률 | 설명 |
| --- | --- | --- |
| Crossover | 0.9 | 부모의 임의 서브트리를 두 번째 토너먼트 승자(donor)의 서브트리로 교체 |
| Subtree Mutation | 0.01 | "headless chicken" — 새 랜덤 트리를 만들어 그 서브트리를 이식 |
| Hoist Mutation | 0.01 | 서브트리 안의 더 작은 서브트리를 끌어올려 대체 (bloat 억제) |
| Point Mutation | 0.01 | 노드 단위 교체. 연산자는 **같은 arity 그룹** 내에서만 교체 |
| Reproduction | 나머지 0.07 | 무변형 복제 |

서브트리 절단점은 **연산자 노드에서만** 고른다 ([`_program.py:576-613`](_program.py#L576-L613), 원본 gplearn의 90:10 가중치와 다름). 잘려나가는 슬라이스가 항상 완결된 서브트리이므로 crossover 결과가 구조적으로 항상 유효하다.

최종 단계의 상관도 제거([`genetic.py:550-580`](genetic.py#L550-L580))가 "서로 중복되지 않는 alpha pool"을 만든다. AlphaEval이 평가하는 **Diversity** 축과 직접 대응되며, 마이닝 단계에서 이미 1차 decorrelation이 적용된 pool이 평가로 넘어간다.

### 1.4 Random Baseline 만들기

세대 0의 population은 진화 없이 순수 랜덤으로 생성된 수식이다. 따라서 **동일한 코드로 `--generations 1`을 주면 Random Baseline**이 된다.

```bash
# GP baseline
python gplearn.py --start_time 2010-01-01 --end_time 2019-12-31 \
                  --population_size 1000 --hall_of_fame 50 --n_components 10 --generations 5

# Random baseline (세대 0만 = 랜덤 수식 풀에서 상위 선별 + 상관도 제거)
python gplearn.py --start_time 2010-01-01 --end_time 2019-12-31 \
                  --population_size 1000 --hall_of_fame 50 --n_components 10 --generations 1
```

두 실행의 유일한 차이가 `--generations`이므로, 같은 평가 예산 안에서 "진화가 랜덤 탐색보다 실제로 나은가"를 그대로 비교할 수 있다.

---

## 2. 실행 방법

### 2.1 사전 준비

```bash
pip install -r ../requirements.txt        # qlib 0.9.0, numpy, pandas, scikit-learn, joblib ...
```

Qlib 데이터는 저장소 루트 README의 `data_collection/fetch_baostock_data.py` 절차를 따른다.

**실행 전 반드시 고쳐야 하는 4곳:**

| # | 위치 | 내용 |
| --- | --- | --- |
| 1 | [`../gplearn.py:11`](../gplearn.py#L11) | `provider_uri="path/to/your/qlib_data"` → 실제 Qlib 데이터 경로 |
| 2 | [`../backtest/ictester.py:10`](../backtest/ictester.py#L10) | 같은 플레이스홀더. **여기를 놓치면 적합도 계산 시점에 깨진다** |
| 3 | [`../gplearn.py:38-55`](../gplearn.py#L38-L55) | **`transformer.fit()` 호출이 빠져 있다.** 아래 참고 |
| 4 | [`../gplearn.py:65`](../gplearn.py#L65) | `to_parquet("your.parquet")` → 원하는 출력 경로 |

`gplearn.py`는 `SymbolicTransformer`를 생성한 직후 `transformer._best_programs`에 접근하는데, 이 속성은 `fit()` 안에서만 설정된다. 따라서 현재 코드를 그대로 실행하면 `AttributeError`가 난다.

```python
transformer = SymbolicTransformer(...)
transformer.fit()                       # ← 이 한 줄을 추가해야 진화가 실행된다
programs = transformer._best_programs
```

### 2.2 실행

**저장소 루트에서** 실행해야 한다 (`_program.py`가 `from backtest.ictester import ICBacktester`를 하기 때문).

```bash
cd /path/to/AlphaEval
python gplearn.py --start_time 2010-01-01 --end_time 2019-12-31 \
                  --population_size 1000 --hall_of_fame 50 \
                  --n_components 10 --generations 5
```

표준출력이 매우 시끄럽다. 개체마다 `executing: <수식>`, `ic: <값>`, `calculating on factor time: ...`이 찍히고 세대마다 전체 적합도 리스트가 출력된다. 로그로 남기고 진행 요약만 보려면 `verbose=1`을 함께 켜는 것이 좋다(→ 3.2절).

```bash
python gplearn.py ... 2>&1 | tee gplearn_run_$(date +%Y%m%d).log
```

산출물: `your.parquet` — 컬럼은 `formula`(Qlib 표현식 문자열), `IC`.

> `parsimony_coefficient=0.0`이므로 저장되는 `IC` 값은 길이 패널티가 없는 `fitness_`, 즉 **정확히 `|IC|`** 다.

### 2.3 산출물 → AlphaEval 평가로 넘기기

```python
import pandas as pd
df = pd.read_parquet("your.parquet")
exprs = df["formula"].tolist()
# 1) backtest/combo.py 의 WeightCalculator 로 결합 weights 산출
# 2) backtest/test.ipynb 처럼 AlphaEval(factor_expressions=exprs, weights=w, ...) 실행
```

---

## 3. 조건을 바꾸는 방법

### 3.1 CLI 인자 (바로 조절 가능)

| 인자 | 기본값 | 의미 | 조절 지침 |
| --- | --- | --- | --- |
| `--start_time` / `--end_time` | 필수 | 마이닝(=in-sample) 구간 | 평가 구간과 겹치지 않게. 저장소 예시는 학습 `2010~2019`, 평가 `2021~2024` |
| `--population_size` | 100 | 세대별 개체 수 | 탐색 폭. 총 비용에 선형으로 영향 |
| `--generations` | 10 | 세대 수 | 탐색 깊이. `1`이면 Random Baseline |
| `--hall_of_fame` | 25 | 상관도 제거 대상 상위 개체 수 | `population_size` 이하. 크게 잡으면 더 다양한 후보에서 고를 수 있지만 마지막에 Qlib 조회가 그만큼 늘어난다 |
| `--n_components` | 10 | 최종 alpha 개수 | `hall_of_fame` 이하 |

### 3.2 `../gplearn.py`를 수정해야 하는 것

`SymbolicTransformer(...)` 인자로 넘기면 된다. **CLI로 노출되어 있지 않은** 주요 손잡이:

| 파라미터 | 기본값 | 효과 |
| --- | --- | --- |
| **`n_jobs`** | 1 | **가장 효과가 큰 손잡이.** 비용의 대부분이 Qlib I/O이므로 `-1`(전 코어) 또는 코어 수를 지정하면 크게 빨라진다. ([`../gplearn.py:2-3`](../gplearn.py#L2-L3)의 주석 처리된 `cpu_count` 오버라이드가 그 시도의 흔적이다) |
| **`verbose`** | 0 | `1`이면 세대별 요약 표(평균 길이/적합도, 최고 적합도, 남은 시간)를 출력한다. `2` 이상은 joblib 진행률까지 |
| **`tournament_size`** | 20 | 선택압. 작은 population에 20을 쓰면 사실상 항상 최상위 개체가 부모가 되어 다양성이 죽는다. `population_size`의 2~5% 정도가 무난하다 |
| **`init_depth`** | `(1, 4)` | 초기 수식 깊이 범위. 넓히면 처음부터 복잡한 수식이 등장한다 |
| **`p_crossover` / `p_subtree_mutation` / `p_hoist_mutation` / `p_point_mutation`** | 0.9 / 0.01 / 0.01 / 0.01 | 합이 1.0 이하여야 하고, 나머지가 reproduction 확률이 된다. 조기 수렴이 문제면 mutation 확률을 올린다 |
| **`p_point_replace`** | 0.05 | point mutation에서 각 노드가 교체될 확률 (4절의 주의사항 참고) |
| **`parsimony_coefficient`** | `../gplearn.py`에서 `0.0` | 키우면 짧은 수식을 선호(bloat 억제). `'auto'`는 세대마다 `Cov(길이, 적합도)/Var(길이)`로 자동 계산 |
| **`init_method`** | `'half and half'` | `'grow'`(비대칭) / `'full'`(빽빽한 트리)로 변경 가능 |
| **`const_range`** | `None` | 튜플을 주면 수식에 숫자 리터럴이 등장한다. `None`이면 상수 없음 |
| **`low_memory`** | `False` | `True`면 이전 세대를 버려 메모리를 절약한다. 큰 population/세대에 유용 |
| **`random_state`** | `../gplearn.py`에서 `42` | 재현성. gplearn fork는 전역 `random`을 쓰지 않으므로 이 값만으로 재현된다 |

그 밖에 `qlib_config` 딕셔너리에서 바꾸는 것:

| 무엇 | 위치 |
| --- | --- |
| 종목 유니버스 | [`../gplearn.py:31`](../gplearn.py#L31) `D.instruments(market="all")` → `market="csi300"` 등 |
| 데이터 주기 | [`../gplearn.py:34`](../gplearn.py#L34) `"freq": "day"` |
| 사용 연산자 부분집합 | [`../gplearn.py:43`](../gplearn.py#L43) `function_set=functions_arity.keys()` → `["Add","Sub","Mean","Std"]`처럼 리스트로 직접 전달 |

### 3.3 `config.py`를 수정해야 하는 것 (탐색 공간 자체)

| 무엇 | 방법 |
| --- | --- |
| **입력 feature** | `FEATURE_LIST`에 Qlib 필드 추가/삭제. `gplearn.py`가 그대로 `feature_names`로 넘기므로 자동 반영된다 |
| **rolling window 후보** | `window_lengths = [5, 12, 30, 64]` 수정 |
| **연산자 추가** | `functions_arity`에 `"이름": arity` 추가. rolling 계열은 반드시 `4`로 등록해야 `(하위트리, window)` 규약을 탄다 |
| **주석 처리된 연산자** | `Not`, `And`, `Or`, `Cov`, `Corr`, `Quantile`이 비활성 상태다. `Cov`/`Corr`는 `(시계열, 시계열, window)` 3인자라 현재 arity 규약으로 표현되지 않으므로, 살리려면 `_program.py`의 트리 조립 로직을 함께 고쳐야 한다 |

### 3.4 효과가 없거나 오해하기 쉬운 파라미터 (함정)

- **`metric`** — `'pearson'` / `'spearman'` 중에서만 고를 수 있지만, 실제 적합도 수치에는 영향이 없다(1.2절). 단 `'spearman'`으로 두면 **마지막 상관도 제거 단계에서** factor 값을 rank로 변환해 비교한다([`genetic.py:560-561`](genetic.py#L560-L561)) — 그 부분만 달라진다.
- **`stopping_criteria`** — `SymbolicTransformer` 기본값이 1.0이므로 `|IC| ≥ 1.0`이어야 조기 종료한다. 실질적으로 항상 `generations`만큼 돈다. 조기 종료를 쓰려면 예: `stopping_criteria=0.1`.
- **`max_samples` / `sample_weight`** — 적합도 계산이 `sample_weight`를 무시하므로 서브샘플링과 OOB 적합도가 무력화되어 있다. `max_samples < 1.0`으로 두면 in-sample과 OOB가 같은 값이 나오고 평가 횟수만 2배가 된다.
- **`transformer`** — `SymbolicClassifier`용 잔여 파라미터다. 이 fork에는 분류기가 없다.

### 3.5 비용 계산 (실행 전 꼭 확인)

```
총 IC 계산 횟수 ≈ generations × population_size   (+ 마지막에 hall_of_fame회 추가 조회)
```

각 IC 계산이 Qlib 조회를 2~3회 유발한다(`execute`에서 1회, `ICBacktester`에서 factor·label 각 1회).

| 설정 | 총 IC 계산 |
| --- | --- |
| `pop=100, gens=10` (`gplearn.py` 기본값) | 1,000 |
| `pop=1000, gens=5` (루트 README 예시) | **5,000** |
| `pop=1000, gens=1` (Random Baseline) | 1,000 |

처음에는 `--population_size 50 --generations 2` 정도로 파이프라인이 끝까지 도는지 확인한 뒤 규모를 올리는 것을 권한다. 그리고 규모를 올릴 때는 `n_jobs`를 먼저 올려야 한다.

---

## 4. 알려진 문제

> 아래는 코드를 읽고 확인한 사항이다. 이 문서는 코드를 수정하지 않는다. 근거는 [`../docs/AboutGPLearn.md`](../docs/AboutGPLearn.md) 4절에 정리해 두었다.

- **`fit()` 호출 누락** — 2.1절 참고. 현재 `gplearn.py`를 그대로 실행하면 `AttributeError`다.
- **point mutation이 feature를 숫자로 바꿔 버린다** ([`_program.py:741-753`](_program.py#L741-L753)) — `build_program`은 `self.feature_names[terminal]`로 `"$close"`를 넣는데, point mutation은 `random_state.randint(self.n_features)`가 만든 **정수 인덱스를 그대로 대입**한다. 그 결과 `Add($close, 3)`처럼 feature가 숫자 리터럴로 바뀐 수식이 생긴다. 또 이 분기는 rolling 연산자의 **window 슬롯도 교체 대상**으로 보므로 `[5,12,30,64]` 밖의 window(0~9)가 나올 수 있다. Qlib 파싱은 되므로 크래시는 없고 적합도로만 걸러진다. `p_point_mutation=0.01`이라 영향 범위는 작지만, mutation 확률을 올릴 때는 이 동작을 감안해야 한다.
- **실패한 수식이 조용히 `$close`로 대체된다** ([`_program.py:463`](_program.py#L463), [`../backtest/ictester.py:50`](../backtest/ictester.py#L50)) — 로버스트하지만 실제 파싱 실패율이 감춰진다. 로그의 `"... can not be executed."` 줄 수를 세어 보면 확인할 수 있다.
- **label 데이터를 개체마다 다시 조회한다** — `ICBacktester.__init__`이 매번 label을 새로 받아온다. label은 불변이므로 캐싱하면 조회량이 크게 줄어든다.
- **`__all__`과 실제 구현 불일치** — [`genetic.py:34`](genetic.py#L34)의 `__all__`은 `SymbolicRegressor`, `SymbolicClassifier`를 포함하지만 이 fork에는 `SymbolicTransformer`만 정의되어 있다. 나머지를 import하면 실패한다.
- **[`functions.py`](functions.py)는 거의 죽은 코드다** — 연산자가 Qlib 문자열로 대체되었으므로 `_function_map`은 프로그램 생성에 쓰이지 않는다. `genetic.py`가 실제로 쓰는 것은 `_Function`(타입 체크)과 `sig1`(`transformer` 파라미터용)뿐이다.
- **`qlib.init()`은 `gplearn.genetic` import보다 먼저** 호출해야 한다. `qlib_config` 기본 인자값이 모듈 import 시점에 `D.instruments(market="all")`를 평가하기 때문이다. `gplearn.py`의 import 순서가 그래서 그렇게 되어 있다.
- **`transform1()` / `fit_transform1()`** — 원본 gplearn의 `transform`/`fit_transform`이 이름과 시그니처가 바뀌었다(`X` 인자 없음). `fit()`도 `fit(sample_weight=None)`이다. 즉 **scikit-learn 파이프라인에 그대로 끼울 수 없다.**

---

## 5. 디렉토리 구성

| 파일 | 역할 |
| --- | --- |
| [`config.py`](config.py) | **탐색 공간 정의** — feature 10개, 연산자 29개, rolling window 4개 |
| [`_program.py`](_program.py) | **개체 표현** — 트리 생성, Qlib 표현식 문자열 조립, 실행, 적합도, crossover/mutation |
| [`genetic.py`](genetic.py) | **진화 루프** — `SymbolicTransformer`, 세대별 병렬 개체 생성(`_parallel_evolve`), 최종 상관도 제거 |
| [`fitness.py`](fitness.py) | 원본 gplearn의 적합도 메트릭 모음 (이 fork에서는 `greater_is_better` 플래그 용도) |
| [`functions.py`](functions.py) | 원본 gplearn의 numpy 연산자 노드 (대부분 미사용) |
| [`utils.py`](utils.py) | scikit-learn 유틸 복사본 (`check_random_state`, `_partition_estimators`) |

원본 gplearn과의 차이 요약은 [`../docs/AboutGPLearn.md`](../docs/AboutGPLearn.md) 3절 표에 정리되어 있다.

라이선스: 원본 gplearn(BSD 3-clause) 기반. 저장소 루트 `LICENSE` 참고.
