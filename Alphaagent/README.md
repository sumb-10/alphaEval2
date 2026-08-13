# AlphaAgent

AlphaEval의 formula alpha mining baseline 중 하나. 유전 알고리즘 대신 **LLM 멀티에이전트**가 가설을 세우고 수식을 만들고 백테스트 리포트를 읽어 스스로 개선한다.

- 엔트리포인트: [`../alphaagent.py`](../alphaagent.py)
- 코드 레벨 상세 분석: [`../docs/AboutAlphaAgent.md`](../docs/AboutAlphaAgent.md)

> 디렉토리 이름은 `Alphaagent`(두 번째 a가 소문자)다. `from Alphaagent.agents...`로 import하므로 대소문자를 바꾸면 깨진다.

---

## 1. 알고리즘

### 1.1 전체 구조

GP 계열 baseline이 "population을 IC로 진화시키는" 방식이라면, AlphaAgent는 **한 번에 하나의 factor를 놓고 생성 → 검증 → 비평 → 재생성 루프를 도는** 방식이다.

```
seed 수식 37개 (Alpha101 스타일, alphaagent.py에 하드코딩)
      │   seed 하나씩 순회
      ▼
┌─ 최대 3라운드 ────────────────────────────────────────────────────┐
│                                                                    │
│  ① IdeaAgent      (gpt-4o, temperature 1.0)                       │
│     seed 수식을 "영감"으로 삼아 시장 가설 + factor 설명을 생성      │
│     출력: { "hypothesis": ..., "description": ... }   (JSON)       │
│                    │                                               │
│  ② FactorAgent    (gpt-4o, temperature 0.3)                       │
│     자연어 설명 → Qlib 수식 문자열 + Python AST                     │
│     프롬프트에 허용 feature/연산자 사양을 박아 문법을 강제           │
│                    │                                               │
│  ③ FactorBacktester  (코드, Qlib)                                  │
│     상위 20% 롱 / 하위 20% 숏, 편도 거래비용 0.15%                  │
│     AnnRet · AnnTurn · Sharpe · IC · RankIC · MaxDD · Fitness       │
│                    │                                               │
│  ④ EvalAgent      (gpt-4o, temperature 0.4)                       │
│     AnnRet(total) · IC(total) · 기존 합격 factor와의 AST 유사도     │
│     → 이 3개만 LLM에 넘겨 summary / recommendation / 합격여부 판정  │
│                    │                                               │
│     합격  → 풀에 저장하고 다음 seed로                                │
│     불합격 → summary + recommendation(자연어)을 ①에 되먹임해 재시도  │
└────────────────────────────────────────────────────────────────────┘
      ▼
alpha_agent.txt / alpha_agent_results.json  →  AlphaEval
```

### 1.2 탐색을 이끄는 세 가지 장치

