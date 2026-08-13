# AboutAlphaAgent — LLM 멀티에이전트 기반 Formula Alpha 마이닝

이 문서는 AlphaEval 저장소의 `alphaagent.py` 및 `Alphaagent/` 패키지가 **어떻게 동작하는지**를 코드 레벨에서 설명한다.
실행 방법과 조건 변경은 [`../Alphaagent/README.md`](../Alphaagent/README.md)를 참고.

---

## 0. AlphaEval 전체 구조에서의 위치

AlphaAgent도 파이프라인의 **1단계 생성기**지만, 나머지 baseline과 성격이 근본적으로 다르다.

| | gplearn / AutoAlpha / AlphaEvolve | **AlphaAgent** |
| --- | --- | --- |
| 탐색 주체 | 유전 알고리즘 (population) | **LLM (gpt-4o)** |
| 탐색 신호 | IC 적합도 수치 | **자연어 백테스트 리포트 + LLM 판단** |
| 개체 표현 | 전위 리스트 → 문자열 조립 | **LLM이 직접 뱉는 수식 문자열** |
| 다양성 확보 | 값 상관계수 pruning | **AST(구문 트리) 유사도 페널티** |
| 비용 지배 요인 | Qlib 조회 횟수 | **LLM API 호출 횟수** |
| 산출물 | `{formula, IC}` parquet | 수식 문자열 리스트 (`.json` / `.txt`) |

```
37개 seed 수식 (하드코딩)
      │
      ▼
[IdeaAgent]  가설 + 자연어 factor 설명 생성          (LLM, temp 1.0)
      │
      ▼
[FactorAgent] 자연어 → Qlib 수식 문자열 + AST        (LLM, temp 0.3)
      │
      ▼
[FactorBacktester] long/short 백테스트 → 성과 지표    (Qlib, 코드)
      │
      ▼
[EvalAgent]  성과 3개 지표 → 요약/권고/합격 판정      (LLM, temp 0.4)
      │
      ├─ 합격 → 풀에 저장
      └─ 불합격 → 리포트를 IdeaAgent에 되먹임 (최대 3라운드)
      │
      ▼
alpha_agent.txt / alpha_agent_results.json → AlphaEval
```

---

## 1. 파일 구성

| 파일 | 역할 |
| --- | --- |
| [`../alphaagent.py`](../alphaagent.py) | 엔트리포인트. seed 수식 37개 정의, 3개 agent 조립, seed별 최대 3라운드 루프 |
| [`../Alphaagent/agents/idea_agent.py`](../Alphaagent/agents/idea_agent.py) | **IdeaAgent** — 시장 가설 + factor 아이디어(자연어) 생성 |
| [`../Alphaagent/agents/factor_agent.py`](../Alphaagent/agents/factor_agent.py) | **FactorAgent** — 자연어 아이디어 → Qlib 수식 문자열 + Python AST |
| [`../Alphaagent/agents/eval_agent.py`](../Alphaagent/agents/eval_agent.py) | **EvalAgent** — 백테스트 실행 + AST 유사도 계산 + LLM 합격 판정 |
| [`../Alphaagent/backtester.py`](../Alphaagent/backtester.py) | `FactorBacktester` — long/short 포트폴리오 백테스터 (IC·Sharpe·MaxDD 등) |
| `../Alphaagent/alpha_agent.txt` | **최종 alpha pool** (수식 9개, 줄 단위) |
| `../Alphaagent/alpha_agent_results.json` | 파이프라인이 자동 저장하는 합격 수식 리스트 (현재 커밋된 값은 `[]`) |
| `../Alphaagent/test.log`, `test_time.log` | 실제 실행 로그 (아래 5절에서 이 로그로 동작을 검증했다) |

> 디렉토리 이름은 `Alphaagent`(두 번째 a가 소문자)이다. `import`도 `from Alphaagent.agents...` 형태이므로 대소문자를 바꾸면 깨진다.

---

## 2. 각 Agent의 동작

### 2.1 IdeaAgent — 가설 생성 / 가설 개선

