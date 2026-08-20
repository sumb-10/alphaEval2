# Search Space Record — `gp_native` v1

상태: 기록·버전링용 (Controlled Benchmark 단계에서 중립 공통 명세
`alpha_space_v1`로 통일하기 위한 사전 문서). 이 문서는 **GP가 실제로 탐색
가능한 수식 공간**을 정의하며, 코드 근거는 `gplearn_asb/gplearn_asb/
vendored_gplearn/config.py`와 `_program.py`다.

버전 규칙: terminal/operator/window/complexity 규칙이 바뀌면 v2로 증가.
공통 명세는 mining method와 evaluator(ASB) **모두로부터 독립**된 위치에
정의한다(소유권: 어느 쪽도 아님).

## Terminals (10)

```
$adjclose  $amount  $change  $close  $factor  $high  $low  $open  $volume  $vwap
```

상수 terminal 없음(`const_range=None`) — 수치는 rolling window 자리에만 등장.

## Operators (29)

| 종류 | 연산자 | 실효 인자 |
|---|---|---|
| unary (3) | `Abs, Sign, Log` | 1 |
| binary (7) | `Add, Sub, Mul, Div, Power, Greater, Less` | 2 |
| rolling (19) | `Ref, Mean, Sum, Std, Var, Skew, Kurt, Min, Max, IdxMin, IdxMax, Med, Mad, Delta, Slope, Rsquare, Resi, WMA, EMA` | 2 (`Op(x, window)`) |

의미론 주의(qlib 0.9.0 미러):
* **`Greater`/`Less` = element-wise max/min** (비교 아님) → `Greater(x,x)=x` 항등.
* rolling `min_periods=1`; **window 0 = expanding**; `Ref(x,0)` = 커버리지 시작 행 값.
* `functions_arity`의 rolling 값 4는 실제 인자 수가 아니라 트리 빌더 마커
  (렌더링 시 arity 2로 환원).
* 비활성(주석 처리): `Not, And, Or, Cov, Corr, Quantile`.

## Window 상수

```
window_lengths = [5, 12, 30, 64]
```

트리 노드에 박힌 정수 상수로 표현되며 유전연산의 대상이다.

## Complexity 규칙

| 항목 | v1 (legacy) | v2 |
|---|---|---|
| 초기 깊이 | randint(1, 5) → 1~4 (half-and-half) | 동일 |
| 진화 후 깊이/길이 | **무제한** (crossover/mutation이 검사 안 함) | `gp.max_program_length` hard bound — **값 결정 대기**(교차 방법 문법 대조 후, freeze 조건 ①) |
| parsimony | 0 (실효 없음) | 0 내부 고정 (hard bound와 이중 패널티 금지) |

## 알려진 문법 이탈 (v1 한정 — v2에서 소멸)

legacy point mutation(`_program.py:708-755`)이 terminal 자리에 **feature
인덱스 정수(0~9)를 그대로 대입** → ① feature 자리에 상수 유사 노드
(`Add(3, $close)`), ② rolling window 자리에 `window_lengths` 밖 값
(`Var($factor, 6)` 실측 — 단 qlib 의미론상 유효 평가됨). v2의 typed
mutation은 feature→feature 이름, window→`window_lengths` 내 교체로 이
이탈을 제거한다. **따라서 v1과 v2의 실효 탐색 공간은 미세하게 다르다**
(v1이 문법 밖 표본을 소량 포함) — 교차 비교 시 명시할 것.

## 공간 밖 (이 문법으로 표현 불가)

순위(Rank) 연산, 조건 분기, 비교 연산자(진짜 부등호), cross-sectional
정규화 연산자, 상수항(위 window 제외), 다중 자산 참조.

## 방법별 대조 (Controlled 단계 준비)

| | gp_native v1 | alphaagent_native (기록 예정) |
|---|---|---|
| terminal | 10 필드 | 5 필드($open/high/low/close/volume) |
| operator | 29 | 22 (Corr/Cov/Rank 포함 — GP에 없음) |
| window | {5,12,30,64} 고정 | 자유 정수 |
| 표현 | 함수형 prefix 문자열 | 자유 텍스트 infix (파서 후처리) |

공통 명세(`alpha_space_v1`)는 이 대조표의 교집합/합집합 결정과 함께
Controlled 단계에서 확정한다.
