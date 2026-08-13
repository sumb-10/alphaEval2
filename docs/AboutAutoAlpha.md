# AboutAutoAlpha — 계층적(depth 단계별) 진화 기반 Formula Alpha 마이닝

이 문서는 AlphaEval 저장소의 `autoalpha.py` 및 `AutoAlpha/` 패키지가 **어떻게 동작하는지**를 코드 레벨에서 설명한다.
gplearn 쪽과 겹치는 기반 구조는 [`AboutGPLearn.md`](AboutGPLearn.md)에 이미 정리되어 있으므로, 이 문서는 **AutoAlpha가 달라지는 지점**에 집중한다.
실행 방법과 파라미터 조정은 [`../AutoAlpha/README.md`](../AutoAlpha/README.md)를 참고.

---

## 0. AlphaEval 전체 구조에서의 위치

AutoAlpha도 gplearn과 마찬가지로 파이프라인의 **1단계 생성기**다. 산출물은 `{formula, IC}` parquet이고, 그 formula가 그대로 `backtest/modeltester`의 `AlphaEval`에 입력된다.

```
Qlib Market Data
      │
      ▼
[AutoAlpha]  ← 이 문서의 대상: depth를 한 층씩 키우는 계층적 GP
      │  "Div(Add(Mean($close, 30), $open), Std($volume, 12))"
      ▼
autoalpha_results.parquet  {formula, IC}
      │
      ▼
backtest/combo.py (WeightCalculator) → weights
      │
      ▼
backtest/modeltester.py (AlphaEval) → 평가
```

원 논문은 Zhang et al., *"AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment"* 이며, 핵심 아이디어는 **얕은 수식에서 시작해 depth를 한 층씩 키워 가며(coarse-to-fine) 탐색 공간을 계층적으로 확장**하는 것이다. 이 저장소의 구현은 gplearn fork를 베이스로 그 아이디어를 얹었다.

---

## 1. 파일 구성 — gplearn fork와 무엇이 같고 무엇이 다른가

`AutoAlpha/`는 `gplearn/`의 복사본에서 출발했다. 실제로 `diff`를 떠 보면 **5개 파일은 완전히 동일**하다.

| 파일 | gplearn/ 대비 |
| --- | --- |
| `config.py` | **완전 동일** (feature 10개 · 연산자 29개 · window `[5,12,30,64]`) |
| `functions.py` | **완전 동일** (대부분 미사용) |
| `fitness.py` | **완전 동일** (`greater_is_better` 플래그 용도) |
| `utils.py` | **완전 동일** |
| `__init__.py` | **완전 동일** |
| [`_program.py`](../AutoAlpha/_program.py) | **변경**: `depth()` 헬퍼 추가, `get_subtree`에 `target_depth` 추가, `crossover` 재작성, `depth_evolution` 신규, **subtree/hoist/point mutation 전부 삭제** |
| [`genetic.py`](../AutoAlpha/genetic.py) | **변경**: `_parallel_growth` 신규, `_parallel_evolve` 재작성, `fit`이 2단(growth→evolve) 구조로 변경, `growth_k` 파라미터 추가 |

따라서 다음 요소는 gplearn 문서의 설명이 **그대로 유효**하다.

- 개체 표현 = 전위(prefix) 리스트 `['Div','Mean','$close',30,'$volume']`
- `arity == 4` = rolling 연산자 sentinel (실제로는 `(하위트리, window 상수)` 2슬롯)
- `__str__`/`execute`의 Qlib 표현식 문자열 조립
- **적합도 = `abs(일별 cross-sectional IC의 평균)`** — `backtest/ictester.py`의 `ICBacktester.calculate1()`
- 최종 단계의 `hall_of_fame` → 상관도 제거 → `n_components`

바뀐 것은 오직 **"다음 세대 개체를 어떻게 만드는가"** 다.

---

## 2. 알고리즘: depth를 한 층씩 올리는 2단 루프

gplearn은 "임의 깊이의 트리를 만들고 crossover/mutation을 섞는" 평평한 GP다. AutoAlpha는 **세대 = depth 레벨**로 보고, 각 세대에서 두 단계를 순서대로 돌린다.

