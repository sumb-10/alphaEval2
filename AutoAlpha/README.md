# AutoAlpha

AlphaEval의 formula alpha mining baseline 중 하나. **depth를 한 층씩 키워 가는 계층적(hierarchical / coarse-to-fine) 유전 프로그래밍**으로 Qlib 표현식 alpha를 탐색한다.

- 엔트리포인트: [`../autoalpha.py`](../autoalpha.py)
- 코드 레벨 상세 분석: [`../docs/AboutAutoAlpha.md`](../docs/AboutAutoAlpha.md)
- 기반이 되는 gplearn fork 설명: [`../docs/AboutGPLearn.md`](../docs/AboutGPLearn.md)

원 논문: Zhang et al., *AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment*.

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

> `arity == 4`는 "인자 4개"가 아니라 **rolling 연산자 표식**이다. 실제로는 `연산자(하위트리, window상수)` 2슬롯이며, window는 항상 위 4개 값 중 하나가 들어간다.

**적합도(fitness) = `abs(일별 cross-sectional IC의 평균)`**. [`../backtest/ictester.py`](../backtest/ictester.py)의 `ICBacktester.calculate1()`이 계산한다. label은 익일 수익률 `Ref($close, -1)/$close - 1`이다. 부호는 무시하므로(절대값) IC가 음수인 factor도 동등하게 평가된다.

### 1.2 세대 = depth 레벨

일반적인 GP처럼 임의 깊이 트리를 섞는 대신, **얕은 수식에서 시작해 세대마다 깊이를 정확히 1씩 올린다.**

```
seed :  depth-1 수식 population_size개          예) Mean($close, 30), Add($high, $low)
  │
  │ ┌── Generation g ────────────────────────────────────────────────────┐
  │ │ ① Growth                                                          │
  │ │    depth_evolution: 새 루트 연산자를 하나 씌워 depth를 +1          │
  │ │      단항 f  →  [f] + 자기                                         │
  │ │      이항 f  →  [f] + 자기 + 파트너      (파트너는 균등 랜덤)      │
  │ │    후보 growth_k × population_size개 생성 → 전부 IC 평가           │
  │ │    → 정렬 후 상위 population_size개만 생존 (truncation selection)  │
  │ │                                                                    │
  │ │ ② Evolve                                                          │
  │ │    tournament로 부모·기증자 선택 (둘은 depth가 같아야 함)          │
  │ │    특정 depth 레벨을 골라 그 층의 서브트리를 교환 → 자녀 2개        │
  │ │    max(자녀 IC) > max(부모 IC) 일 때만 두 슬롯을 자녀로 교체        │
  │ └────────────────────────────────────────────────────────────────────┘
  │        depth 1 → 2 → 3 → ... 
  ▼
마지막 세대 → 상위 hall_of_fame개 → 서로 |상관|이 높은 쌍에서 열등한 쪽 제거
            → n_components개 = 최종 alpha pool
```

**최종 트리 depth = `generations` + 1.**

핵심 설계 포인트 3가지:

1. **mutation이 없다.** gplearn fork의 subtree/hoist/point mutation은 전부 삭제되었고, 변형 수단은 `depth_evolution`(성장)과 같은 층 crossover(교환) 둘뿐이다.
2. **같은 depth끼리만 교배한다.** 덕분에 세대 내 depth가 균일하게 유지되어 "이번 세대는 depth d를 탐색한다"는 계층 구조가 성립한다.
3. **rolling 연산자는 새 루트가 될 수 없다.** → 생성되는 트리에서 `Mean`, `Std` 같은 rolling 연산자는 **최하단 시드 층에만** 존재하고 그 위는 전부 산술/논리 연산자다. `Mean(Add($close, $open), 30)` 같은 "복합식의 이동평균"은 이 구현으로는 나오지 않는다.

### 1.3 gplearn baseline과의 차이 한눈에

