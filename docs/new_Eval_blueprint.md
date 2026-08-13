# new_Eval_blueprint — OOS Evaluation + QD Behavioral Analysis 설계 조사

AlphaEval codebase 기반으로 (A) train/test 분리 OOS 평가, (B–D) QD behavioral
descriptor 파이프라인을 설계하기 위한 **코드 조사 보고서**다. 코드는 아직
수정하지 않았고, 각 답변에 file/class/function 근거를 달았다.

각 항목 태그: **[가능]** 현재 코드/데이터로 즉시 가능 · **[신규]** 데이터는
충분하나 코드 신규 구현 필요 · **[데이터필요]** 현재 번들로 불가능.

조사 환경: conda `AlphaEval38`(qlib 0.9.0, pandas 1.5.3, sklearn 1.3.2),
데이터 `/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data`.

---

# A. Out-of-sample alpha evaluation

## Q1. 지표별 재사용 가능한 class/function

| 지표 | 재사용 대상 | 근거 | 태그 |
|---|---|---|---|
| IC | `backtest/ictester.py` `ICBacktester.calculate1()` (66-82행): 일별 cross-sectional Pearson → 평균. `backtest/modeltester.py` `AlphaEval.run()` 300-302행도 동일 패턴 | signed IC 반환 | [가능] |
| RankIC | `ictester.py` `calculate2()` (84-99행), `modeltester.py` 303-305행: `x["factor"].rank().corr(x["label"].rank())` | | [가능] |
| **ICIR** | **어디에도 없음.** 단, 재료인 일별 `ic_series`는 위 두 곳에서 이미 생성 → `ic_series.mean()/ic_series.std()` 한 줄 추가 | | [신규] |
| AnnRet | `Alphaagent/backtester.py` `FactorBacktester.calculate_performance()` 172행 | Q3 참조 | [가능] |
| Sharpe | 같은 곳 176-178행 | | [가능] |
| MaxDD | 같은 곳 183-185행 | | [가능] |
| Turnover | ① `modeltester.py` `calculate_pnl()` 181-190행 ② `Alphaagent/backtester.py` 120-129행 (동일 로직) | Q2 참조 | [가능] |
| 값 행렬 배치 계산 | `D.features(instruments, [f1..fN], ...)` — `modeltester.fetch_data()` 59-65행, `combo.py fetch_data()` 44-49행이 실사용. 또는 `scripts/tensor_eval.py` `TensorEvaluator.frame(expr)` | Q6 참조 | [가능] |
| pool 가중치 | `backtest/combo.py` `WeightCalculator.fit()` | Q5 참조 | [가능] |
| pool 결합 | `modeltester.py` 149행 `self.alphacombo = self.factor_data.dot(self.weights)` (일별 z-score 후 선형결합) | | [가능] |

개별 alpha와 pool combination 모두 "factor 시계열 1개 → 지표 7개" 구조가 같으므로
**동일한 집계 함수를 재사용**할 수 있다 (pool은 결합 시계열을 넣으면 됨).

## Q2. `modeltester.calculate_pnl()`의 portfolio construction (158-200행)

| 항목 | 동작 | 근거 행 |
|---|---|---|
| 종목 선택 | `long_cut = f.quantile(1-0.2)`, `short_cut = f.quantile(0.2)` — **상위 20% 롱 / 하위 20% 숏**, 경계 포함(`>=`, `<=` — quantile 동값이면 20%보다 많아질 수 있음) | 170-174 |
| 가중 | **equal-weight** — `l[f >= long_cut].mean()` (동일가중 평균수익) | 176-177 |
| 리밸런스 | **매 거래일** (일별 groupby 루프) | 166 |
| 비용 | `cost = turnover * 0.0015` — 편도 0.15%를 turnover 비율에 곱해 차감 | 192-193 |
| turnover 정의 | (롱 진입+롱 이탈+숏 진입+숏 이탈 **종목 수**) ÷ (직전 롱+숏 보유 종목 수). 집합 기반(가중치 무관), 종목 전면 교체 시 최대 2.0 | 181-190 |
| pnl 단위 | `(long_ret + short_ret)/2` = **일간 수익률(fraction)**. 숏은 `-l.mean()` | 176-178 |
| 결측 처리 | `alphacombo.join(label, how="inner").dropna()` — factor 또는 label이 NaN인 (종목,일)은 **그날 유니버스에서 제외** | 160 |
| 기타 | 첫날 turnover=NaN, `market_mean`(그날 유니버스 평균수익)도 기록. `calculate_pnl()`은 내부에서 `fetch_data()`를 다시 호출(159행) — `run()`과 같이 쓰면 이중 페치 | 159, 181, 194 |