```
[seed]  depth-1 프로그램 population_size개 생성        (genetic.py:553-570)
   │
   ├── Generation 0 ─────────────────────────────────────────────
   │     ① Growth  : depth_evolution으로 depth+1 후보 k×pop개 생성
   │                 → IC 평가 → 정렬 → 상위 pop개만 생존 (truncation)
   │     ② Evolve  : 같은 depth끼리 crossover, 2자녀, 탐욕적 교체
   │   → population: depth 2
   │
   ├── Generation 1 : 같은 ①② → population: depth 3
   ├── Generation 2 : 같은 ①② → population: depth 4
   └── ...
   │
   ▼
마지막 세대 → hall_of_fame → 상관도 제거 → n_components → _best_programs
```

**최종 트리 depth = `generations` + 1** 이다. `--generations 5`면 depth 6 수식까지 자란다.

### 2.1 Seed: depth-1 유전자 풀

```python
for _ in range(self.population_size):
    program = _Program(..., init_depth=[1, 1], ..., program=None, ...)
    warm_start_parents.append(program)
```

([`genetic.py:553-570`](../AutoAlpha/genetic.py#L553-L570))

`init_depth=[1,1]`이 **하드코딩**되어 있으므로 시드는 항상 `연산자(터미널…)` 형태의 depth-1 수식이다. 예: `Mean($close, 30)`, `Add($high, $low)`, `Abs($change)`.

> ⚠️ 이 하드코딩 때문에 `SymbolicTransformer(init_depth=...)`로 넘기는 값은 **아무 효과가 없다.** 또한 이후 단계에서 `_Program`은 항상 `program=<리스트>`를 받아 생성되므로 `build_program`은 시드 생성에서만 호출된다.

### 2.2 ① Growth phase — `depth_evolution`

```python
def depth_evolution(self, partner, random_state):
    function = random_state.choice(비-rolling 연산자)     # arity 4는 재추첨
    if functions_arity[function] == 1:
        return [function] + self.program                  # 단항: 자기 위에 한 층
    return [function] + self.program + partner.program    # 이항: 자기 + 파트너를 자식으로
```

([`_program.py:693-701`](../AutoAlpha/_program.py#L693-L701))

- 새 루트를 하나 씌워 **depth를 정확히 1 늘린다.**
- 같은 세대의 부모들은 모두 같은 depth이므로, 이항 결합(`1 + max(d, d) = d+1`)도 depth를 정확히 1만 늘린다. 이 **"세대 내 depth 균일" 불변식**이 다음 단계 crossover의 전제가 된다.
- **rolling 연산자(arity 4)는 새 루트가 될 수 없다** (`while functions_arity[function] == 4: 재추첨`). `[f] + program + <window 정수>` 형태를 만들 코드가 없기 때문이다.
  → 구조적 귀결: **AutoAlpha가 만드는 트리에서 rolling 연산자는 최하단(시드) 층에만 존재하고, 그 위층은 전부 산술/논리 연산자다.** `Mean(Add($close, $open), 30)` 같은 "복합식의 이동평균"은 생성되지 않는다. gplearn fork와의 가장 큰 표현력 차이다.

후보 생성·선별 ([`genetic.py:165-251`](../AutoAlpha/genetic.py#L165-L251), [`:589-614`](../AutoAlpha/genetic.py#L589-L614)):

```python
total_candidates = growth_k * population_size          # 후보를 k배로 뽑고
... _parallel_growth(...)                              # 전부 IC 평가
all_candidates.sort(key=lambda p: p.raw_fitness_, reverse=True)
parents_for_evolve = all_candidates[: self.population_size]   # 상위 pop개만 생존
```

- 부모/파트너 선택은 **적합도와 무관한 균등 랜덤**(`random.randint(0, len(parents)-1)`)이다. 선택압은 뒤의 **truncation selection**(상위 `population_size` 절단)에서만 걸린다.
- 즉 growth phase = "한 층 키운 변형을 k배로 만들어 보고 좋은 것만 남긴다"는 **beam search**에 가깝다.

### 2.3 ② Evolve phase — 같은 depth끼리 crossover

```python
if depth(donor) != self._depth():
    raise ValueError("Crossover two trees with different depth.")
subtree_depth = random.randint(1, self._depth() - 1)
start, end             = self.get_subtree(random_state, target_depth=subtree_depth)
donor_start, donor_end = self.get_subtree(random_state, program=donor, target_depth=subtree_depth)
return (앞 + donor조각 + 뒤), (donor앞 + 내조각 + donor뒤)      # 자녀 2개
```

([`_program.py:657-691`](../AutoAlpha/_program.py#L657-L691))

gplearn fork의 crossover와 세 군데가 다르다.

1. **depth가 같은 두 트리만** 교배한다 (다르면 예외).
2. 절단 위치를 랜덤 노드가 아니라 **"특정 depth 레벨의 노드"** 로 고른다 → 같은 층끼리 교환하므로 자녀의 depth가 보존된다.
3. 자녀를 **2개** 반환한다 (교환의 양방향).

교체 규칙 ([`genetic.py:72`](../AutoAlpha/genetic.py#L72), [`:158-160`](../AutoAlpha/genetic.py#L158-L160)):

```python
programs = parents.copy()                 # 기본은 부모 그대로 유지
...
son1, son2 = parent.crossover(donor.program, random_state)
...
if max(son1.raw_fitness_, son2.raw_fitness_) > max(parent.raw_fitness_, donor.raw_fitness_):
    programs[parent_index] = son1
    programs[donor_index]  = son2
```

**탐욕적 쌍 교체(greedy pairwise replacement)** 다. 부모 쌍 중 잘한 쪽보다 자녀 쌍 중 잘한 쪽이 나을 때만 두 슬롯을 자녀로 덮어쓴다. 즉 population 최고 적합도는 세대 내에서 **단조 비감소**다. 부모 선택 자체는 gplearn과 같은 tournament(`tournament_size`)를 쓴다.

### 2.4 적합도와 최종 선택

gplearn fork와 **완전히 동일**하다.

- `raw_fitness()` → `ICBacktester(수식, ...).calculate1()` → `abs(일별 cross-sectional IC 평균)`
- `fitness_ = raw_fitness_ - parsimony_coefficient × len(program) × sign`
- 마지막 세대에서 상위 `hall_of_fame` → 개체 간 `|corrcoef|`가 가장 큰 쌍에서 열등한 쪽 제거 → `n_components`개 → `_best_programs` ([`genetic.py:704-733`](../AutoAlpha/genetic.py#L704-L733))

### 2.5 세대별 진행 예시 (`population_size=30, growth_k=5, generations=3`)

| Gen | 부모 depth | Growth 후보 | 생존 | Evolve 평가 | 세대 말 depth | 세대별 IC 계산 횟수 |
| --- | --- | --- | --- | --- | --- | --- |
| seed | — | — | 30 | — | 1 | 0 (시드는 평가 안 함) |
| 0 | 1 | 150 | 30 | 60 (자녀 2×30) | 2 | 210 |
| 1 | 2 | 150 | 30 | 60 | 3 | 210 |
| 2 | 3 | 150 | 30 | 60 | 4 | 210 |

세대당 IC 계산 = `population_size × (growth_k + 2)`. 각 계산이 Qlib 조회 2~3회를 유발한다.

---

## 3. gplearn fork와의 차이 요약

| 항목 | gplearn fork | AutoAlpha |
| --- | --- | --- |
| 초기 population | `init_depth=(1,4)` ramped half-and-half | **depth 1 고정** (`init_depth` 무시) |
| depth 변화 | 자유 (crossover/mutation에 따라) | **세대마다 정확히 +1** (계층적) |
| 유전 연산 | crossover + subtree/hoist/point mutation + reproduction | **crossover만** (mutation 전부 삭제) + `depth_evolution` |
| crossover 제약 | 없음 | **동일 depth 트리끼리, 동일 depth 레벨에서만** |
| 자녀 수 | 1 | **2** |
| 세대 교체 | 전 세대를 새 개체로 완전 교체 | **탐욕적 쌍 교체** (개선될 때만) |
| 선택압 | tournament | growth는 **truncation**, evolve는 tournament + 탐욕 |
| rolling 연산자 위치 | 트리 어디든 | **최하단 시드 층에만** |
| 세대당 평가 수 | `population_size` | `population_size × (growth_k + 2)` |
| 추가 파라미터 | — | `growth_k` |

---

## 4. 실행 시 알아야 할 것 / 알려진 문제

### 4.1 실행 전 반드시 수정

1. **`fit()` 호출 누락** — [`autoalpha.py`](../autoalpha.py)는 `SymbolicTransformer`를 생성한 직후 `transformer._best_programs`에 접근한다. 이 속성은 `fit()` 안에서만 설정되므로 **그대로 실행하면 `AttributeError`** 다. (gplearn 쪽과 동일한 문제)
   ```python
   transformer = SymbolicTransformer(...)
   transformer.fit()          # ← 필요
   programs = transformer._best_programs
   ```
2. **Qlib 경로 2곳** — [`autoalpha.py:10`](../autoalpha.py#L10) 과 [`backtest/ictester.py:10`](../backtest/ictester.py#L10). 후자를 놓치면 적합도 계산 시점에 깨진다.
3. **실행 위치** — `_program.py`가 `from backtest.ictester import ICBacktester`를 하므로 저장소 루트에서 실행해야 한다.
4. **`qlib.init()`이 import보다 먼저** — `qlib_config` 기본 인자값이 import 시점에 `D.instruments(market="all")`를 평가한다.

### 4.2 `n_jobs > 1`은 population을 망가뜨린다

```python
programs = parents.copy()        # 각 워커가 "전체 부모 리스트"의 복사본을 반환
...
population = list(itertools.chain.from_iterable(population))
```

`_parallel_evolve`는 자기 몫(`n_programs[i]`)만 처리하지만 반환값은 **항상 population 전체**다. 워커가 n개면 concat 결과 길이가 `n_jobs × population_size`가 되어 세대가 진행될수록 population이 뻥튀기된다.
→ **현재 구현은 `n_jobs=1` 전용**이다. (growth phase는 이 문제가 없다.)

### 4.3 `get_subtree`의 depth 계산 오류

[`_program.py:626`](../AutoAlpha/_program.py#L626)이 `stack[-1] -= 1`이어야 할 자리에 `stack[-1] == 0`(비교문, no-op)로 되어 있다. 서브트리가 완성되어 pop된 뒤 부모의 슬롯 카운터가 감소하지 않으므로, **완성된 서브트리 뒤에 오는 얕은 층 노드의 depth가 과대 계산**된다.

직접 확인한 반례:

```
program: ['Add','Add','Add','$a','$b','$c','$d']   = Add(Add(Add(a,b), c), d)
올바른 depth: [0, 1, 2, 3, 3, 2, 1]
코드가 계산:  [0, 1, 2, 3, 3, 2, 2]   ← 마지막 $d

program: ['Div','Add','Mean','$close',5,'$open','Std','$volume',12]
올바른 depth: [0, 1, 2, 3, 3, 2, 1, 2, 2]
코드가 계산:  [0, 1, 2, 3, 3, 2, 2, 3, 3]   ← Std 이하 전부
```

depth 2 이하 트리에서는 결과가 우연히 일치하므로 **Generation 0~1은 정상 동작하고, depth 3 이상이 되는 Generation 2부터 틀어진다.** 그 결과:

- `target_depth`로 고른 노드의 실제 depth가 달라 **"같은 층끼리 교환" 불변식이 깨진다** → 자녀 depth가 부모와 달라질 수 있다.
- 그렇게 생긴 depth 불일치 개체가 다음 세대에 부모로 뽑히면 `crossover`의 `raise ValueError("Crossover two trees with different depth.")`가 **잡히지 않고 그대로 크래시**한다.
- 트리가 depth 1로 줄어든 개체가 부모가 되면 `random.randint(1, 0)` → `ValueError: empty range`.

즉 `generations`를 크게 잡을수록 중도 실패 확률이 올라간다. 이 문서는 코드를 수정하지 않지만, 장기 실행을 하려면 이 한 줄을 먼저 확인하는 것이 좋다.

### 4.4 재현성

`random_state=0`을 줘도 **완전 재현되지 않는다.** 두 곳에서 파이썬 전역 `random`(시드 미설정)을 쓴다.

- [`_program.py:681`](../AutoAlpha/_program.py#L681) `subtree_depth = random.randint(...)` — crossover 절단 레벨
- [`genetic.py:198-201`](../AutoAlpha/genetic.py#L198-L201) 부모/파트너 선택

`numpy` `random_state`로 결정되는 부분(시드 생성, 연산자 추첨, `get_subtree` 후보 선택)만 재현된다.

### 4.5 그 밖의 주의점

- **`parsimony_coefficient='auto'`는 첫 세대에서 `NameError`** — [`genetic.py:618-621`](../AutoAlpha/genetic.py#L618-L621)이 아직 정의되지 않은 `length`/`fitness`를 참조한다. `autoalpha.py`는 `0.0`을 넘기므로 발동하지 않는다.
- **`tournament_size`(기본 20)와 `population_size`(`autoalpha.py` 기본 30)의 균형** — 30개 중 20개를 뽑아 최고를 고르면 사실상 항상 최상위 개체가 부모가 된다. population을 작게 쓸 때는 `tournament_size`도 함께 줄여야 다양성이 유지된다.
- **`stopping_criteria`는 실질적으로 동작하지 않는다** — `SymbolicTransformer` 기본값 1.0, 즉 `|IC| ≥ 1.0`이어야 조기 종료한다.
- **`params['curr_depth']`는 설정되지만 사용되지 않는다** ([`genetic.py:576`](../AutoAlpha/genetic.py#L576), `_parallel_growth`에서 unpack만 함).
- **조상 pruning의 인덱스 의미가 어긋난다** — `genome`의 `parent_idx`/`donor_idx`는 `parents_for_evolve`(growth 결과) 기준 인덱스인데, pruning은 이를 `self._programs[gen-1]` 인덱스로 간주해 `None`을 채운다. 최종 결과는 `_programs[-1]`만 쓰므로 산출물에는 영향이 없다.
- **실패한 수식은 조용히 `$close`로 대체**된다 (gplearn과 동일).
- **`growth_k` 기본값이 두 군데서 다르다** — `BaseSymbolic`은 3([`:298`](../AutoAlpha/genetic.py#L298)), `SymbolicTransformer`는 5([`:979`](../AutoAlpha/genetic.py#L979)). `autoalpha.py`는 이를 지정하지 않으므로 **실제 적용값은 5**다.

---

## 5. 한 장 요약

```
seed        depth-1 수식 pop개            Mean($close,30), Add($high,$low), ...
  │
  │  ┌─ Generation g ────────────────────────────────────────────────┐
  │  │ ① Growth   depth_evolution: [새 루트] + 자기 (+ 파트너)        │
  │  │            → k×pop 후보 → 전부 |IC| 평가 → 상위 pop개 생존     │
  │  │ ② Evolve   같은 depth·같은 레벨 crossover → 자녀 2개            │
  │  │            → max(자녀) > max(부모)일 때만 두 슬롯 교체          │
  │  └───────────────────────────────────────────────────────────────┘
  │        depth 1 → 2 → 3 → ... → generations+1
  ▼
hall_of_fame 상위 → |상관| 높은 쌍에서 열등한 쪽 제거 → n_components
  ▼
autoalpha_results.parquet  {formula, IC=|IC|}  →  AlphaEval
```

한 문장으로: **AutoAlpha는 gplearn fork의 개체 표현과 IC 적합도를 그대로 쓰면서, mutation을 모두 버리고 "depth를 한 층씩 키우는 growth + 같은 층끼리의 crossover"로 탐색을 계층화한 변형**이다.