`gpt-4o`, `temperature=1.0`(높은 창의성). **system prompt를 두 개** 들고 있고 인자 조합으로 분기한다 ([`idea_agent.py:33-99`](../Alphaagent/agents/idea_agent.py#L33-L99)).

| 호출 형태 | 사용 프롬프트 | 용도 |
| --- | --- | --- |
| `generate(context=seed수식)` | `system_prompt_new` | seed 수식을 **영감**으로 새 아이디어 생성 (그대로 베끼지 말라고 지시) |
| `generate()` (전부 None) | `system_prompt_new` | 아무 조건 없이 아이디어 생성 |
| `generate(context, hypothesis, previous_expr, eval_report)` | `system_prompt_enhance` | 이전 수식과 **백테스트 리포트를 보고** (A) 개선 또는 (B) 폐기 후 재발명 |

출력 계약은 JSON 한 덩어리다.

```json
{ "hypothesis": "<시장 가설>", "description": "<factor 자연어 설명>" }
```

`parse_response`는 `json.loads`를 시도하고 실패하면 **예외를 던지지 않고 빈 딕트 `{"hypothesis":"", "description":""}`를 반환**한다 ([`:101-122`](../Alphaagent/agents/idea_agent.py#L101-L122)). 즉 파싱 실패가 조용히 "빈 아이디어"로 전파되어, 다음 단계에서 LLM이 빈 설명으로 수식을 만들게 된다.

`enhance` 경로에서만 `{`~`}` 구간을 잘라내는 전처리를 한다(`content.find('{')` / `rfind('}')`). `new` 경로에는 이 처리가 없어서, 모델이 코드 펜스나 설명을 덧붙이면 파싱이 실패한다.

### 2.2 FactorAgent — 자연어 → Qlib 수식

`gpt-4o`, `temperature=0.3`(낮은 창의성 = 형식 준수). 핵심은 **프롬프트에 박아 넣은 연산자 사양**이다 ([`factor_agent.py:12-30`](../Alphaagent/agents/factor_agent.py#L12-L30)).

```
features : $open, $high, $low, $close, $volume
operators: Abs Log Sign + - * / **
           Ref(x,d) Corr(x,y,d) Cov(x,y,d) Delta(x,d) WMA(x,d)
           Min(x,d) Max(x,d) IdxMax(x,d) IdxMin(x,d) Rank(x,d)
           Sum(x,d) Std(x,d) Greater(x,y) Less(x,y)
```

GP 계열의 탐색 공간(`gplearn/config.py`)과 비교하면 성격이 뚜렷하다.

- feature가 **5개로 축소**($vwap, $amount, $change, $adjclose, $factor 없음)
- **`Corr`/`Cov`/`Rank`가 추가**됨 — GP 쪽은 arity 규약 문제로 `Corr`/`Cov`를 주석 처리해 두었다. 즉 **AlphaAgent만 2변수 시계열 상관 factor를 만들 수 있다.**
- window `d`가 **`[5,12,30,64]`에 묶이지 않는다** — LLM이 50, 120 등 임의 값을 쓴다 (실제 산출물에 `WMA($close, 120)`, `Rank($high/$close, 10)`가 있다).
- 중첩 깊이 제한이 없다.

반환값은 `(수식 문자열, Python AST)`다. AST는 `$`를 제거한 뒤 `ast.parse(expr, mode='eval')`로 만든다 ([`:57`](../Alphaagent/agents/factor_agent.py#L57)) — Qlib 수식이 마침 Python 표현식과 문법이 호환되기 때문에 가능한 트릭이고, 이 AST가 다음 단계의 중복 판정에 쓰인다.

### 2.3 FactorBacktester — 실제 성과 계산

[`backtester.py`](../Alphaagent/backtester.py). GP 계열이 `ICBacktester`로 IC 하나만 재는 것과 달리, **실제 long/short 포트폴리오를 굴린다.**

```python
long_cut  = f.quantile(1 - 0.2)      # 상위 20%
short_cut = f.quantile(0.2)          # 하위 20%
pnl = (long_ret + short_ret) / 2
turnover = (진입+이탈 종목수) / (이전 롱+숏 종목수)
pnl = pnl - turnover * 0.0015        # 편도 0.15% 거래비용
```

([`:98-139`](../Alphaagent/backtester.py#L98-L139))

`calculate_performance()`는 이를 **연도별 + 전체(`total`)** 로 집계한다 ([`:141-221`](../Alphaagent/backtester.py#L141-L221)).

| 지표 | 정의 |
| --- | --- |
| `AnnRet` | `(1+누적수익)^(252/n) - 1` |
| `AnnTurn` | 일별 turnover 평균 |
| `Sharpe` | `mean(pnl)/std(pnl) × √252` |
| `IC` | 일별 cross-sectional Pearson IC의 평균 |
| `RankIC` | 일별 cross-sectional Spearman(rank) IC의 평균 |
| `MaxDD` | 누적 곡선 기준 최대 낙폭 |
| `Fitness` | `Sharpe × √|AnnRet / AnnTurn|` (WorldQuant 스타일 지표) |

> 주의: 하드코딩된 `0.2` 분위수([`:109-110`](../Alphaagent/backtester.py#L109-L110))가 실제로 쓰이고, 생성자의 `long_threshold`/`short_threshold` 인자는 저장만 되고 사용되지 않는다.

### 2.4 EvalAgent — 중복 판정 + LLM 합격 판정

두 가지 일을 한다 ([`eval_agent.py`](../Alphaagent/agents/eval_agent.py)).

**(a) AST 유사도로 중복 억제** ([`:10-61`](../Alphaagent/agents/eval_agent.py#L10-L61))

```
similarity = (최대 공통 부분트리 노드 수) / ((트리1 노드 수 + 트리2 노드 수) / 2)
```

노드 라벨(`BinOp`, `Call`, `Name` 등 AST 타입 이름)이 같은지로 매칭하고, 자식들끼리는 **LCS 스타일 DP**로 최대 매칭을 구한다(`max_common_subtree_size`). 즉 **값이 아니라 수식의 구조**를 비교한다. GP 계열이 factor 값의 상관계수로 중복을 제거하는 것과 대비되는 접근이다.

비교 대상은 `results_ast` — **이미 합격한 factor들**뿐이다. 불합격 factor는 누적되지 않으므로, 계속 탈락하는 비슷한 수식들은 서로 걸러지지 않는다.

**(b) LLM 합격 판정** ([`:114-152`](../Alphaagent/agents/eval_agent.py#L114-L152))

LLM에 넘기는 정보는 딱 3개다.

```python
perf = {"AnnRet": perf["AnnRet"]["total"],
        "IC": perf["IC"]["total"],
        "Similarity to Previous": max_corr}
```

그리고 system prompt가 기준을 알려준다.

> "When the annual return > 10% and IC > 0.03, it is considered a high-quality factor. The similarity the lower, the better."

**핵심: 합격/불합격 게이트는 코드의 `if`문이 아니라 LLM의 판단이다.** 기준은 프롬프트로만 전달되므로 경계 사례에서는 판정이 흔들릴 수 있고, `is_high_quality`가 `None`으로 돌아오는 경우도 있다(5절 실측). Sharpe·MaxDD·RankIC·Fitness는 계산되지만 **LLM에게 전달되지 않는다** — 백테스터가 만든 정보의 대부분이 판정에 쓰이지 않는다.

백테스트 중 예외가 나면 `result["is_valid"]=False`, `is_high_quality=None`으로 삼키고 계속 진행한다 ([`:109-110`](../Alphaagent/agents/eval_agent.py#L109-L110)).

---

## 3. 오케스트레이션 루프

[`alphaagent.py:63-96`](../alphaagent.py#L63-L96)

```python
for example in expressions[20:]:              # ← seed 37개 중 21번째부터 17개만
    idea = idea_agent.generate(example)       # seed를 영감으로 아이디어
    for round_id in range(3):                 # 최대 3라운드
        expr, expr_ast = factor_agent.generate(idea)
        result = eval_agent.evaluate(expr, expr_ast, results_ast)
        if result["is_high_quality"]:
            results.append(expr); results_ast.append(expr_ast)
            break                             # 합격 → 다음 seed로
        elif round_id < 2:
            eval_report_str = result["summary"] + "\n" + result["recommendation"]
            idea = idea_agent.generate(example, idea, expr, eval_report_str)
json.dump(results, open("alpha_agent_results.json", "w"), indent=2)
```

- **seed 주도 탐색**: 37개의 손으로 쓴 기본 factor(모멘텀·변동성·거래량·반전 등 Alpha101 스타일)가 각각 하나의 탐색 시작점이 된다. LLM은 "이걸 베끼지 말고 영감으로 삼아" 새 아이디어를 만든다.
- **되먹임 루프**: 불합격이면 `summary + recommendation`(자연어)이 다음 IdeaAgent 호출에 들어간다. GP의 적합도 기울기 대신 **자연어 비평**이 개선 신호다.
- **최대 3라운드**, 합격 즉시 다음 seed로 이동. seed당 LLM 호출은 최대 `3라운드 × 3콜 = 9회` (IdeaAgent 1 + FactorAgent 1 + EvalAgent 1), 백테스트는 최대 3회.
- 현재 슬라이스 `expressions[20:]`(17개) 기준 총 LLM 호출은 최대 153회, 백테스트 최대 51회.

> `hypothesis = None`([`:19`](../alphaagent.py#L19))은 어디에도 쓰이지 않는 잔여 변수다.
> `idea`는 dict인데 `factor_agent.generate(description: str)`와 `idea_agent.generate(hypothesis: str)`에 그대로 넘어간다 — f-string에서 dict가 그대로 문자열화되어 프롬프트에 들어간다. 동작은 하지만 의도된 계약은 아니다.

---

## 4. 산출물과 AlphaEval로의 연결

- `alpha_agent_results.json` — 루프가 자동 저장하는 합격 수식 리스트. **커밋된 파일의 내용은 `[]`** 다.
- `alpha_agent.txt` — 실제 alpha pool로 보이는 수식 **9개**. 아래처럼 LLM 산출물 특유의 자유로운 window와 연산자 조합이 보인다.

  ```
  ($low - $high) / $close
  (($close - $high) / ($high - $low))
  (2 * $close - ($high + $low) / 2) / $open
  $high / Ref($close, 1)
  -Rank($high / $close, 10)
  $close / (Sum($close * $volume, 10) / Sum($volume, 10))
  WMA($close, 120) / $close
  WMA($low, 5) / $close
  (($close - Min($low, 15)) / (Max($high, 15) - Min($low, 15)))
  ```

평가 단계 연결은 GP 계열과 동일하다. `backtest/test.ipynb`가 요구하는 입력은 `factor_expressions`(문자열 리스트) + `weights`이므로:

```python
exprs = [l.strip() for l in open("Alphaagent/alpha_agent.txt") if l.strip()]
# backtest/combo.py 의 WeightCalculator 로 weights 산출 → AlphaEval(factor_expressions=exprs, weights=...)
```

---

## 5. 실제 로그로 확인한 동작

커밋된 `Alphaagent/test.log`(1,493줄)를 집계한 결과다.

| 항목 | 값 |
| --- | --- |
| 평가(라운드) 횟수 | 81 |
| `is_high_quality = True` | **5** |
| `is_high_quality = False` | 72 |
| `is_high_quality = None` (판정 실패) | 4 |
| 백테스트 예외 | 4 |

예외 내역과 원인:

| 메시지 | 횟수 | 원인 |
| --- | --- | --- |
| `'Index' object has no attribute 'year'` | 2 | factor 데이터가 join·dropna 후 **전부 비어** pnl 인덱스가 `DatetimeIndex`가 아니게 됨 → [`backtester.py:204`](../Alphaagent/backtester.py#L204)의 `.index.year` 실패 |
| `window must be an integer 0 or greater` | 2 | LLM이 **Qlib이 받지 않는 window**를 생성 (실수·음수 등) |

즉 실측 합격률은 **81라운드 중 5건(약 6%)** 이다. LLM이 만든 수식이 Qlib 수준에서 거절되거나 데이터가 비는 경우도 실제로 발생한다.

`test_time.log`에는 단계별 소요 시간이 남아 있다(예: `[FactorAgent] Time taken: 1.18 seconds`). 병목은 Qlib 조회보다 **LLM 왕복 지연**이다.

---

## 6. 알려진 문제 / 실행 전 확인 사항

### 6.1 반드시 수정해야 하는 것

1. **OpenAI API 키** — [`alphaagent.py:12`](../alphaagent.py#L12)의 `openai.api_key = "<Your API Key>"`가 플레이스홀더다.
2. **Qlib 경로** — [`alphaagent.py:13`](../alphaagent.py#L13)은 다른 스크립트와 달리 `~/.qlib/qlib_data/cn_data`로 하드코딩되어 있다. 저장소의 다른 파일들이 쓰는 `path/to/your/qlib_data` 규칙과 다르므로 실제 데이터 경로로 맞춰야 한다.
3. **`expressions[20:]` 슬라이스** ([`:63`](../alphaagent.py#L63)) — 37개 seed 중 **뒤 17개만** 돈다. 중단된 실행을 이어받은 흔적으로 보인다. 전체를 돌리려면 `expressions`로 바꿔야 한다.

### 6.2 구조적으로 주의할 점

- **결과가 마지막에 한 번만 저장된다** — `json.dump`가 루프 밖에 있으므로 중간에 죽으면 그 세션의 성과가 전부 사라진다. 게다가 이 줄은 `if __name__ == "__main__":` **블록 밖**(들여쓰기 0)에 있어서, `alphaagent`를 import만 해도 `alpha_agent_results.json`이 `[]`로 덮어써진다. 커밋된 파일이 `[]`인 이유로 설명될 수 있다.
- **FactorAgent의 재시도 상한이 동작하지 않는다** ([`factor_agent.py:45-65`](../Alphaagent/agents/factor_agent.py#L45-L65)) — `try_times = 0`이 `try` 블록 앞에서 초기화되고 재시도는 `return self.generate(description)` 재귀로 이루어지므로, 재귀 호출마다 카운터가 0으로 리셋된다. `try_times < 5` 조건은 절대 거짓이 되지 않아 **API 장애 시 재귀 한계까지 무한 재시도**한다.
- **재현성이 없다** — LLM `temperature`가 1.0/0.3/0.4이고 seed 고정 수단이 없다. 동일 커밋·동일 데이터에서도 매 실행 결과가 달라진다. GP 계열의 `random_state`에 대응하는 개념이 없다.
- **합격 기준이 LLM 판단**이라 재현성·일관성이 코드 임계값보다 약하다. 엄격한 비교 실험이 필요하면 `perf`를 코드에서 직접 임계값 판정하는 편이 낫다.
- **`is_high_quality`가 `None`이면 불합격으로 처리**된다(`if result["is_high_quality"]`) — 판정 실패와 진짜 불합격이 구분되지 않는다.
- **EvalAgent의 기본 `instruments`가 `["CSI300"]`** ([`eval_agent.py:71`](../Alphaagent/agents/eval_agent.py#L71)) — 지수 코드 문자열 리터럴이라 종목 리스트로는 유효하지 않다. `alphaagent.py`는 `D.instruments(market='all')`을 명시적으로 넘기므로 이 기본값 경로를 타지 않는다.
- **AST 유사도는 라벨 타입만 본다** — `ASTNodeWrapper.label`이 `type(node).__name__`이므로 `$close`와 `$volume`은 둘 다 `Name`으로 같게 취급된다. 즉 "구조가 같고 입력만 다른" 수식은 유사도가 매우 높게 나온다. 이는 의도된 보수적 중복 억제로 볼 수도 있으나, 값 기반 상관도와는 의미가 다르다는 점을 기억해야 한다.
- **`load_data()`에는 예외 대체 경로가 없다** — GP 계열은 실패한 수식을 `$close`로 조용히 대체하지만, 여기서는 예외가 그대로 올라가 `EvalAgent`가 `is_valid=False`로 기록한다. (실패가 로그에 남는다는 점에서는 오히려 낫다.)

---

## 7. 한 장 요약

```
seed 수식 37개 (Alpha101 스타일, 하드코딩)   ── 현재는 [20:] 슬라이스로 17개만
   │
   ▼  ┌─ seed 하나당 최대 3라운드 ───────────────────────────────────┐
   │  │ IdeaAgent   (gpt-4o, t=1.0)  가설 + 자연어 factor 설명 (JSON) │
   │  │ FactorAgent (gpt-4o, t=0.3)  → Qlib 수식 문자열 + Python AST  │
   │  │ Backtester  (코드)           long/short 상하위 20%, 비용 0.15%│
   │  │                              AnnRet·Sharpe·IC·RankIC·MaxDD   │
   │  │ EvalAgent   (gpt-4o, t=0.4)  AnnRet·IC·AST유사도 3개만 보고   │
   │  │                              합격 여부를 LLM이 판정            │
   │  │   합격 → 풀에 추가 / 불합격 → 자연어 리포트를 IdeaAgent에 되먹임│
   │  └──────────────────────────────────────────────────────────────┘
   ▼
alpha_agent.txt (수식 9개) / alpha_agent_results.json
   ▼
backtest/combo.py → weights → backtest/modeltester.py (AlphaEval)
```

한 문장으로: **AlphaAgent는 population과 적합도 기울기를 LLM의 사전지식과 자연어 비평으로 대체한 생성기**다. 수식 다양성은 값 상관도가 아니라 **AST 구조 유사도**로, 채택 여부는 임계값이 아니라 **LLM 판정**으로 결정된다. 그 대가로 재현성이 없고 라운드당 비용이 LLM 호출에 지배된다.