주의: 생성자에 `long_threshold/short_threshold` 같은 파라미터는 없고
`Alphaagent/backtester.py`에는 있으나 **미사용**(0.2 하드코딩, 109-110행) —
동일 계열 코드의 알려진 함정.

## Q3. `FactorBacktester`의 계산식 (Alphaagent/backtester.py 141-221행)

```python
cum_ret = pnl_s.add(1).prod() - 1
ann_ret = (1 + cum_ret) ** (252 / n) - 1          # ← compounded CAGR (mean×252 아님!)
sharpe  = pnl_s.mean() / pnl_s.std(ddof=1) * np.sqrt(252)
ann_turn = to_s.mean()                             # 일 turnover 평균 (연환산 아님, 이름과 달리)
cum = pnl_s.add(1).cumprod()
max_dd = ((cum - cum.cummax()) / cum.cummax()).min()   # 누적곡선 기준 최대낙폭 (음수)
fitness = sharpe * (abs(ann_ret / ann_turn)) ** 0.5
```

- **Annualization은 compounded CAGR**: `(1+누적수익)^(252/n) - 1` (172행).
  `mean(return)*252`가 아니다.
- Sharpe는 일수익 기준 `mean/std(ddof=1) × √252` (176-178행), 무위험수익률 0 가정.
- Turnover 정의는 Q2와 동일 (120-129행).
- 연도별 + `total` 행으로 집계 (204-218행).
- 함정 2개: ① 첫날 `turnover=NaN`인데 `if turnover:`에서 NaN이 truthy →
  `cost=NaN` → **첫날 pnl이 NaN** (130-131행; pandas prod/std가 NaN을 skip해
  결과 왜곡은 작지만 `n=len(pnl_s)`에는 포함되어 CAGR 지수가 미세 편향).
  ② `AnnRet` 반환값은 연도별 테이블 기준 — OOS 평가에는 `total` 행 사용.

## Q4. |IC| fitness와 train IC sign의 행방