**(a) seed 기반 시작점.** [`../alphaagent.py:20-58`](../alphaagent.py#L20-L58)에 손으로 쓴 기본 factor 37개(모멘텀·반전·변동성·거래량·위치 등)가 있다. LLM은 "이 예시를 반복하지 말고 영감으로 삼아라"라는 지시를 받으므로, seed는 탐색 공간의 **시작 방향**을 정하는 역할을 한다.

**(b) 자연어 되먹임이 적합도 기울기를 대신한다.** 불합격 시 `summary + recommendation` 문자열이 다음 IdeaAgent 호출에 들어가고, 이때는 별도의 `system_prompt_enhance`가 쓰인다 — "(A) 기존 factor를 개선하거나 (B) 폐기하고 새 아이디어를 내라". 수치 기울기가 아닌 **비평 텍스트**가 개선 신호다.

**(c) AST 구조 유사도로 중복을 억제한다.** 값의 상관계수를 쓰는 GP 계열과 달리, 수식을 Python AST로 파싱해 **최대 공통 부분트리** 크기를 비교한다 ([`agents/eval_agent.py:10-61`](agents/eval_agent.py#L10-L61)).

```
similarity = (최대 공통 부분트리 노드 수) / ((트리1 노드 수 + 트리2 노드 수) / 2)
```

이 값이 LLM에게 `"Similarity to Previous"`로 전달되고, 프롬프트는 "낮을수록 좋다"고 알려 준다. 비교 대상은 **이미 합격한 factor들**뿐이다.

### 1.3 탐색 공간 — GP baseline과 다르다

FactorAgent의 프롬프트가 사실상 탐색 공간 정의다 ([`agents/factor_agent.py:12-30`](agents/factor_agent.py#L12-L30)).

| | gplearn / AutoAlpha (`config.py`) | **AlphaAgent (프롬프트)** |
| --- | --- | --- |
| feature | 10개 (`$vwap`, `$amount`, `$change`, `$adjclose`, `$factor` 포함) | **5개** (`$open $high $low $close $volume`) |
| 2변수 시계열 연산 | `Corr`/`Cov` **제외**(arity 규약 문제로 주석 처리) | **`Corr(x,y,d)`, `Cov(x,y,d)` 사용 가능** |
| `Rank` | 없음 | **있음** |
| rolling window | `[5, 12, 30, 64]`로 고정 | **임의 정수** (실제 산출물에 `WMA($close, 120)`) |
| 산술 표기 | `Add(a, b)` 함수 형태 | `(a + b)` 중위 표기도 자유롭게 사용 |
| 깊이 제한 | 세대/`init_depth`로 통제 | 없음 |

즉 AlphaAgent는 GP baseline이 못 만드는 수식(2변수 상관, 임의 window)을 만들 수 있고, 반대로 window가 통제되지 않아 비교 실험 시 조건이 달라진다는 점을 감안해야 한다.

### 1.4 합격 판정은 코드가 아니라 LLM이 한다

EvalAgent의 system prompt에 기준이 문장으로 들어 있다 ([`agents/eval_agent.py:120`](agents/eval_agent.py#L120)).

> "When the annual return > 10% and IC > 0.03, it is considered a high-quality factor. The similarity the lower, the better."

임계값 비교를 하는 `if`문은 없다. LLM이 `is_high_quality: true/false`를 반환하고 파이프라인은 그것을 따른다. 또한 백테스터가 계산한 `Sharpe`, `MaxDD`, `RankIC`, `AnnTurn`, `Fitness`는 **LLM에게 전달되지 않는다** — 판정에 쓰이는 값은 `AnnRet`, `IC`, `Similarity` 3개뿐이다.

### 1.5 백테스트 지표 정의

[`backtester.py`](backtester.py). 연도별 + 전체(`total`)로 집계한다.

| 지표 | 정의 |
| --- | --- |
| `AnnRet` | `(1 + 누적수익)^(252/n) - 1` |
| `AnnTurn` | 일별 turnover 평균 |
| `Sharpe` | `mean(pnl) / std(pnl) × √252` |
| `IC` | 일별 cross-sectional Pearson IC의 평균 |
| `RankIC` | 일별 cross-sectional Spearman IC의 평균 |
| `MaxDD` | 누적 수익 곡선의 최대 낙폭 |
| `Fitness` | `Sharpe × √|AnnRet / AnnTurn|` |

일별 손익은 `pnl = (롱 평균수익 + (-숏 평균수익)) / 2 - turnover × 0.0015`. label은 익일 수익률 `Ref($close, -1)/$close - 1`이다.

---

## 2. 실행 방법

### 2.1 사전 준비

```bash
pip install -r ../requirements.txt
pip install openai                       # requirements.txt에 없다 — 별도 설치 필요
```

**실행 전 반드시 고쳐야 하는 3곳:**

| # | 위치 | 내용 |
| --- | --- | --- |
| 1 | [`../alphaagent.py:12`](../alphaagent.py#L12) | `openai.api_key = "<Your API Key>"` → 실제 키. 환경변수(`OPENAI_API_KEY`)로 빼는 편이 안전하다 |
| 2 | [`../alphaagent.py:13`](../alphaagent.py#L13) | `provider_uri="~/.qlib/qlib_data/cn_data"` → 실제 Qlib 데이터 경로. (다른 스크립트들의 `path/to/your/qlib_data`와 규칙이 다르다) |
| 3 | [`../alphaagent.py:63`](../alphaagent.py#L63) | `for example in expressions[20:]` — **37개 seed 중 뒤 17개만** 돈다. 전체를 돌리려면 `expressions`로 바꾼다 |

### 2.2 실행

**저장소 루트에서** 실행한다 (`from Alphaagent.agents...` 상대 import 때문).

```bash
cd /path/to/AlphaEval
python alphaagent.py
```

CLI 인자는 없다. 모든 설정은 `alphaagent.py`를 직접 편집해서 바꾼다.

진행 상황은 표준출력으로 나온다(`📌 IdeaAgent` / `🧮 FactorAgent` / `📊 EvalAgent` / `✅ Is High Quality?`). 실행이 길기 때문에 로그를 남겨 두는 것이 좋다.

```bash
python alphaagent.py 2>&1 | tee Alphaagent/run_$(date +%Y%m%d).log
```

산출물:

| 파일 | 내용 |
| --- | --- |
| `alpha_agent_results.json` | 파이프라인이 자동 저장하는 **합격 수식 리스트** (루프 종료 후 한 번만 기록) |
| `alpha_agent.txt` | 정리된 최종 alpha pool (현재 커밋본에 수식 9개). 평가 단계에 이 파일을 쓴다 |

### 2.3 산출물 → AlphaEval 평가로 넘기기

```python
exprs = [l.strip() for l in open("Alphaagent/alpha_agent.txt") if l.strip()]
# 1) backtest/combo.py 의 WeightCalculator 로 결합 weights 산출
# 2) backtest/test.ipynb 처럼 AlphaEval(factor_expressions=exprs, weights=w, ...) 실행
```

### 2.4 실제 실행 결과 참고치

커밋된 `test.log`(1,493줄)를 집계한 수치다.

| 항목 | 값 |
| --- | --- |
| 총 평가 라운드 | 81 |
| 합격(`True`) | **5** |
| 불합격(`False`) | 72 |
| 판정 실패(`None`) | 4 |
| 백테스트 예외 | 4 (`'Index' object has no attribute 'year'` 2건, `window must be an integer 0 or greater` 2건) |

합격률은 약 6%다. LLM이 만든 수식이 Qlib에서 거절되거나 데이터가 비는 경우도 실제로 발생한다.

**비용 추정**: seed 하나당 최대 `3라운드 × 3콜 = 9회` LLM 호출 + 최대 3회 백테스트. 현재 슬라이스(17 seed) 기준 최대 **153회 LLM 호출**, seed 37개 전체면 최대 **333회**. 병목은 Qlib 조회가 아니라 LLM 왕복 지연이다.

---

## 3. 조건을 바꾸는 방법

CLI가 없으므로 전부 파일 편집이다.

### 3.1 `../alphaagent.py`

| 무엇 | 위치 | 방법 |
| --- | --- | --- |
| **seed 수식 집합** | `expressions = [...]` ([`:20-58`](../alphaagent.py#L20-L58)) | 리스트를 직접 교체. 탐색의 시작 방향을 정하는 가장 강력한 손잡이다 |
| **탐색할 seed 범위** | `expressions[20:]` ([`:63`](../alphaagent.py#L63)) | 전체는 `expressions`, 빠른 확인은 `expressions[:3]` |
| **라운드 상한** | `max_rounds = 3` ([`:69`](../alphaagent.py#L69)) | 늘리면 개선 기회↑ 비용↑ |
| **마이닝 구간** | `EvalAgent(start_date=..., end_date=...)` ([`:62`](../alphaagent.py#L62)) | 기본 `2010-01-01 ~ 2019-12-31` (GP baseline과 동일 조건) |
| **종목 유니버스** | 같은 줄 `instruments=D.instruments(market='all')` | `market='csi300'` 등 |
| **주기** | 같은 줄 `freq="day"` | |
| **결과 파일명** | [`:97`](../alphaagent.py#L97) `alpha_agent_results.json` | |

### 3.2 LLM 설정

| 무엇 | 위치 | 비고 |
| --- | --- | --- |
| IdeaAgent 모델/온도 | [`agents/idea_agent.py:6`](agents/idea_agent.py#L6) | 기본 `gpt-4o`, `temperature=1.0` — 아이디어 다양성 담당. 낮추면 비슷한 아이디어가 반복된다 |
| FactorAgent 모델/온도 | [`agents/factor_agent.py:7`](agents/factor_agent.py#L7) | 기본 `gpt-4o`, `temperature=0.3` — 문법 준수 담당. 올리면 Qlib 파싱 실패가 늘어난다 |
| EvalAgent 모델/온도 | [`agents/eval_agent.py:66`](agents/eval_agent.py#L66) | 기본 `gpt-4o`, `temperature=0.4` |
| **가설 생성 프롬프트** | [`agents/idea_agent.py:9-31`](agents/idea_agent.py#L9-L31) | `system_prompt_new`(신규) / `system_prompt_enhance`(개선) 두 개 |
| **탐색 공간(연산자·feature)** | [`agents/factor_agent.py:12-30`](agents/factor_agent.py#L12-L30) | 여기를 GP의 `config.py`와 맞추면 baseline 간 비교 조건이 정렬된다 |
| **합격 기준** | [`agents/eval_agent.py:116-128`](agents/eval_agent.py#L116-L128) | 프롬프트 문장(`AnnRet > 10%`, `IC > 0.03`)을 수정. 재현성이 중요하면 이 판정을 코드 `if`문으로 옮기는 편이 낫다 |
| **LLM에 넘기는 지표** | [`agents/eval_agent.py:99`](agents/eval_agent.py#L99) | 현재 `AnnRet`/`IC`/`Similarity` 3개뿐. `Sharpe`, `MaxDD` 등을 추가할 수 있다 |

### 3.3 백테스트 조건

| 무엇 | 위치 | 비고 |
| --- | --- | --- |
| 롱/숏 분위수 | [`backtester.py:109-110`](backtester.py#L109-L110) | `0.2`가 **하드코딩**되어 있다. 생성자의 `long_threshold`/`short_threshold` 인자는 저장만 되고 사용되지 않으므로, 값을 바꾸려면 이 두 줄을 고쳐야 한다 |
| 거래비용 | [`backtester.py:130`](backtester.py#L130) | `0.0015` (편도 0.15%) |
| label(예측 대상) | [`backtester.py:76`](backtester.py#L76) | `Ref($close, -1)/$close - 1` (익일 수익률) |
| 연율화 기준일수 | [`backtester.py:172-177`](backtester.py#L172-L177) | `252` |

### 3.4 GP baseline과 동일 조건으로 비교하려면

AlphaEval의 다른 baseline과 공정하게 비교하려면 최소 다음 4가지를 맞춰야 한다.

1. **기간** — `EvalAgent(start_date, end_date)`를 GP의 `--start_time/--end_time`과 일치시킨다.
2. **유니버스** — 양쪽 모두 `D.instruments(market='all')`.
3. **탐색 공간** — FactorAgent 프롬프트의 feature/연산자/window를 `gplearn/config.py`에 맞춘다 (feature 5개↔10개, window 자유↔`[5,12,30,64]`가 특히 크게 다르다).
4. **최종 alpha 개수** — GP는 `--n_components`로 개수를 고정하는데, AlphaAgent는 합격한 만큼만 나온다. 비교 시에는 개수를 동일하게 잘라 주는 것이 좋다.

---

## 4. 알려진 문제

> 아래는 코드를 읽고 확인한 사항이다. 이 문서는 코드를 수정하지 않는다. 근거는 [`../docs/AboutAlphaAgent.md`](../docs/AboutAlphaAgent.md) 6절에 정리해 두었다.

- **결과가 마지막에 한 번만 저장된다.** `json.dump`가 루프 밖에 있어 중간에 죽으면 그 세션 성과가 전부 사라진다. 게다가 이 줄은 `if __name__ == "__main__":` **블록 밖**(들여쓰기 0)에 있어서 `alphaagent`를 import만 해도 `alpha_agent_results.json`이 `[]`로 덮어써진다. 커밋된 파일이 `[]`인 이유로 설명될 수 있다. → 라운드마다 append 저장하도록 바꾸는 것을 권한다.
- **FactorAgent의 재시도 상한이 동작하지 않는다.** `try_times = 0`이 `try` 앞에서 초기화되는데 재시도는 `return self.generate(description)` 재귀로 이루어져 카운터가 매번 0으로 리셋된다. `try_times < 5` 조건이 거짓이 되지 않아 **API 장애 시 재귀 한계까지 무한 재시도**한다.
- **재현성이 없다.** LLM `temperature`가 1.0/0.3/0.4이고 seed 고정 수단이 없다. 같은 커밋·같은 데이터에서도 매번 결과가 달라진다. GP의 `random_state`에 대응하는 개념이 없다.
- **`is_high_quality`가 `None`이면 불합격으로 처리된다** (`if result["is_high_quality"]`). LLM 판정 실패와 진짜 불합격이 구분되지 않는다.
- **IdeaAgent의 JSON 파싱 실패가 조용히 넘어간다.** `parse_response`가 실패 시 `{"hypothesis": "", "description": ""}`을 반환하므로, 빈 아이디어로 FactorAgent가 호출된다. 또한 `{`~`}` 잘라내기 전처리가 `enhance` 경로에만 있어 신규 생성 경로가 코드 펜스에 더 취약하다.
- **AST 유사도는 노드 타입만 비교한다.** `label = type(node).__name__`이라서 `$close`와 `$volume`은 둘 다 `Name`으로 동일 취급된다. "구조는 같고 입력만 다른" 수식의 유사도가 매우 높게 나온다.
- **불합격 factor는 유사도 비교 대상에 들어가지 않는다.** `results_ast`에는 합격분만 쌓이므로, 계속 탈락하는 비슷한 수식들이 반복 생성될 수 있다.
- **EvalAgent 기본 `instruments`가 `["CSI300"]`** — 종목 리스트로는 유효하지 않은 지수 코드 문자열이다. `alphaagent.py`는 `D.instruments(market='all')`을 명시적으로 넘기므로 이 경로를 타지 않는다.
- **`hypothesis = None`** ([`../alphaagent.py:19`](../alphaagent.py#L19))은 사용되지 않는 잔여 변수다.
- **`idea`는 dict인데 `str` 파라미터로 전달된다.** f-string에서 dict가 그대로 문자열화되어 프롬프트에 들어간다 — 동작은 하지만 의도된 계약은 아니다.

---

## 5. 디렉토리 구성

| 파일 | 역할 |
| --- | --- |
| [`agents/idea_agent.py`](agents/idea_agent.py) | 시장 가설 + factor 아이디어 생성 (신규 / 개선 두 프롬프트) |
| [`agents/factor_agent.py`](agents/factor_agent.py) | 자연어 → Qlib 수식 문자열 + Python AST |
| [`agents/eval_agent.py`](agents/eval_agent.py) | 백테스트 실행 + AST 유사도 + LLM 합격 판정 |
| [`backtester.py`](backtester.py) | `FactorBacktester` — long/short 백테스터, 성과 지표 산출 |
| `alpha_agent.txt` | 최종 alpha pool (수식 9개) |
| `alpha_agent_results.json` | 파이프라인 자동 저장 결과 (현재 `[]`) |
| `test.log`, `test_time.log` | 과거 실행 로그 (결과·소요시간 참고용) |

의존성: `openai`, `qlib`, `pandas`, `numpy`. `agents/` 디렉토리에 `__init__.py`가 없지만 Python 3의 암시적 namespace package로 동작한다.