| | gplearn | **AutoAlpha** |
| --- | --- | --- |
| 초기 depth | `(1,4)` ramped half-and-half | **1 고정** |
| depth 변화 | 자유 | **세대마다 +1** |
| 변형 연산 | crossover + mutation 3종 + reproduction | **crossover만** + `depth_evolution` |
| crossover 제약 | 없음 | **동일 depth · 동일 레벨** |
| 자녀 수 | 1 | **2** |
| 세대 교체 | 전면 교체 | **개선될 때만 교체(탐욕적)** |
| 세대당 평가 | `population_size` | `population_size × (growth_k + 2)` |

---

## 2. 실행 방법

### 2.1 사전 준비

```bash
pip install -r ../requirements.txt        # qlib 0.9.0, numpy, pandas, scikit-learn, joblib ...
```

Qlib 데이터는 저장소 루트 README의 `data_collection/fetch_baostock_data.py` 절차를 따른다.

**실행 전 반드시 고쳐야 하는 3곳:**

| # | 위치 | 내용 |
| --- | --- | --- |
| 1 | [`../autoalpha.py:10`](../autoalpha.py#L10) | `provider_uri="path/to/your/qlib_data"` → 실제 Qlib 데이터 경로 |
| 2 | [`../backtest/ictester.py:10`](../backtest/ictester.py#L10) | 같은 플레이스홀더. **여기를 놓치면 적합도 계산 시점에 깨진다** |
| 3 | [`../autoalpha.py:34-48`](../autoalpha.py#L34-L48) | **`transformer.fit()` 호출이 빠져 있다.** 아래 참고 |

`autoalpha.py`는 `SymbolicTransformer`를 생성한 직후 `transformer._best_programs`에 접근하는데, 이 속성은 `fit()` 안에서만 설정된다. 따라서 현재 코드를 그대로 실행하면 `AttributeError`가 난다.

```python
transformer = SymbolicTransformer(...)
transformer.fit()                       # ← 이 한 줄을 추가해야 진화가 실행된다
programs = transformer._best_programs
```

### 2.2 실행

**저장소 루트에서** 실행해야 한다 (`_program.py`가 `from backtest.ictester import ICBacktester`를 하기 때문).

```bash
cd /path/to/AlphaEval
python autoalpha.py --start_time 2010-01-01 --end_time 2019-12-31 \
                    --population_size 1000 --hall_of_fame 50 \
                    --n_components 10 --generations 5
```

산출물: `autoalpha_results.parquet` — 컬럼은 `formula`(Qlib 표현식 문자열), `IC`(= `|IC|`).

> `parsimony_coefficient=0.0`이므로 저장되는 `IC` 값은 길이 패널티가 없는 `fitness_`, 즉 **정확히 `|IC|`** 다.

### 2.3 산출물 → AlphaEval 평가로 넘기기

```python
import pandas as pd
df = pd.read_parquet("autoalpha_results.parquet")
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
| `--population_size` | 30 | 세대별 개체 수 | 탐색 폭. 비용에 선형으로 영향 |
| `--generations` | 3 | 세대 수 | **곧 최종 수식 깊이(= generations+1)** 다. 표현력과 비용을 동시에 지배 |
| `--hall_of_fame` | 10 | 상관도 제거 대상 상위 개체 수 | `population_size` 이하 |
| `--n_components` | 6 | 최종 alpha 개수 | `hall_of_fame` 이하 |

### 3.2 `autoalpha.py`를 수정해야 하는 것

| 무엇 | 위치 | 비고 |
| --- | --- | --- |
| **`growth_k`** (세대별 후보 배수) | `SymbolicTransformer(...)` 인자로 추가 | **CLI로 노출되어 있지 않다.** 미지정 시 `SymbolicTransformer` 기본값 **5**가 적용된다 ([`genetic.py:979`](genetic.py#L979)). 비용을 줄이려면 여기를 먼저 낮춘다 |
| **`tournament_size`** | 같음 (기본 20) | population을 30 정도로 작게 쓰면 30개 중 20개를 뽑아 최고를 고르는 셈이라 선택압이 과도하다. `population_size`를 줄일 때 함께 줄일 것 |
| **종목 유니버스** | [`../autoalpha.py:27`](../autoalpha.py#L27) `D.instruments(market="all")` | `market="csi300"` 등으로 변경 |
| **주기(freq)** | [`../autoalpha.py:30`](../autoalpha.py#L30) | `"day"` |
| **난수 시드** | [`../autoalpha.py:44`](../autoalpha.py#L44) `random_state=0` | 단, 아래 4.2 때문에 완전 재현은 되지 않는다 |
| **길이 패널티** | `parsimony_coefficient` (현재 `0.0`) | 값을 키우면 짧은 수식을 선호. `'auto'`는 4.3 참고 |
| **연산자 집합** | `function_set=functions_arity.keys()` | 일부만 쓰려면 `["Add","Sub","Mean","Std"]`처럼 리스트로 직접 전달 |

### 3.3 `config.py`를 수정해야 하는 것 (탐색 공간 자체)

| 무엇 | 방법 |
| --- | --- |
| **입력 feature** | `FEATURE_LIST`에 Qlib 필드 추가/삭제. `autoalpha.py`가 그대로 `feature_names`로 넘기므로 자동 반영된다 |
| **rolling window 후보** | `window_lengths = [5, 12, 30, 64]` 수정 |
| **연산자 추가** | `functions_arity`에 `"이름": arity` 추가. rolling 계열은 반드시 `4`로 등록해야 `(하위트리, window)` 규약을 탄다. 주석 처리된 `Cov`, `Corr`, `Quantile`은 인자 구조가 이 규약에 맞지 않아 제외되어 있다 |

### 3.4 효과가 없는 파라미터 (함정)

- **`init_depth`** — 시드 생성 시 [`genetic.py:558`](genetic.py#L558)에 `init_depth=[1, 1]`이 **하드코딩**되어 있어 전달값이 무시된다. 그 이후 단계에서는 `build_program`이 아예 호출되지 않는다.
- **`p_subtree_mutation` / `p_hoist_mutation` / `p_point_mutation` / `p_point_replace` / `p_crossover`** — mutation 코드가 삭제되고 crossover는 무조건 수행되므로 아무 영향이 없다 (검증 로직만 남아 있다).
- **`stopping_criteria`** — 기본값 1.0, 즉 `|IC| ≥ 1.0`이어야 조기 종료하므로 실질적으로 항상 `generations`만큼 돈다.
- **`max_samples` / `sample_weight`** — 적합도 계산이 `sample_weight`를 사용하지 않으므로 서브샘플링·OOB가 무력화되어 있다.

### 3.5 비용 계산 (실행 전 꼭 확인)

```
총 IC 계산 횟수 = generations × population_size × (growth_k + 2)
```

각 IC 계산은 Qlib 조회를 2~3회 유발한다(수식 조회 + label 조회, `execute` 별도 1회).

| 설정 | 총 IC 계산 |
| --- | --- |
| `pop=30, gens=3, k=5` (autoalpha.py 기본값) | **630** |
| `pop=1000, gens=5, k=5` (루트 README 예시) | **35,000** |

루트 README의 예시 인자는 gplearn 기준(5,000회)의 **7배** 비용이다. 처음에는 `--population_size 50 --generations 3`에 `growth_k=2` 정도로 감을 잡는 것을 권한다.

---

## 4. 알려진 문제

> 아래는 코드를 읽고 확인한 사항이다. 이 문서는 코드를 수정하지 않는다. 근거와 반례는 [`../docs/AboutAutoAlpha.md`](../docs/AboutAutoAlpha.md) 4절에 정리해 두었다.

### 4.1 `n_jobs`는 1로 두어야 한다

`_parallel_evolve`가 자기 몫만 처리하면서 반환값은 **population 전체 복사본**([`genetic.py:72`](genetic.py#L72))이다. 워커가 n개면 결과를 concat한 population 길이가 `n_jobs × population_size`로 불어난다. 병렬화가 필요하면 growth phase만 나누도록 고쳐야 한다.

### 4.2 `random_state`만으로는 재현되지 않는다

두 곳이 파이썬 전역 `random`(시드 미설정)을 쓴다.

- [`_program.py:681`](_program.py#L681) crossover의 절단 depth 선택
- [`genetic.py:198-201`](genetic.py#L198-L201) growth phase의 부모/파트너 선택

`random.seed(...)`를 함께 설정하지 않으면 매 실행 결과가 달라진다.

### 4.3 depth 3 이상에서 계층 불변식이 깨질 수 있다

[`_program.py:626`](_program.py#L626)이 `stack[-1] -= 1`이어야 할 자리에 `stack[-1] == 0`(비교문, no-op)으로 되어 있어, 노드별 depth가 일부 과대 계산된다. depth 2 이하에서는 결과가 우연히 일치하므로 **Generation 0~1은 정상이고 Generation 2 이후(depth ≥ 3)** 부터 영향이 나타난다. 확인된 반례:

```
['Add','Add','Add','$a','$b','$c','$d']  = Add(Add(Add(a,b), c), d)
올바른 depth: [0, 1, 2, 3, 3, 2, 1]
코드가 계산:  [0, 1, 2, 3, 3, 2, 2]
```

이로 인해 "같은 층끼리 교환"이 어긋나 자녀 depth가 부모와 달라질 수 있고, 그 개체가 다음 세대 부모로 뽑히면 `crossover`의 `raise ValueError("Crossover two trees with different depth.")`가 잡히지 않고 **크래시**한다. depth가 1로 줄어든 개체가 부모가 되면 `random.randint(1, 0)` → `ValueError: empty range`. `--generations`를 크게 잡을수록 중도 실패 확률이 올라간다.

### 4.4 그 밖

- `parsimony_coefficient='auto'`는 첫 세대에서 `NameError` — [`genetic.py:618-621`](genetic.py#L618-L621)이 아직 정의되지 않은 `length`/`fitness`를 참조한다. `0.0`이나 실수 값을 쓰면 문제없다.
- Qlib이 파싱하지 못하는 수식은 예외를 삼키고 **조용히 `$close`로 대체**된다. 로그의 `"... can not be executed."` 줄 수를 세어 보면 실제 실패율을 알 수 있다.
- `growth_k` 기본값이 `BaseSymbolic`은 3, `SymbolicTransformer`는 5로 서로 다르다. 실제 적용값은 **5**.
- `__all__`에 `SymbolicRegressor`, `SymbolicClassifier`가 남아 있지만 구현체는 `SymbolicTransformer`뿐이다.
- `qlib.init()`은 `AutoAlpha.genetic` import보다 **먼저** 호출해야 한다 (`qlib_config` 기본 인자값이 import 시점에 평가된다).

---

## 5. 디렉토리 구성

| 파일 | 역할 | gplearn fork 대비 |
| --- | --- | --- |
| [`config.py`](config.py) | 탐색 공간 (feature · 연산자 · window) | 동일 |
| [`_program.py`](_program.py) | 개체 표현, 문자열 조립, Qlib 실행, 적합도, `depth_evolution`, 같은 층 crossover | **변경** |
| [`genetic.py`](genetic.py) | `SymbolicTransformer`, growth/evolve 2단 루프 | **변경** |
| [`fitness.py`](fitness.py) | 적합도 메트릭 모음 (실제로는 `greater_is_better` 플래그 용도) | 동일 |
| [`functions.py`](functions.py) | 원본 gplearn의 numpy 연산자 노드 (대부분 미사용) | 동일 |
| [`utils.py`](utils.py) | scikit-learn 유틸 복사본 | 동일 |

라이선스: 원본 gplearn(BSD 3-clause) 기반. 저장소 루트 `LICENSE` 참고.