- sign 소실 지점: [`gplearn/_program.py:554`](../gplearn/_program.py#L554)
  `return abs(raw_fitness)` — `ICBacktester.calculate1()`은 **signed IC를
  반환**하지만 `raw_fitness()`가 절대값을 취한다. AutoAlpha도 동일
  (`AutoAlpha/_program.py` 같은 구조). 결과 CSV의 `IC` 컬럼 = `fitness_` = |IC|.
- **signed train IC는 이미 우리 러너의 memo에 살아 있다**:
  - [`scripts/fast_eval.py`](../scripts/fast_eval.py) `FastICEvaluator.ic_memo`
    — `evaluate()`가 signed IC를 저장하고, abs는 `make_fast_parallel_evolve`의
    `p.raw_fitness_ = abs(ic)` 시점에만 적용된다.
  - [`scripts/tensor_eval.py`](../scripts/tensor_eval.py) `TensorEvaluator.ic_memo` — 동일.
- **sign 고정 평가는 가능**: `sign = sign(train_IC)`를 train에서 결정해
  test에서 재결정하지 않는 방식은 `signed_factor = sign × factor` 로 즉시
  구현 가능하다 (IC/RankIC는 부호만 뒤집히고, 포트폴리오 지표는 롱숏 방향이
  결정되므로 sign이 필수).
- **수정 필요 지점** [신규]: 러너 2개(`scripts/run_gplearn_fast.py`,
  `run_gplearn_tensor.py`)의 저장부에서 `evaluator.ic_memo[formula]`를 조회해
  결과 CSV에 `signed_train_IC`(또는 `train_sign`) 컬럼을 추가하면 된다.
  원본(`gplearn/`) 무수정. 이미 끝난 run(883881/883882 등)은 memo가 없으므로
  train 구간에서 formula별 IC를 1회 재계산해 sign을 복원해야 한다
  (formula당 1 쿼리 — `TensorEvaluator.ic()`로 저렴).

## Q5. pool weight의 학습 기간과 freeze

- 학습 기간: [`backtest/combo.py`](../backtest/combo.py) `WeightCalculator.fit()`
  — 생성 시 받은 `start_date~end_date`(= `modeltester.AlphaEval.__init__` 38행이
  넘기는 **train_start_date~train_end_date**)의 데이터로만
  `differential_evolution`(maxiter=1, popsize=20)을 돌려 mean IC를 최대화한다.
  가중치는 `|w|` 합=1로 정규화, 각 wᵢ∈[-1,1].
- **freeze는 이미 구조적으로 보장**: `AlphaEval`은 test 구간에서 weight를
  재학습하지 않고 `self.weights`를 그대로 쓴다 (149행 `dot(self.weights)`).
  `weights=[...]`로 명시 주입도 가능(`backtest/test.ipynb` 방식) — 별도
  validation 구간에서 학습한 weight를 넘겨 얼리는 것도 인자만으로 된다. [가능]
- 주의: maxiter=1은 사실상 1세대 DE — 최적화 강도가 약하다(의도된 논문 설정).
  결정론이 필요하면 `differential_evolution(..., seed=...)`가 없으므로
  비재현(Q24 ⑤와 동류).

## Q6. formula list → date×instrument 값 행렬 batch 계산

세 가지가 이미 존재한다. [가능]

1. **qlib 자체**: `D.features(instruments, [f1..fN], start, end, freq="day")`
   → MultiIndex(instrument, datetime) × N컬럼 DataFrame.
   실사용처: `modeltester.fetch_data()` 59-65행(전체 formula 리스트를 한 번에),
   `combo.py fetch_data()` 44-49행. date×instrument 행렬은
   `df[f].unstack(level="instrument")` 한 줄.
2. **`scripts/fast_eval.py` `FastICEvaluator`**: chunk 단위 batch + `$close`
   폴백 + memo (IC까지 원본 비트 일치).
3. **`scripts/tensor_eval.py` `TensorEvaluator.frame(expr)`**: 패널 1회 적재 후
   formula당 0.3~4s로 **(date×instrument) float32 DataFrame을 직접 반환** —
   qlib과 37/37 비트 일치 검증됨(`scripts/verify_tensor_eval.py`).
   OOS 평가처럼 formula×기간이 많은 작업에는 이것이 최적.

## Q7. evaluator 설계 제안 (구현 위치)

원본 무수정 원칙에 따라 **`scripts/oos_eval.py` 신규 모듈**이 자연스럽다.
`backtest/`에 넣으면 원본 패키지를 건드리게 되고, `backtest/__init__.py`의
누락 모듈 문제(`backtest/backtester.py` 부재 — `ensure_backtest_importable()`로
우회 중)도 있다.

```python
# scripts/oos_eval.py (설계만 — 미구현)
class OOSEvaluator:
    def __init__(self, test_start, test_end, market, horizon=1):
        self.tev = TensorEvaluator(test_start, test_end, market)   # 값 행렬 공급자
        # forward return 행렬, 지수 수익률 등 사전 준비

    def evaluate_factor(self, formula, sign=+1) -> dict:
        F = sign * self.tev.frame(formula)          # (date×inst), train_sign 적용
        return self._metrics(F)                     # IC/RankIC/ICIR/AnnRet/Sharpe/MDD/Turnover

    def evaluate_pool(self, formulas, weights) -> dict:
        Z = daily_zscore([self.tev.frame(f) for f in formulas])    # modeltester.zscore 이식
        combo = Σ wᵢ·Zᵢ                                            # modeltester 149행과 동일
        return self._metrics(combo)

    def _metrics(self, F):
        # IC/RankIC: ictester.calculate1/2 의 일별 corr 집계 이식
        # ICIR: ic_series.mean()/ic_series.std()  (신규)
        # AnnRet/Sharpe/MDD/Turnover: FactorBacktester.calculate_performance 집계식 이식
        #   (import 재사용도 가능하나 첫날 NaN cost 버그가 있어 이식+수정 권장)
```

- 포트폴리오 구성은 Q2의 20/20 quantile·equal-weight·0.15% 비용을 그대로
  이식(비교 가능성 유지)하되, threshold를 인자화.
- `evaluate_factor`는 반드시 `sign`을 받게 해 **sign 결정을 평가기 밖(train)**
  에 둔다 — Q24 leakage 규칙.

---

# B. QD Behavioral Descriptor용 데이터 확인

## Q8. 사용 가능한 raw field — 디스크 전수 확인 완료

`features/` 전체 6,016 디렉토리에 대해 known-10 필드 제외 `find` 결과 **0건**
— 번들에는 정확히 아래 10개 필드만 존재한다:

| field | 존재 | 비고 |
|---|---|---|
| $open $high $low $close | ✓ | |
| $volume | ✓ | 주 수량 |
| **$amount** | ✓ | **거래대금 (turnover value)** — 유동성 계산에 직접 사용 가능 |
| $vwap $adjclose $change $factor | ✓ | factor = 수정계수 (주식수 아님) |
| **market capitalization** | **✗** | mkt_cap/total_share/float_share/turnover_rate 계열 파일 전무 |
| **benchmark/index** | **✓** | `features/sh000300`(CSI300), `sh000905`(CSI500), `sh000852`(CSI1000), `sh000906`(CSI800), `sh000985`(CSIAll), `sz399300` — 10필드 완비, 2005-01-04~2026-01-09. `instruments/all.txt`에도 등재되어 `D.features(["SH000300"], ...)` 직접 조회 가능 (`modeltester.fetch_data()` 68-74행이 실사용). SH000001·SZ399001은 **없음** |
| universe membership | ✓ | `instruments/csi300·500·800·1000·csiall.txt` (편입 구간 포함), `D.list_instruments(D.instruments(market), ..., as_list=False)` → 종목별 span. `scripts/tensor_eval.py` `_build_universe_mask()`가 (date×inst) bool 마스크 구현체 |

## Q9. forward return 1/5/10/20d — [가능]

- 현재 label: **`Ref($close, -1)/$close - 1`** = 1일 선행 수익률(t 종가 → t+1 종가).
  정의 위치: `backtest/ictester.py:58` (수식 문자열은 gplearn label
  `(Ref($close,-1)-$close)/$close`(genetic.py 235-241행)와 표기만 다르고 동일),
  `modeltester.py:56`, `combo.py:34`, `Alphaagent/backtester.py:76` — 전부 동일.
- horizon k 확장: `Ref($close, -k)/$close - 1` (k=1,5,10,20) — qlib이 우측
  extended window로 처리하므로 즉시 가능. `TensorEvaluator`로는
  `close.shift(-k)/close - 1` 한 줄 (label 계산부 199-205행과 동일 패턴).
- 주의 2개: ① k>1은 **overlapping return** — 일별 IC 시계열에 자기상관이 생겨
  ICIR·t-stat이 부풀므로 fingerprint 용도로는 무방하나 유의성 주장에는
  비중첩 샘플링/보정 필요. ② 데이터 끝(2026-01) 근처 k일은 NaN — 2010–2019/
  2021–2024 구간에선 문제없음.

## Q10. Volatility regime용 benchmark 시계열 — [가능]

`SH000300`(CSI300) 일봉이 번들에 있으므로 **지수 수익률의 rolling σ로 regime을
직접 만들 수 있다**. universe별 매칭도 가능: csi300↔SH000300, csi500↔SH000905,
csi800↔SH000906, csi1000↔SH000852, all↔SH000985(CSI All Share).
universe aggregate return 대용은 불필요하다(원하면 label 행렬의 일별
cross-sectional mean으로도 계산 가능 — `calculate_pnl()`의 `market_mean`이
같은 개념, modeltester 179행).
**regime 경계(예: σ tercile)는 train 구간에서 캘리브레이션해 test에 적용**해야
leakage가 없다(§Q24).

## Q11. Market direction 분할 — [가능]

`ret_bench(t) = Ref($close,-1)/$close - 1` 을 SH000300에 적용해
`>0 / <0` 마스크로 일별 분할 — 즉시 가능. (0인 날의 처리 규칙만 정의 필요.
참고로 노이즈 분산 캘리브레이션에 지수 close를 쓰는 선례가
`modeltester.fetch_data()` 68-83행에 있다.)

## Q12. Size Response — [데이터필요] ✗

**market cap 데이터가 없다.** 시가총액 = 주가 × 발행주식수인데 발행주식수
(total/float share) 필드가 전무하고 `$factor`는 가격 수정계수라 대용 불가.
따라서 **현재 번들만으로 size descriptor는 구현할 수 없다.**

- 대안 1(정공법): baostock/AkShare에서 total_share 시계열을 받아
  `qlib_dump_bin.py`(data_collection/)로 필드 추가 덤프 → `$close × $totalshare`.
- 대안 2(비권장): 가격 수준·ADV를 proxy로 쓰는 것 — 이는 **liquidity(Q13)와
  강하게 혼재**되어 fingerprint의 S축과 L축이 사실상 중복되므로, S축은
  데이터 확보 전까지 **비워두는 것을 권장**한다 (5차원 → 4차원 운용).

## Q13. Liquidity descriptor — [가능]

`$amount`(거래대금)가 직접 존재하므로 proxy가 필요 없다:
- **ADV20 = `Mean($amount, 20)`** — qlib 표현식 한 줄, 또는 TensorEvaluator로
  rolling mean.
- `$close × $volume`도 계산 가능하지만 `$amount`가 있으니 불필요
  (참고: AlphaAgent 산출물에 `Sum($close*$volume,10)/Sum($volume,10)` 같은
  VWAP식 사용례 존재).
- 일별 cross-sectional percentile: `adv20.rank(axis=1, pct=True)` — 신규 코드 한 줄.

---

# C. 추가 behavioral descriptor

## Q14. 일별 z-score / portfolio weight 변환 기존 코드 — [가능]

- **일별 cross-sectional z-score**: `modeltester.py` `zscore()`(15-19행) +
  `groupby(level=1, group_keys=False).apply(zscore)`(124-147행) — level 1 =
  datetime이므로 정확히 일별 단면 z-score. `combo.py` 57-69행에 동일 사본.
  (dense 행렬 기준으로는 `(F - F.mean(axis=1)) / F.std(axis=1)` 벡터화가 등가.)
- **portfolio weight 변환**: 명시적 weight 벡터를 만드는 코드는 없고,
  `calculate_pnl()`(modeltester 166-178행)이 상/하위 20% **집합 선택 +
  equal-weight**라는 암묵적 가중을 쓴다. z-score 비례 가중(`w ∝ z/Σ|z|`)은
  [신규]지만 재료(z-score 행렬)는 위에서 나온다.

## Q15. Effective breadth (N_eff) — [신규, 데이터 충분]

수식 그대로 구현 가능하고 수치적으로도 안전하다:
`p_i = |w_i|/Σ|w_j|`, `N_eff = 1/Σp_i²` (Herfindahl 역수), `Breadth = N_eff/N`.
- w로 무엇을 쓰는지만 정의하면 된다 — 권장: 일별 z-score 비례 가중
  (Q14). quantile 선택 가중(calculate_pnl 방식)을 쓰면 Breadth가 항상
  ≈0.4(상하위 40% equal-weight)로 퇴화하므로 **z-비례 가중이 정보량 있음**.
- N = 그날 유효 종목 수(dropna 후) — 일별 계산 후 기간 평균.

## Q16. Turnover를 calculate_pnl 것으로 재사용? — 조건부 [가능]

- `calculate_pnl()`의 turnover(Q2)는 **집합 기반**(quintile 멤버십 churn)이라
  OOS 지표(F. factor_metrics의 Turnover)와 **동일 정의를 쓰면 일관성** 측면에서
  적절하다. 스왑=2 카운트·최대 2.0 스케일임을 문서화하면 됨.
- 단 Map 2(Turnover × Liquidity Footprint)의 behavioral 축으로는
  **weight 기반 turnover `0.5·Σᵢ|w_i(t) - w_i(t-1)|`** 가 더 매끄럽다
  (z-비례 가중과 정의가 맞물리고 연속적). → 권장: factor_metrics에는
  기존 정의(비교 가능성), descriptor에는 weight 기반 [신규] — 두 값을 모두 저장.

## Q17. Liquidity Footprint — [가능(신규 코드)]

`Σᵢ |w_i| × liquidity_percentile_i`: 필요한 재료 전부 존재 —
|w| (Q14/15), ADV20 percentile (Q13). 낮을수록 저유동성 종목에 베팅.
유의: percentile 방향(1=고유동성)과 결측일 처리(그날 유효 종목만)를 명시.

---

# D. Fingerprint → 2D QD space

## Q18. Fingerprint 계산에 필요한 intermediate data 정리

alpha 하나당 필요한 것 (전부 TensorEvaluator/D.features로 산출 가능):

| 재료 | 생성 방법 | 재사용 |
|---|---|---|
| ① signed factor 행렬 Z (date×inst, 일별 z-score) | `sign(train_IC) × TensorEvaluator.frame(f)` → 일별 z-score | tensor_eval + modeltester.zscore 이식 |
| ② forward return 행렬 R_k (k=1,5,10,20) | `close.shift(-k)/close - 1` | tensor_eval label 패턴 (Q9) |
| ③ 지수 일수익률 + regime 마스크 | SH000300 계열 (Q10-11); vol tercile 경계는 **train에서** 산출 | modeltester 68-83행 패턴 |
| ④ ADV20 percentile 행렬 | `Mean($amount,20)` → 일별 pct rank (Q13) | 신규 1줄 |
| ⑤ universe 마스크 | `TensorEvaluator.universe_mask` | 기존 |

Fingerprint 성분:
- **H (Prediction Horizon Response)**: IC(Z, R_k)를 k별로 → 예: argmax k 또는
  IC(k=20)-IC(k=1)의 normalized contrast.
- **V (Volatility Regime Response)**: D(IC_highvol, IC_lowvol) — 사용자 제안
  `D(a,b) = (IC_a - IC_b)/(|IC_a|+|IC_b|+eps)` 사용. 값域 [-1,1], 절대 성능과
  분리됨 — 타당한 설계다. eps는 IC 스케일(~1e-2) 대비 작게, 예: 1e-4.
  (참고: 두 IC가 모두 ~0이면 D가 노이즈에 민감 — |IC_a|+|IC_b| < 임계면
  0으로 처리하는 가드 권장.)
- **M (Market Direction Response)**: D(IC_up, IC_down).
- **S (Size Response)**: **market cap 부재로 보류** (Q12) — 데이터 추가 전까지
  4차원 [H,V,M,L]로 운용 권장.
- **L (Liquidity Response)**: D(IC_liq_top, IC_liq_bottom) — ADV20 percentile
  상/하위 절반(또는 tercile)으로 단면 분할.

일별 IC 시계열을 regime 마스크로 조건화해 평균하는 구조이므로, **alpha당
일별 IC 시계열(각 k별) + 일별 조건 마스크**만 캐시하면 모든 성분이 나온다.

## Q19. method 공통 좌표계 (fixed scaler → fixed PCA) — [가능(신규)]

구현 가능. env에 scikit-learn 1.3.2 존재(확인). 구조:

```
reference alphas (모든 method 합집합, 또는 지정 기준셋)
  → StandardScaler.fit → PCA(n_components=2).fit   # 1회만
  → 저장 (Q20)
새 method 결과 → 동일 scaler.transform → 동일 pca.transform → (PC1, PC2)
```

method별 PCA를 따로 하지 않으므로 좌표계가 고정되고, 이후 추가되는 miner도
같은 지도 위에 찍힌다. 주의: reference set 구성이 좌표계의 정의이므로
**reference에 들어간 run 목록을 manifest로 함께 고정**해야 한다(Q20).

## Q20. scaler/PCA 영속화 제안

```
out/qd/
  scaler.pkl          # joblib.dump(StandardScaler)
  pca.pkl             # joblib.dump(PCA)
  manifest.json       # {"features": ["H","V","M","L","breadth","footprint",...],  ← 순서 고정
                      #  "reference_runs": [...], "eps": 1e-4,
                      #  "regime_calibration": {"train": "2010-01-01~2019-12-31", "vol_terciles": [..]},
                      #  "sklearn_version": "1.3.2", "created": "..."}
```

- joblib은 env에 이미 있음. sklearn pickle은 버전 민감 → manifest에 버전 기록,
  로드 시 검증.
- **feature 순서·regime 경계까지 manifest에 넣는 것이 핵심** — transform의
  재현성은 scaler/PCA 파라미터만이 아니라 입력 정의 전체에 걸려 있다.
- API: `qd_project.fit_reference(df) → 저장`, `qd_project.apply(df) → PC1,PC2`.

---

# E. Alpha combination

## Q21. run당 combined alpha 개수 — **정확히 1개**

- 흐름: 마지막 세대 → 상위 `hall_of_fame`(50) → 상관도 pruning →
  `n_components`(10)개 pool ([`gplearn/genetic.py`](../gplearn/genetic.py)
  550-580행) → `WeightCalculator`가 weight **1벌** → `alphacombo` **1개**
  (modeltester 149행). seed 하나당 최종 combination 하나가 맞다.
- **QD 지도에서 individual alpha를 주 포인트로, combination을 별도 marker로**
  두는 설계는 현 구조와 정합적이다.
- 여러 combination을 줄 수 있는 기존 intermediate:
  - `hall_of_fame` 50개 목록과 pruning 순서(어떤 쌍에서 무엇이 탈락했는지)는
    fit() 내부 지역변수로만 존재, **미저장**. 이를 저장하면 "pruning 단계별
    pool" 시퀀스(50→49→…→10)가 자연스러운 nested combination 후보가 된다 —
    단 각각의 weight 재학습이 필요하므로 post-hoc 최적화를 안 한다는 방침과는
    경계선. **현 단계 결론: 자연 발생 combination은 1개뿐이며, 추가 저장 없이
    여러 combination을 얻을 방법은 없다.**
  - seed 스윕이 사실상의 combination 분포를 제공한다(시드당 1점).

## Q22 & Q25. Search trajectory 저장 — 현재 미저장, **원본 무수정으로 추가 가능**

현황 (Q25의 전제 확인):
- `transformer._programs`(세대별 population)는 **메모리 전용**이고, 심지어
  다음 세대에 부모로 쓰이지 않은 개체는 pruning으로 `None` 처리된다
  (genetic.py 500-515행). fit() 종료 후에도 완전한 궤적이 남지 않는다.
- 러너 로그의 `final:` 줄(genetic.py 517행)은 **fitness 리스트만** 있고 수식이
  없다. `[fast_eval]` 줄은 집계 통계뿐.

**가능하다** — 우리 monkey-patch 지점이 정확히 궤적을 관찰하는 위치다:
`scripts/fast_eval.py` `make_fast_parallel_evolve()`의 phase B는 세대의 모든
프로그램(수식·signed IC·`program.parents` genome)을 생성 직후 보유한다.
여기서 per-generation append 로깅을 하면 원본 무수정으로 전 궤적이 남는다.

저장 권장 스키마 (JSONL 또는 parquet append, run당 1파일):

```
trajectory.jsonl : 한 줄 = 개체 하나
  run_id, method, seed, generation, idx_in_pop,
  formula, signed_train_IC, raw_fitness(=|IC|),
  op(Crossover/Subtree/Hoist/Point/Reproduction), parent_idx, donor_idx,
  program_length, program_depth, eval_was_memo_hit
추가로 run 말미에:
  hall_of_fame_formulas, pruning_order(탈락 시퀀스), final_pool, weights
```

- `parents` genome은 이미 dict로 존재(genetic.py 89-117행 — method,
  parent_idx, donor_idx, 교체 노드 인덱스). depth/length는 `program.depth_`,
  `program.length_` 프로퍼티로 즉시 취득.
- hall_of_fame/pruning은 fit() 내부라 원본 무수정으로는 못 잡는다 → 러너에서
  fit() 종료 후 `transformer._programs[-1]` + `_best_programs`로 최종 pool은
  복원 가능하되, **pruning 순서까지 원하면 fit()을 러너에 사본으로 떠야 한다**
  (경계 명시).
- AutoAlpha도 동일 접근이 가능하지만 `AutoAlpha/genetic.py`는 우리 patch가
  아직 없으므로 별도 사본 evolve 함수가 필요하다 [신규].

---

# F. 최종 산출물 설계

## Q23. 최소 수정 아키텍처

기존 자산과의 연결(전부 신규 파일, 원본 무수정 — 지금까지의 원칙 유지):

```
scripts/oos_eval.py        OOSEvaluator (Q7) — factor/pool 공용 지표 엔진
scripts/qd_descriptors.py  fingerprint(H,V,M,L) + breadth + footprint + turnover(2종)
scripts/qd_project.py      fit_reference()/apply() + scaler·pca·manifest 영속화 (Q19-20)
scripts/run_oos_eval.py    CLI 오케스트레이터:
                           miner CSV들(+ic_memo 덤프) → 3개 parquet
scripts/run_gplearn_fast.py / run_gplearn_tensor.py  (기존 파일 소수정)
                           ① ic_memo 덤프 → signed_train_IC/train_sign 컬럼
                           ② --trajectory 옵션 → trajectory.jsonl (Q22)
```

- 값 공급은 전부 `TensorEvaluator`(검증 완료, formula당 0.3~4s)로 통일 —
  formula 수백 개 × (test 값 + 4개 horizon + regime 분할)이 몇 분 단위가 된다.
- 3개 산출 파일의 스키마는 사용자 제안 그대로 수용하되:
  - `factor_metrics`: `train_sign` + **`signed_train_IC`**(sign만 저장하면 크기
    정보 소실) 컬럼 추가 권장. `test_ICIR` 정의 = mean/std of daily IC.
  - `factor_descriptors`: `size_response`는 데이터 확보 전 NaN 고정(스키마는
    유지) + manifest 참조 컬럼(`qd_manifest_id`).
  - `pool_metrics`: `AlphaEval_Diversity`는
    `modeltester.calculate_covariance_entropy()`(202-229행) 이식으로 충당.
- **parquet 엔진 부재**: AlphaEval38에 pyarrow/fastparquet 없음(실측) —
  `pip install pyarrow` 1회 필요(권장), 아니면 `.pkl` 폴백.

## Q24. 구현 전 반드시 처리할 버그·leakage 위험

**Leakage 감사 (train/valid/test 경계):**

| 항목 | 현황 | 판정 |
|---|---|---|
| alpha sign | 현재 sign 자체가 **저장 안 됨**(Q4). test에서 sign을 정하면 leakage | ⚠️ 선결: 러너에 signed_train_IC 저장, 평가기는 sign을 입력으로만 받게 |
| pool weight | train 구간에서만 학습, test 재학습 없음 (Q5) | ✅ 안전 (freeze 구조 확인) |
| normalization | 일별 cross-sectional z-score — 당일 데이터만 사용 | ✅ 시간 누수 없음 (단 NaN→0 치환(modeltester 130행)은 dead-stock bias 검토) |
| regime threshold | 신규 구현 대상 — **train에서 캘리브레이션 후 고정**을 설계 규칙으로 | ⚠️ 규칙 명문화 필요 (manifest에 기록, Q20) |
| noise 분산 (PFS) | train 구간 SH000300으로 캘리브레이션(modeltester 68-83행) | ✅ 안전 |
| QD scaler/PCA | reference set에 test 성과 지표를 넣으면 지도 자체가 오염 | ⚠️ fingerprint는 behavioral 성분만으로 구성(절대 성능 배제 — normalized contrast 채택 이유) |

**기존 버그 (구현 전 수정/우회 필요):**

1. `modeltester.run_single_factor()` 371행 — 단일 factor인데
   `pivot(values="alphacombo")` → 항상 예외, try/except로 은폐되어 **개별
   factor RRE가 조용히 누락**된다. (신규 evaluator에서는 재사용하지 말 것.)
2. `modeltester.run()` 332행이 `LLM_scores()`를 무조건 호출 — API 키
   placeholder(237행 `"Your own LLM key"`) 상태에서 전체 평가가 죽는다.
   LLM 축은 opt-in으로 분리 필요.
3. placeholder `qlib.init` 3곳 — `modeltester.py:54`, `combo.py:32`,
   `ictester.py:9` — 러너에서 쓰던 스텁(실경로 init 후 `qlib.init=no-op`)
   필수. 또 `modeltester.__init__`은 `instruments=None`이면 **init 이전에**
   `D.list_instruments`를 호출(46-52행)하는 순서 문제가 있다.
4. `Alphaagent/backtester.py` — 첫날 `turnover=NaN`이 truthy로 흘러 첫날
   pnl NaN(130-131행); `long_threshold/short_threshold` 인자 미사용(109-110행
   0.2 하드코딩). 집계식 이식 시 함께 수정.
5. **비재현 요소**: PFS 노이즈(`noise_proc.py` — np.random 시드 없음),
   `WeightCalculator.differential_evolution`(seed 인자 없음) → seed 주입
   가능하게 이식. (참고: AutoAlpha는 탐색 자체도 전역 `random` 사용으로 비재현.)
6. `calculate_pnl()`이 내부에서 `fetch_data()` 재호출(159행) — run()과 함께
   쓰면 이중 페치 + PFS 노이즈가 다시 뽑히면서 상태가 바뀐다.
7. parquet 엔진 부재(pyarrow) — 산출 파일 형식 요구사항의 선결 조건.
8. (재확인) `backtest/__init__.py`의 `backtest/backtester.py` 부재 —
   `scripts/fast_eval.py ensure_backtest_importable()`로 이미 우회 중.

## Q25. (재확인) generation × alpha 궤적 저장 가능 여부

**가능하다.** 근거와 방법은 Q22에 통합 — 요지: `transformer._programs`는
메모리 전용 + pruning으로 소실되지만, 우리 러너의 monkey-patch 지점
(`fast_eval.make_fast_parallel_evolve` phase B)이 세대 전체의
(수식, signed IC, 유전 연산 genome)을 생성 직후 보유하므로, 그 자리에서
JSONL append를 하면 **원본 무수정으로 완전한 search trajectory**가 남는다.
hall-of-fame pruning 순서까지 원하면 fit()의 러너측 사본이 추가로 필요하다.

---

# 요약: 가능 / 신규 / 데이터필요

| 분류 | 항목 |
|---|---|
| **[가능] 기존 코드·데이터로 즉시** | IC·RankIC(ictester/modeltester), AnnRet·Sharpe·MDD·Turnover(FactorBacktester 집계식), weight freeze(combo+modeltester 구조), batch 값행렬(D.features/TensorEvaluator), 일별 z-score(modeltester.zscore), forward return 1/5/10/20d, 지수 기반 vol regime·direction(SH000300 계열 6종 존재), 유동성 ADV20($amount 존재), universe 마스크 |
| **[신규] 코드만 추가** | ICIR, signed_train_IC 저장(러너 memo 덤프), OOSEvaluator(evaluate_factor/evaluate_pool), fingerprint(H,V,M,L)+normalized contrast, N_eff breadth, liquidity footprint, weight 기반 turnover, fixed scaler/PCA + 영속화, trajectory JSONL, 3개 산출 parquet(+pyarrow 설치) |
| **[데이터필요] 현 번들로 불가** | **Size Response(market cap)** — 발행주식수 필드 전무. baostock 등에서 total_share 추가 덤프 전까지 S축 보류(4차원 운용) 권장 |
