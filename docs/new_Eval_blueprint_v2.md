# new_Eval_blueprint v2 — OOS / QD / Backtest 3-파이프라인 청사진 확정 조사

[v1 조사](new_Eval_blueprint.md)에 이어, 평가 시스템을 **OOS Evaluation / QD
Evaluation / Backtest** 세 독립 파이프라인으로 분리하기 위한 확정 조사다.
코드는 수정하지 않았고, 필요한 곳은 **실행 검증(수치 실험·import 실증)**까지
수행했다.

각 항목 태그: **[가능]** 현재 코드·데이터로 즉시 / **[신규]** 코드 구현 필요
(데이터 충분) / **[결정]** 연구자의 설계 결정 필요 / **[데이터필요]**.

이 문서에서 새로 실측한 헤드라인 3가지:

1. **현재 PFS 구현은 논문 정의와 3중으로 다르다** — noise가 (raw feature가
   아닌) **alpha 출력에**, (덧셈이 아닌) **곱셈으로** 들어가고, 상관은
   (Spearman이 아닌) **Pearson**이며, σ는 (지수 수익률 변동성이 아닌)
   **min-max 정규화된 지수 가격 레벨의 분산**이다. (§D)
2. **RRE는 sign 반전에 불변이 아니다** (수치 검증: RRE(S)=0.698234 vs
   RRE(−S)=0.700572) — |IC| 마이닝 산출물에는 orientation 규칙이 필요하다. (§C)
3. **qlib 0.9.0 native backtester가 이 env에서 실제로 동작한다** —
   `qlib.backtest.backtest`, `Exchange(deal_price, limit_threshold, open_cost,
   close_cost, min_cost)`, `TopkDropoutStrategy` import 실증. (§O8)

---

# A. 세 파이프라인의 경계와 공통 데이터 계층

### A1. 공통 signal layer 위에 3개 evaluator — [가능(신규 조립)]

**결론: 가능하며, 현재 코드베이스와 잘 맞는다.** 공통 계층에 필요한 8개
구성요소가 전부 이미 존재하거나 검증된 형태로 준비되어 있다:

| 공통 요소 | 기존 구현 | 위치 |
|---|---|---|
| formula evaluation | `TensorEvaluator.frame(expr)` — qlib 37/37 비트 일치 | `scripts/tensor_eval.py` |
| point-in-time universe mask | `TensorEvaluator._build_universe_mask()` | 〃 (§B9에서 검증) |
| train sign | `FastICEvaluator.ic_memo` / `TensorEvaluator.ic_memo` (signed) | `scripts/fast_eval.py`, `tensor_eval.py` |
| forward return (1/5/10/20d) | label 계산부 패턴 `close.shift(-k)/close - 1` | `tensor_eval.py` 199-205행 |
| daily cross-sectional z-score | `zscore()` + `groupby(level=1)` | `backtest/modeltester.py` 15-19, 124-147행 |
| benchmark return | SH000300/905/852/906/985 번들 존재 (v1 §Q8) | `D.features(["SH000300"],...)` |
| ADV20 | `Mean($amount, 20)` — $amount 존재 | v1 §Q13 |
| pool combination | `factor_data.dot(weights)` | `modeltester.py` 149행 |

제안 구조(설계만): `SignalContext(market, splits, manifest)` 가 위 8개를
**split별로 1회** 계산·캐시하고, `OOSEvaluator / QDEvaluator /
BacktestEvaluator`는 이 컨텍스트만 읽는다. `TensorEvaluator`가 이미 패널
1회 적재 + memo 구조라서 그 위에 얇게 얹힌다.

### A2. 단일 manifest 공유 — [신규]

가능하다. 현재도 암묵적 공유는 있으나(예: label 문자열이 4개 파일에 중복 —
`ictester.py:58`, `modeltester.py:56`, `combo.py:34`, `Alphaagent/backtester.py:76`)
**명시적 config는 없다.** universe/missing rule/sign/normalization/date
range/label/benchmark를 JSON manifest 하나로 두고 세 evaluator가 같은 객체를
받게 하면 된다 (§H1에 고정 항목 전체 목록).

### A3. original_alphaeval 보존 + 신규 3종 병행 — [가능]

이미 세션에서 검증된 패턴이다: 원본(`backtest/`)은 무수정 유지하고, 신규는
`scripts/`에 두며, placeholder `qlib.init` 3곳(`modeltester.py:54`,
`combo.py:32`, `ictester.py:9`)은 **실경로 init 후 `qlib.init`을 no-op으로
스텁**해서 우회한다 (`scripts/run_gplearn_fast.py init_qlib_once()` 전례).
`backtest/backtester.py` 부재는 `scripts/fast_eval.py
ensure_backtest_importable()`로 이미 해결. 네 모드
(`original_alphaeval/new_oos/new_qd/new_backtest`)는 같은 프로세스에서
순차 실행 가능하다.

### A4. old vs new regression test — [가능]

전례가 두 개나 있다: `scripts/verify_equivalence.py`(fast 러너 결과 불변,
ALL PASS), `scripts/verify_tensor_eval.py`(연산자 37/37 비트 일치, IC 오차
≤1e-17). 같은 형식으로 `verify_new_eval.py`를 만들어 IC/RankIC/RRE/PFS/DE를
old(modeltester)·new에서 동시 계산·대조하면 된다. 단 **PFS는 old 구현이
비결정적**(§D5-D6)이라 노이즈 고정 없이는 수치 재현이 불가 — old를 시드
고정판으로 감싸거나 허용오차 비교로 설계해야 한다 [결정].

---

# B. OOS Evaluation Pipeline

### B1. daily IC/RankIC series 저장 → 집계 — [신규(재료 존재)]

가능. `ICBacktester.calculate1()`(`ictester.py` 70-72행)과
`modeltester.run()`(300-305행)이 이미 `ic_series`/`rank_ic_series`를
만들지만 **mean만 취하고 버린다**. 신규 evaluator는 series 자체를
`daily_metrics/`에 저장(§S)하고 Mean/ICIR을 후처리로 계산 — 정의 변경 시
재평가 없이 재집계 가능해진다.

### B2. ICIR 관례 — **저장소 내 근거 있음** [가능]

`AlphaEval/AlphaForge`가 관례를 갖고 있다 (grep 실증):

- [`AlphaForge/train_AFF.py:112`](../AlphaForge/train_AFF.py#L112)
  `icir = (ic_mean/ic.std()).item()` — **raw 정의, √252 없음**
- `AlphaForge/exp_*_calc_result.ipynb` 4종: `icir = ic_mean/ic_std`,
  `ricir = rank_ic_mean/rank_ic_std`

`backtest/`(modeltester/ictester)와 AlphaAgent에는 ICIR이 없다. →
**raw를 기본(`test_ICIR`)으로 채택**(AlphaForge·alphagen 계열 관례와 호환),
연환산이 필요하면 `test_ICIR_ann = ICIR×√252`를 **별도 컬럼**으로 저장. [결정: 채택 확인만]

### B3. RankICIR — [신규]

동일 구조로 가능. AlphaForge의 `ricir`이 정확히 같은 정의
(rank_ic_mean/rank_ic_std)의 전례.

### B4. train_sign 강제 — [신규(구조 설계)]

가능하며 강제 방법도 명확하다: **평가기가 sign을 추정하는 코드 경로 자체를
갖지 않게** 한다 — `evaluate_factor(formula, train_sign)` 처럼 sign을 필수
입력으로 받고, 내부에서는 `S_oriented = train_sign × S`만 사용. sign 산출은
러너(train memo) 또는 B5 복원 스크립트만 담당. test IC의 부호를 읽어 방향을
바꾸는 API를 아예 만들지 않는 것이 leakage 방지의 실효적 강제다.

### B5. 완료된 run의 signed_train_IC 복원 — [가능]

가능하고 **search 결과를 바꾸지 않는다**. IC는 (formula, market, 기간)의
결정적 함수이고(`verify_tensor_eval.py`에서 재현성 실증), 복원은 읽기 전용
재평가다. 방법: 결과 CSV의 formula들을 train 구간에서
`TensorEvaluator.ic(f)`로 재평가 (formula당 ~0.3-4s) → `sign(signed_IC)`.
주의: **train 구간·market이 원 run과 정확히 일치해야** 같은 sign이 나온다
(§C·§D에서 본 것처럼 qlib 값은 query 구간의 함수다). run 메타데이터(sbatch
로그 1행)에 기간·market이 기록되어 있으므로 매칭 가능.

### B6. weight freeze — [가능(이미 구조적)]

v1 §Q5 재확인: `WeightCalculator.fit()`은 생성자에 받은 (train) 구간
데이터만 사용하고, `AlphaEval`은 test에서 재학습 없이 `self.weights`를
사용한다(`modeltester.py` 38, 149행). `weights=[...]` 명시 주입으로 어떤
구간에서 학습한 weight든 얼릴 수 있다.

### B7. combined signal에서 직접 계산 — [가능]

현재 코드가 이미 그렇게 한다: `modeltester.py` 149행
`alphacombo = factor_data.dot(weights)` (일별 z-score 후) → 이 결합 신호
자체로 IC/RankIC 계산(300-305행). component 평균이 아니다. 신규 evaluator도
같은 순서(z-score → Σwᵢ·Zᵢ → 지표)를 따르면 된다.

### B8. test end에서의 label 경계 — **test_end 이후 가격을 사용함** [결정]

현재 동작 (코드 확정): qlib은 `Ref($close,-1)`의 우측 extended window
(`qlib/data/ops.py Ref.get_extended_window_size` — N<0이면 rght+|N|)만큼
**end_time 너머의 데이터를 로드**해 label을 계산한다
(`LocalExpressionProvider.expression`, `data.py` 844-882행: `end_index +
rght_etd`). 따라서 **test 마지막 날의 label은 test_end 다음 거래일의 종가를
사용**한다 (데이터가 존재하는 한 NaN이 아님). `TensorEvaluator`도 이에 맞춰
end+20일 버퍼로 패널을 적재해 동일 동작(비트 일치 검증됨).

두 대안의 정확한 의미:
- **현행 유지**: label horizon이 평가 구간을 1일 초과 — 일반적 관행이며
  "test_end까지 형성된 신호의 미래 수익"이므로 leakage 아님. 단 test_end가
  데이터 끝이면 마지막 날은 자동 NaN→제외.
- **마지막 관측 제외**: 신호 구간을 [start, end-1]로 잘라 label이 구간 안에
  갇히게 함 — 재현 대상 논문과의 비교 시에만 필요.

권장: 현행 유지 + manifest에 `label_uses_post_end_price: true` 명시.

### B9. point-in-time universe mask 재확인 — [가능] ✓

`TensorEvaluator._build_universe_mask()`(`scripts/tensor_eval.py`)는
`D.list_instruments(D.instruments(market), start, end, as_list=False)`가
반환하는 **종목별 (편입일, 편출일) span**으로 (date×inst) bool 마스크를
만든다. csi 계열 파일은 membership **구간**을 담고 있으므로(v1 §Q8) 이는
point-in-time 마스크가 맞다: 상장폐지 종목은 존속·편입 기간에 포함되고
(생존 편향 없음), 편입 전/편출 후는 False. 실측 예: csi800 마스크의 일평균
686종목 — 시점별로 변한다. 동일 마스크를 label·QD·backtest에 재사용하는
것도 가능(§A1) — 단 **현재 원본 경로(ictester)는 마스크 적용 시점이 qlib
내부(span 필터)이고 TensorEvaluator는 IC 단계에서 적용**하는데, 두 방식이
동치임은 IC 비트 일치로 이미 검증됐다.

### B10. pathological factor 처리 규칙 — 현재 암묵적, [신규]로 명시화

현재 동작 (`ictester.calculate1`, `tensor_eval._daily_ic` — 동일 의미):

| 병리 | 현재 처리 |
|---|---|
| 전 구간 constant | 일별 corr 분산 0 → NaN → `ic_series` 전부 NaN → NaN 비율>50% 규칙으로 IC=0.0 |
| 특정 날 constant | 그날 corr NaN → dropna로 그날만 제외 |
| NaN 비율 큼 | 일별 유효쌍 0개면 그날은 series에서 **부재**(NaN 아님 — isna 분모에서 빠짐); `isna().mean()>0.5` → 0.0 |
| ±inf | dropna는 inf를 **통과**시킴 → 그날 corr NaN (v1 §Q24) |
| 유효 종목 극소 | corr에 최소 2개 필요; 1개면 NaN |
| Qlib 거절 수식 | `$close`로 조용히 대체 (`ictester.py` 50-57행, tensor도 동일 폴백) |

즉 실패가 전부 **0.0 또는 조용한 대체로 뭉개진다**. 신규 OOS evaluator에서
`valid: bool, invalid_reason: str, n_valid_days, mean_cross_section_size,
const_day_ratio, inf_cell_ratio, used_close_fallback` 컬럼을 기록하는 것은
전부 이미 계산 과정의 부산물이라 비용이 없다. [신규]

---

# C. RRE — 논문 정의 vs 현재 코드

구현 위치: [`backtest/modeltester.py`](../backtest/modeltester.py) 313-327행.

```python
ranks = factor_mat.rank(axis=1)                  # 일별 cross-sectional rank
probs = ranks.div(ranks.sum(axis=1), axis=0)     # p = R/ΣR
probs_prev = probs.shift(1)
kl = (probs * np.log((probs+eps)/(probs_prev+eps))).sum(axis=1)   # eps=1e-8
rre = mean( 1/(1+kl.dropna()) )
```

### C1. 수식 일치 여부 — **골격은 일치, 3곳이 다름**

| 논문 | 코드 | 판정 |
|---|---|---|
| p = R/ΣR | `ranks.div(ranks.sum(axis=1))` | ✓ 일치 |
| KL(S_t‖S_{t−1}) = Σ p_t log(p_t/p_{t−1}) | `probs*log((probs+eps)/(probs_prev+eps))` | △ **eps가 분자·분모 안에** 들어감 (수치 안정화 — 논문에 없는 항) |
| RRE = mean 1/(1+KL) | `(1/(1+kl.dropna())).mean()` | ✓ 일치 (첫날은 shift로 자동 제외) |
| 동일 asset index 전제 | union pivot + NaN 전파 | ✗ **재정규화 없는 교집합** (C3) |

추가 차이: `factor_mat`은 `self.alphacombo`에서 직접 pivot(313-317행) —
label과의 inner join **이전** 값이라 IC 계산과 유니버스가 미세하게 다를 수
있다(label NaN인 날 포함).

### C2. rank 방향/타이 — [실측 확정]

pandas `rank()` 기본값 실측: `[3,1,2,2].rank() → [4, 1, 2.5, 2.5]` —
**작은 signal = rank 1 (ascending), tie = average**. 논문은 R의 방향을
명시하지 않으므로 "일치/불일치"를 판정할 수 없다 → **[결정]**: 방향을
manifest에 고정해야 한다 (§T7). 큰 신호=높은 rank(현행)면 p가 강한 신호에
큰 확률을 주는 해석이 된다.

### C3. universe 변경 처리 — **비재정규화 교집합**

실측 확인: `probs`는 **그날의 자기 유니버스**로 정규화(합=1, 결측 절반인
날도 1.0), `probs_prev`는 전날 유니버스로 정규화. 곱셈 시 NaN 전파로
**U_t ∩ U_{t−1}에 있는 항만 합산**되지만 p들은 교집합 위에서 다시
정규화되지 않는다 → 합이 1이 아닌 "부분 KL". 종목 교체가 잦은 날은 KL이
체계적으로 왜곡된다(교집합이 작을수록 항 누락). 논문 정의의 충실한 구현이
아니다.

### C4. QD용 교집합 RRE — [신규]

가능하다: 날짜쌍마다 `common = U_t ∩ U_{t−1}` (dense 행렬에서
`~isnan(S_t) & ~isnan(S_{t−1})` + universe mask), 교집합 위에서 rank·정규화를
다시 수행한 진짜 KL을 계산하고 `n_common`을 함께 기록. dense
(date×inst) 행렬 기반이라 벡터화 용이.

### C5. sign 불변성 — **불변이 아님 (수치 실증)** [결정]

```
RRE(S)  = 0.698234
RRE(−S) = 0.700572     (T=60, N=40, 결측 포함 랜덤 데이터)
```

rank가 뒤집히면 p 분포가 달라지므로(선형이지만 KL은 비선형) RRE가 변한다.
따라서 |IC| 마이닝 산출물의 RRE는 **어느 방향으로 재느냐가 결과에 영향을
준다** → QD descriptor로 쓸 때는 **train_sign을 적용한 oriented signal**로
통일할 것을 권장 (B4의 sign 규칙과 일관). 원본 AlphaEval 재현 모드에서는
raw combo(=학습된 weights가 이미 방향을 흡수)로 계산 — 두 모드를 manifest로
구분.

---

# D. PFS — 논문 정의 vs 현재 코드

구현 위치: [`backtest/noise_proc.py`](../backtest/noise_proc.py),
[`backtest/modeltester.py`](../backtest/modeltester.py) 76-113, 306-311행.
주입 경로: `LocalDatasetProvider.dataset(..., inst_processors=[NoiseInjection])`
→ qlib `inst_calculator`(`qlib/data/data.py` 601-635행)가 **표현식을 모두
계산한 뒤** processor를 적용.

### D1–D2. additive input perturbation인가? — **아니다 (이중 불일치)**

| 논문 | 현재 코드 |
|---|---|
| `S' = α(X + ε)` — **raw feature에 덧셈** | `S' = α(X) × (1 + ε)` — **alpha 출력에 곱셈** (`noise_proc.py` `df*(1.0+noise)`; inst_calculator가 표현식 계산 **후** 적용) |

즉 현재 PFS는 "입력 섭동에 대한 formula의 강건성"이 아니라 "출력에 곱셈
노이즈를 섞었을 때 상관이 얼마나 남는가"를 잰다 — 후자는 formula 구조와
거의 무관하게 노이즈 크기만의 함수가 되는 경향이 있어, 논문이 의도한
"perturbation fidelity"와 측정 대상이 다르다.

추가 불일치: 논문 `PFS = SpearmanCorr`인데 코드는 `x["factor"].corr(x["noisy1"])`
— pandas 기본 = **Pearson**(`modeltester.py` 306-311행). `min(PFS_G, PFS_t)`도
계산하지 않고 pfs1/pfs2만 따로 출력.

### D3. σ 정의 — **다르다**

- 논문: 해당 market index의 **average daily volatility** (= 일수익률 표준편차).
- 코드(`modeltester.py` 76-83행): train 구간 SH000300 **종가를 min-max
  정규화한 '가격 레벨' 시계열의 분산** — 수익률이 아니라 가격 수준의 산포.
  스케일도 의미도 다르다 (예: 10년 박스권이면 레벨 분산은 크지만 일변동성과
  무관).

### D4. Student-t — **부분 일치**

`dof=3` ✓ (`modeltester.py:109`, `noise_proc.py NoiseInjection_t`).
rescale: `t_raw × σ × √((ν−2)/ν)` — t(3)의 분산 3을 1로 낮춘 뒤 σ 배 →
**Gaussian과 동일 std** ✓. 단 이 σ 자체가 D3의 잘못된 σ이고, 적용 방식이
곱셈이라는 점은 동일하게 불일치.

### D5. noise tensor shape — instrument별 독립 호출

`inst_calculator`가 **종목마다 따로** 호출되고 그 안에서
`np.random.normal(0, σ, size=df.shape)` — df.shape = (그 종목의 날짜 수 ×
factor 수). 즉 (date, factor)별 독립이고 종목 간에도 독립 **의도**지만:
- **시드가 없고**, qlib 멀티프로세스 워커(fork) 안에서 추출되므로 워커들이
  **부모의 RNG 상태를 복제**해 종목 간 노이즈가 상관되거나(같은 시퀀스),
  실행마다 달라진다 — 재현성과 독립성 모두 보장 안 됨. [버그/hazard]

### D6. deterministic perturbation cache — [신규, 가능]

가능. `(market, split, noise_type, seed)` → `np.random.default_rng(hash(key))`
로 (date×inst×field) 텐서를 생성해 디스크 캐시(np.savez, ~0.5GB/개) 또는
on-the-fly 재생성. TensorEvaluator의 dense 패널 구조가 정확히 이 텐서와
같은 축이라 궁합이 좋다.

### D7. perturbed raw tensor 하나에서 모든 formula 평가 — [신규, 가능]

**tensor 트랙이 이걸 정확히 가능하게 한다**: `TensorEvaluator`의
`self.panels`(10필드 dense 패널)에 `X+ε`를 적용한 **복제 evaluator 인스턴스**
를 만들면, 모든 formula가 동일한 perturbed 시장 위에서 평가된다 — 논문의
`S'=α(X+ε)` 정의 그대로. 비용: perturbed 패널당 formula×~1-3s (K개 draw면
K배 — §T6 난도 항목). qlib 경로로는 원시 bin을 바꿀 수 없어 사실상 불가능
했던 것이 tensor 트랙의 부수 효과로 열렸다.

### D8. K-draw 평균 + single-draw 병행 — [신규, 가능]

D6/D7 구조에서 자연스럽다: `PFS_G = mean_k SpearmanCorr(S, S'_k)`.
`mode: {"paper_reproduction_single_draw", "k_draw_mean"}` 를 manifest로 분기,
legacy(현행 곱셈-출력-Pearson) 모드도 재현 비교용으로 병행 가능(단 legacy는
시드 고정 래퍼 필요 — A4).

### D9. 4값 저장 — [신규]

`PFS_Gaussian, PFS_t, PFS_min = min(G,t), noise_config(seed, σ 정의, K,
mode)` 모두 저장 가능 — 계산 부산물이므로 추가 비용 없음.

---

# E. QD Behavioral Descriptor Pipeline

(전 항목 공통 근거: 재료가 되는 dense 행렬·마스크·지수·ADV20은 §A1 표 참조.)

### E1–E4. intermediate 전부 보존 — [신규, 가능]

parquet에 wide 컬럼으로 저장하면 된다: `IC_1d/5d/10d/20d`(E1),
`IC_high_vol/IC_low_vol/vol_contrast`(E2), `IC_up/IC_down/dir_contrast`(E3),
`IC_liq_high/IC_liq_low/liq_contrast`(E4). 일별 IC series까지 보존하려면
`daily_metrics/`에 (formula×date×regime) long 포맷 — H 정의를 나중에 바꿀 때
재평가 없이 재집계 가능. 저장 설계일 뿐 기술 장벽 없음.

### E5. normalized contrast + 소분모 감지 — [신규, 가능]

`D(a,b)=(a−b)/(|a|+|b|+eps)` 는 순수 산술. `denom_small = (|a|+|b|) <
threshold` bool 컬럼을 함께 기록 — v1 §Q18에서 제안한 가드와 동일. eps·
threshold 값은 [결정] (§T7).

### E6. regime threshold를 train에서 고정 — [신규, 가능]

train 구간 SH000300 일수익률의 rolling σ(창 길이 [결정])에서 1/3·2/3
quantile을 계산해 manifest에 **수치로 저장**(§H1), valid/test에는 그 수치를
그대로 적용. 코드 상 장애물 없음. (선례: 노이즈 분산도 train 지수로
캘리브레이션 — `modeltester.py` 68-83행.)

### E7. 중간 tercile 제외 — [신규, 가능]

regime 마스크가 {low, mid, high} 라벨이므로 mid 날짜를 IC 집계에서 빼는
것은 마스크 필터 한 줄.

### E8. z-비례 가중 breadth — [신규, 가능]

v1 §Q15 재확인 + 이유 보강: 20/20 quantile 가중이면 매일 |w|가 상하위 40%
균등이라 N_eff/N ≈ 0.4 상수로 퇴화. `w ∝ z`(일별 z-score, §A1 재료)로
`p=|w|/Σ|w|, N_eff=1/Σp², Breadth=N_eff/N` — 일별 계산 후 기간 평균.
N = 그날 유효 종목 수.

### E9. signal_weight_turnover 분리 — [신규, 가능]

`0.5·Σᵢ|w_i(t)−w_i(t−1)|` (w는 E8의 z-비례 가중, 결측은 0 처리 규칙 [결정]).
backtest의 membership turnover(§O)와 **다른 이름으로** 저장:
`signal_weight_turnover` vs `portfolio_membership_turnover`. 혼동 방지는
스키마 명명으로 해결(§S).

---

# F. RRE/PFS를 QD descriptor로 — manifest 선택 구조

### F1–F2. descriptor set manifest 선택 + ablation — [신규, 가능]

descriptor 계산을 "전부 계산해 wide 저장 → **set 정의는 manifest의 컬럼
리스트**"로 분리하면, `core_behavior`/`extended_behavior` 등 여러 set이 같은
parquet에서 파생되고 PCA만 set별로 다시 fit하면 된다(§G3의 fit 규칙 준수).
Core / Core+RRE / Core+PFS / Core+RRE+PFS ablation은 manifest 4개로 동일
파이프라인 재실행 — 구조적으로 자연스럽다.

### F3. PCA 전 진단 리포트 — [신규, 가능]

raw descriptor DataFrame에서 `df.corr(method="spearman")`,
`df.corr(method="pearson")`, `df.var()`, `df.isna().mean()` — pandas 네이티브.
진단 산출물을 `manifests/descriptor_diagnostics_<set>.csv`로 저장.

### F4. 중복 자동 진단 — [신규, 가능]

F3의 상관 행렬에서 지정 쌍(또는 |ρ|>기준 모든 쌍)을 플래그. 사전 예상
(코드 구조 근거):
- **RRE ↔ signal_weight_turnover**: 둘 다 "일간 랭킹/가중치 변화"의 함수 —
  높은 음의 상관 예상 (RRE↑=안정, turnover↓)
- **PFS_G ↔ PFS_t**: 같은 σ·같은 구조의 노이즈 — 높은 양의 상관 예상
  (min을 쓰는 이유가 이것)
- **Horizon ↔ turnover**: 장호라이즌 신호일수록 느리게 변함 — 상관 예상
- **Liquidity Response ↔ Liquidity Footprint**: 전자는 IC의 조건부 차이,
  후자는 베팅 위치 — 정의상 다르지만 실증 필요
→ 진단은 자동화 가능하고, **제거 여부는 [결정]**.

---

# G. Valid/Test descriptor와 drift

### G1–G2. BD_valid / BD_test 이중 계산 — [신규, 가능]

`SignalContext`를 split별로 만들면(§A1) 같은 formula를 valid·test 두
컨텍스트에서 평가하는 것은 루프 하나. **캘리브레이션 파라미터(regime
threshold, PFS σ·seed)는 train에서 산출한 값을 두 split이 공유** —
manifest에 수치로 고정(§E6, §H1)하는 구조가 그 보장이다.

### G3–G4. PCA fit은 validation descriptor로만 — [신규, 가능]

`qd_project.fit_reference(BD_valid_of_reference_runs)` → scaler/PCA 저장 →
`apply(BD_valid)`, `apply(BD_test)` 동일 transform. test descriptor가 fit에
못 들어가게 하는 것은 **fit 함수의 입력을 valid 파일 경로로 제한**하는
관례 + manifest의 `reference_split: "valid"` 기록으로 강제.

### G5–G6. drift — [신규, 가능]

`drift_raw = ‖BD_test − BD_valid‖`(스케일 문제 → scaler 적용 후 norm 권장
[결정]), `drift_pca = ‖PC_test − PC_valid‖`, 그리고 descriptor별
`Δ = BD_test_i − BD_valid_i` 를 전부 wide 컬럼으로 저장(§S의
`qd_factor_descriptors` 스키마에 포함).

---

# H. PCA / QD Grid manifest

### H1. 고정 항목 전체 — [신규, 가능]

v1 §Q20 manifest를 확장:

```json
{
  "descriptor_set": {"name": "core_behavior", "columns": ["H","V","M","L","B"]},
  "reference_runs": ["gp_seed0..4", "autoalpha_seed0..4"],
  "reference_split": "valid",
  "scaler": "scaler.pkl", "pca": "pca.pkl",
  "pca_explained_variance": [0.xx, 0.yy],
  "pc_bounds": {"pc1": [-a, a], "pc2": [-b, b]}, "clip_rule": "clip|drop",
  "grid": {"resolution": [nx, ny], "bin_edges": "..."},
  "regime": {"train_window": "...", "vol_sigma_window": 20, "vol_terciles": [q33, q66]},
  "pfs": {"sigma_def": "index_daily_ret_std", "sigma": 0.0123, "seeds": [..], "K": 5, "mode": "additive_input"},
  "label": {"expr": "Ref($close,-1)/$close-1", "uses_post_end_price": true},
  "versions": {"sklearn": "1.3.2", "qlib": "0.9.0", "dataset": "cn_data@2026-02-05"}
}
```

joblib + JSON — 전부 직렬화 가능한 대상.

### H2. 신규 method에 기존 transform 적용 — [가능(설계 원칙)]

fit과 apply가 분리되어 있으면 자동으로 성립 (v1 §Q19). 새 method는
`apply()`만 호출.

### H3. PC 좌표와 원본 descriptor 동시 보존 — [가능]

`qd_factor_descriptors.parquet`에 raw 컬럼 + `PCA1/PCA2` 컬럼을 같은 행에
저장 (§S 스키마). PCA 재정의 시 raw에서 재투영만 하면 됨.

---

# I. Pool-level diversity / density

### I1–I3. Coverage / Occupancy Entropy / NN distance — [신규, 가능]

전부 numpy/scipy로 수 줄: 고정 grid의 `occupied/total`,
`-Σ(c_i/Σc)log(c_i/Σc) / log(n_bins)`, `scipy.spatial.cKDTree`(scipy는
qlib 의존성으로 env에 존재)로 NN distance mean/median.

### I4. High-Quality Coverage — [신규, 가능]

`quality_metric: {"name": "test_IC", "threshold": 0.02}` 를 config로 받아
필터 후 I1 재계산. metric 이름은 OOS/backtest parquet의 아무 컬럼이나 참조
가능 (IC/RankIC/Sharpe…). threshold 값은 [결정].

### I5. KDE는 시각화 전용 — [신규, 가능]

`scipy.stats.gaussian_kde` 존재. 정량 지표는 fixed grid로만, KDE는 plot
레이어로만 — 함수 분리로 강제.

---

# J. AlphaEval DE vs QD diversity

구현: [`modeltester.calculate_covariance_entropy()`](../backtest/modeltester.py) 202-229행.

### J1. 논문 정의와 일치? — **골격 일치, 전처리에 차이**

flatten((time,asset) 행 × m factor 열) → `np.cov(rowvar=False)` →
`eigvalsh` → `p=λ/Σλ` → `−Σp log p / log(m)` — **수식 골격은 논문 DE와
일치**. 차이는 전처리(J3/J4).

### J2. 명칭 — 코드는 `self.diversity`

`summary()`가 "Diversity: "로 출력(340행). 논문 DE/DH 혼용 문제는 결과
파일에서 **`AlphaEval_DE`로 통일** 제안 — pool_metrics 스키마에 반영(§S).

### J3. 사전 normalization — 일별 cross-sectional z-score

`daily_normalize=True`(기본)면 `fetch_data`에서 이미 일별 z-score + NaN→0
(124-131행) 된 `factor_data`를 그대로 사용. False면 202-210행에서 동일
z-score를 적용. 즉 **항상 일별 z-score 후 공분산**.

### J4. NaN 처리 — **0 채움(union 그리드)**

z-score 단계에서 `.replace(np.nan, 0)` (130행) → 존재하지 않는
(날짜,종목)이 0으로 공분산에 들어간다. `dropna(how="any")`(212행)는 이미
NaN이 없어져 실질 no-op. **공분산을 0-채움이 왜곡**(상장 기간이 다른
종목이 많을수록 λ 스펙트럼이 평평해져 DE 과대) — 신규 구현에서는
`common intersection` 또는 pairwise covariance 옵션을 두고 [결정].

### J5. 음수 고유값 — 0으로 클립

`np.clip(eigs, 0, None)` 후 `p>0` 필터(222-227행) — 수치오차 음수는
엔트로피에서 제외된다. 안전한 처리.

### J6–J7. DE는 pool_metrics 전용 + QD 지표와 병렬 저장 — [신규, 가능]

DE는 정의상 set 함수이므로 `qd_pool_metrics.parquet`(또는
`oos_pool_metrics`)에만 두고, 같은 행에 `QD_Coverage / QD_Entropy /
NN_Distance / HQ_Coverage`를 함께 저장 — "통계적 신호 다양성(DE)" vs
"행동공간 다양성(QD)"의 직접 비교가 한 테이블에서 가능해진다.

---

# K. Final-pool QD vs Search QD

### K1. scope 3종 — [신규, 가능 (궤적 로깅 전제)]

- `final_pool`: 결과 CSV의 n_components개 — 지금도 가능.
- `all_candidates`: **궤적 로깅이 선행 조건** (v1 §Q22/Q25 — 우리
  monkey-patch 지점에서 JSONL append, 원본 무수정). memo가 formula→IC를
  이미 갖고 있으므로 unique formula 집합은 러너 종료 시 덤프만 해도 확보
  가능(세대 정보 없이). 세대별 분석까지 원하면 per-generation 로깅 필요.
- `generation`: 위 로깅의 (gen, formula) 컬럼으로 슬라이스.

### K2–K5. — [신규, 가능]

`final_pool` diversity는 I 절 지표를 결과 CSV에 적용. `all_candidates`는
unique formula 전체의 descriptor 계산(수천 개 × TensorEvaluator ~1-3s/개 —
예: 883929는 1,675개 ≈ 1-2시간 [비용 주의]). `generation` scope에서는
세대별 coverage/entropy/mean quality/HQ coverage/centroid(PC 좌표 평균)/
descriptor 분포를 저장 — 전부 groupby(generation) 집계.

### K6. transition dynamics — [가능(로깅 후)]

세대별 centroid 이동 벡터, coverage 증가 곡선, 신규 점유 bin 수 등이 그대로
"search가 행동공간을 어떻게 탐색했는가"의 시계열이 된다. 883929 사례가
동기를 실증한다: fitness 다양성이 844→158로 붕괴하는 과정을 QD 공간에서
보면 mode collapse의 궤적이 보일 것.

---

# L. Pool size / 평가 예산 편향

### L1. 최종 alpha 개수 — **항상 정확히 n_components개, 단 중복 포함**

`genetic.py` 569행 `while len(components) > self.n_components` — pruning은
정확히 n_components에서 멈춘다. run마다 개수가 달라지지 않는다. **그러나
unique 개수는 달라진다** — 883929 실증: 10개 중 unique 2개(사실상 1개).
→ coverage 비교는 "개수"가 아니라 **unique formula 수** 기준으로 해야 함.

### L2. 총 평가 수 동일? — **아니다**

- GP: `population_size × generations` (예: 5,000), unique는 그보다 작음
  (883929: 1,675 — memo 실측).
- AutoAlpha: `generations × population_size × (growth_k + 2)` (v1 AutoAlpha
  조사) — 같은 pop·gens라도 **7배 예산**. method 간 evaluation budget이
  구조적으로 다르다.

### L3. sample-size bias — [확인됨, 설계 반영]

coverage/entropy는 표본 수 단조 증가 지표이므로 L2의 예산 차이가 그대로
bias가 된다 — 문서화 + L4로 통제.

### L4. subsampling 기대 coverage — [신규, 가능]

고정 N개를 R회 복원/비복원 추출해 `E[coverage@N]` 곡선(rarefaction curve)
계산 — numpy 몇 줄, 시드는 R1 규칙으로 고정.

### L5. search budget 기록 — [신규, 가능]

러너 로그에 이미 있는 것을 구조화만 하면 된다: total evaluations(pop×gens),
unique evaluations(memo 크기 — `[fast_eval]` 줄), wall-clock(`[run] total`),
generations. trajectory JSONL에 함께 저장.

---

# M. Duplicate / redundant alpha

### M1. 중복 존재? — **예 (실증)**

883929 최종 pool: 10개 중 8개가 동일 문자열. 궤적에서도 reproduction/
crossover가 복제본을 만든다 (memo hit 66.5%가 그 증거).

### M2. exact dedup — [신규, 가능]

formula 문자열 기준 `drop_duplicates` — QD 분석 단계에서 옵션으로.
기본값 권장: **QD point는 dedup, 원본 pool 기록은 보존** (M4 원칙).

### M3. 문자열 다르나 값 동일 — **예 (실증)**

883929의 9·10행: `Div(Less(Power($high,$change), Less(core, ...)), $volume)`
vs `Div(Less(core, ...), $volume)` — IC가 소수 15자리까지 동일 = 신호 동일
(Less 체인이 같은 값으로 붕괴). 구조적으로 GP에서 흔하다 (`Abs(Abs(x))` 등).

### M4. near-duplicate 분석 — [신규, 가능]

`corr(signal_a, signal_b) > 0.999` 기준 클러스터링 — 신호 행렬은
TensorEvaluator로 확보 가능. n개 formula면 n² 상관(n~수천이면 flatten 벡터
간 상관으로 계산 가능하나 메모리 주의 — 883929 규모(1,675개)면 (1,675 ×
6.7M) 행렬은 부담 → 일별 IC 시계열 간 상관 같은 저차원 프록시 or 샘플링
[결정]). **분석 단계 전용 스위치**로 원본 보존.

---

# N. Combined alpha를 QD 지도에

### N1. 실제 결합 신호로 descriptor 재계산 — [신규, 가능]

B7과 동일 경로: frozen weights로 `combined = Σ wᵢ·zscore(alphaᵢ)` 생성 →
그 (date×inst) 행렬을 **개별 alpha와 똑같은 descriptor 함수에 통과** —
component 가중평균이 아니라 신호 자체에서 H/V/M/L/RRE/PFS/Breadth 계산.
구조상 개별 alpha 경로와 코드가 완전히 공유된다.

### N2–N3. 동일 PCA transform + marker 구분 — [가능]

같은 descriptor 벡터이므로 `apply()`에 그대로 투영. 결과 행에
`kind: {"individual", "combined"}` 컬럼을 두면 시각화 marker 분리는 plot
레이어 문제일 뿐.

---

# O. Backtest Pipeline

### O1–O2. 포트폴리오 구조 수학 확인 — ✓ 일치

`Alphaagent/backtester.py` 104-133행 (modeltester.calculate_pnl과 동일 로직):
- top 20% 롱 / bottom 20% 숏 (`quantile(0.8)/(0.2)`, 경계 포함) ✓
- equal weight ✓ (그룹 mean)
- daily rebalance ✓
- **O2 검증**: 롱 0.5/숏 0.5 gross 1·net 0 포트폴리오의 일수익
  = 0.5·mean(long ret) − 0.5·mean(short leg ret) = (long_ret + short_ret)/2
  — 코드의 pnl 정의와 **정확히 일치** (short_ret = −mean(bottom)이므로).

### O3. cost 일관성 — **1차 근사로 일관, 2차 항 누락**

편도 비용률 c=0.15%로 실제 거래 비용 = c·Σ|Δw|. 진입+이탈 카운트 기반으로
n_L=n_S=n이면 Σ|Δw| ≈ (trades_L+trades_S)·(0.5/n) = turnover_code ×
0.0015와 **정확히 같은 값**이 된다 (turnover_code = trades/(2n)).
누락: ① 보유 종목 간 equal-weight 재조정 거래(일일 미세 리밸런스),
② n_L≠n_S일 때 근사 오차, ③ 첫날 NaN(§O4). 결론: 단순 백테스트로서
일관적이나 "카운트 기반 근사"임을 명시.

### O4. 첫날 NaN 수정 영향 — [신규(측정 가능)]

`if turnover:`에 NaN이 truthy로 들어가 첫날 pnl=NaN(130-131행) → pandas가
prod/std에서 skip하므로 영향은 "표본 1일 손실 + n에 NaN일 포함(CAGR 지수
미세 왜곡)". 수정 전후 차이는 기존 결과에 재계산 한 번으로 정량화 가능 —
장기(10년) 백테스트에선 무시 수준, 단기에선 유의할 수 있음.

### O5–O6. cost config화 + gross/cost/net 분리 저장 — [신규, 가능]

현재 0.0015 하드코딩(`backtester.py:130`, modeltester 192행). 신규
BacktestEvaluator에서 `cost_rate` 인자화하고 `daily_gross, daily_cost,
daily_net`을 분리 기록 — 계산 순서상 이미 존재하는 중간값이라 무비용.

### O7. execution 가정 — **same-close**

신호는 t 종가까지의 정보(qlib 표현식이 t까지 데이터 사용), label은 t종가→
t+1종가 수익 — 즉 **t 종가에 신호를 알고 t 종가로 즉시 체결**하는 가정.
실무적으로는 t 종가 데이터가 마감 후에 완성되므로 non-tradable한 낙관적
가정 (미시구조 look-ahead). 대안: label을 `Ref($open,-1)` 기반
(next-open 체결) 또는 `Ref($close,-2)/Ref($close,-1)-1`(t+1 종가 체결)로
바꾸는 것 — 신호 재계산 없이 label만 교체하면 되므로 구조 변경은 작다 [결정].

### O8. qlib native backtester — **[가능] (import 실증)**

이 env(qlib 0.9.0)에서 실증:
```
from qlib.backtest import backtest, executor          # OK
from qlib.backtest.exchange import Exchange            # OK
from qlib.contrib.strategy import TopkDropoutStrategy  # OK
Exchange.__init__ params: deal_price, limit_threshold, open_cost, close_cost, min_cost
```
- next-open/vwap 체결: `deal_price="open"/"vwap"/"close"` — $open/$vwap 필드
  존재 ✓
- limit-up/down: `limit_threshold=0.095` (CN 관행) — $change로 판정 ✓
- suspension: 데이터 NaN → tradable 판정에서 제외 (Exchange 내부)
- cost: open_cost/close_cost/min_cost ✓
주의: TopkDropoutStrategy는 롱 전용(top-k) — 롱숏 백테스트에는
WeightStrategyBase 기반 커스텀 전략이 필요 [신규]. 또 백테스트 기간의
benchmark 지정, trade_unit(100주) 등 CN 세팅 확인 필요.

### O9. backtest_mode = simple | qlib — [신규, 가능]

BacktestEvaluator에 mode 분기: `simple` = O1 구조(§O 수학 그대로, cost
config화·첫날 수정), `qlib` = O8 native. 결과 스키마는 공통(§S).

---

# P. Backtest 지표 정의

### P1. AnnRet = CAGR ✓

`(1+cum_ret)^(252/n)−1` (`Alphaagent/backtester.py:172`) — 확인. 유지 권장,
manifest에 `annualization: "cagr_252"` 명시.

### P2. Sharpe ✓

`mean(daily)/std(daily,ddof=1)×√252`, risk-free 0 (176-178행) — 확인.

### P3. rf/benchmark 인터페이스 — [신규, 가능]

`sharpe(returns, rf=0.0, benchmark=None)` 시그니처로 열어두면 됨 — 지수
수익률은 번들에 있음(§Q8).

### P4. MDD 부호 — 현재 **음수**(signed)

`dd.min()` — 음수 반환(185행). 저장 관례는 [결정]: 권장 `MDD`(양수 크기) +
manifest에 `mdd_convention: "positive_magnitude"` 명시.

### P5. AnnTurn 오명 — 확인됨, 분리 [신규]

`ann_turn = to_s.mean()`(174-175행) — 실제로는 **일평균 turnover**다.
신규 스키마에서 `mean_daily_turnover`와 `annualized_turnover(=×252)`로
분리, 기존 `Fitness` 재현이 필요할 땐 legacy 정의 유지 별도 컬럼.

### P6. 개별/combined 동일 rule — [가능]

BacktestEvaluator가 신호 행렬만 받으므로 (개별 alpha든 combined든) 동일
경로 — B7/N1과 같은 원리.

### P7. daily series 저장 — [신규, 가능]

gross/cost/net/turnover/cumret/long_count/short_count 전부 계산 루프의
중간값 — `daily_metrics/backtest_<id>.parquet`로 저장 설계(§S).

---

# Q. 역할 분리

### Q1. 3-파이프라인 지표 분담 — [가능(설계 확정)]

사용자 제안 분담이 코드 구조와 정합적이다. 한 가지 명확화: **RRE/PFS는 QD
파이프라인에서 계산하되 원본 AlphaEval 재현 모드(§A3)의 산출과 이름을
분리** (`RRE_qd_oriented` vs `RRE_alphaeval_combo` 등 — §C5의 sign 문제
때문에 값이 다르다).

### Q2. 중복 계산 없는 공통 intermediate — [신규(A1 구조)]

`SignalContext`가 공유하는 것: 값 행렬(z-score 전/후), 일별 IC series
(OOS와 QD의 regime IC가 같은 series의 조건부 평균), universe mask, label,
w 행렬(E8·E9·N1·backtest가 공유). 파이프라인은 집계만 달리한다.

---

# R. Reproducibility / Cache / Verification

### R1. 시드 통제 — [신규, 전부 가능]

| 랜덤 요소 | 현재 | 통제 방법 |
|---|---|---|
| PFS Gaussian/t noise | **시드 없음 + 워커 fork RNG hazard** (§D5) | D6 deterministic cache — `default_rng(key)` |
| WeightCalculator DE | `differential_evolution` seed 미전달 (`combo.py` 98행) | scipy DE는 `seed=` 지원 — 신규 사본에서 전달 |
| QD subsampling (L4) | 신규 | `default_rng(seed)` |
| PCA reference sampling | 신규 (샘플링 안 쓰면 해당 없음) | 동일 |
| (참고) GP 자체 | fast/tensor 러너는 random_state로 재현 ✓ (AutoAlpha는 전역 random 사용으로 비재현 — v1) | |

### R2. cache key — [신규, 가능]

제안 키: `(formula, market, universe_file_hash, start, end, split, horizon,
train_sign, dataset_version, label_def, perturbation_config)`. dataset
version은 번들 경로+mtime 해시로. TensorEvaluator memo를 디스크 캐시로
승격할 때 이 키를 사용.

### R3. provenance manifest — [신규, 가능]

git commit(`git rev-parse HEAD` — 저장소가 git repo ✓), Python/qlib/sklearn
버전, dataset 경로+버전, config 전문, method/seed/split/formula count/
timestamp — 실행 시점에 전부 취득 가능한 값들. 각 parquet 옆에
`manifests/<run_id>.json`.

### R4. synthetic sanity test 5종 — [신규, 전부 구현 가능]

1. 매일 동일 rank 신호 → KL=0 → RRE=1 (eps 영향 ~1e-8 이내) ✓ 검증식 자명
2. ε=0 → S'=S → Spearman=1 → PFS=1 ✓
3. 동일 alpha 복제 pool → λ가 1개만 양수 → DE→0 ✓ (0-채움 J4 영향 확인 겸용)
4. 직교 신호 pool → λ 균등 → DE→1 ✓
5. 동일 formula 재평가 → descriptor/metric 완전 재현 (시드 규칙 R1 전제) ✓
(§C5의 RRE sign 실험이 이런 테스트의 실증 전례.)

### R5. old vs new numerical regression — [가능, PFS만 조건부]

IC/RankIC/RRE/DE는 old가 결정적이라 정확 비교 가능. **PFS는 old가
비결정적**(D5) — old에 시드 고정 몽키패치를 하거나(원본 무수정 원칙과
충돌하지 않게 np.random.seed를 러너에서 설정 + kernels=1 강제) 통계적
허용범위 비교로 설계 [결정].

---

# S. 결과 파일 구조 — 확정안

3-파이프라인 분리에 맞춘 6 parquet + 3 디렉토리:

```
out/eval/
  oos_factor_metrics.parquet      method, seed, formula, signed_train_IC, train_sign,
                                  test_IC, test_RankIC, test_ICIR, test_RankICIR,
                                  valid, invalid_reason, n_valid_days, ...(B10 필드)
  oos_pool_metrics.parquet        method, seed, n_factors, n_unique_factors(L1),
                                  test_IC/RankIC/ICIR/RankICIR (결합신호 기준, B7)
  qd_factor_descriptors.parquet   method, seed, formula, kind(individual|combined),
                                  scope(final_pool|all_candidates), generation,
                                  IC_1d/5d/10d/20d, IC_high_vol/low_vol/contrast(+denom_small),
                                  IC_up/down/contrast, IC_liq_high/low/contrast,
                                  breadth, signal_weight_turnover, RRE_qd, PFS_G/t/min,
                                  BD_valid_*, BD_test_*, drift_raw/pca, PCA1, PCA2,
                                  qd_manifest_id
  qd_pool_metrics.parquet         method, seed, scope, generation?, AlphaEval_DE,
                                  coverage, occupancy_entropy, nn_dist_mean/median,
                                  hq_coverage(+threshold config), n_points, n_unique
  backtest_factor_metrics.parquet method, seed, formula, mode(simple|qlib),
                                  AnnRet, Sharpe, MDD(양수 크기), mean_daily_turnover,
                                  annualized_turnover, gross_AnnRet, total_cost, net/gross 분리
  backtest_pool_metrics.parquet   동일 스키마 (결합신호)
  daily_metrics/                  formula/pool별 일별 IC·RankIC·pnl·turnover 시계열
  trajectory/                     <run_id>.jsonl — gen, formula, signed_IC, genome (K/L5)
  manifests/                      <run_id>.json (R3) + qd manifest (H1) + regression 리포트
```

전제: pyarrow 설치(현재 부재 — v1 §Q24⑨) 또는 pkl 폴백.

---

# T. 핵심 설계 판단 (코드베이스 관점 의견)

### T1. 세 파이프라인 간 불필요한 중복?

있다 — 그러나 §A1/Q2의 SignalContext로 해소된다. 구체적으로 겹치는 것:
① 일별 IC series (OOS의 지표이자 QD regime IC의 원료) — 한 번 계산해 공유.
② z-score 신호/가중치 행렬 (QD breadth·turnover와 backtest 포트폴리오가
같은 w를 쓰도록 정의 통일). ③ label/forward return. 반대로 **RRE/PFS는
QD 전용**으로 두고 OOS에 넣지 않는 것이 역할 분리상 맞다.

### T2. 잔여 test leakage 위험

1. **PFS 노이즈 σ와 draw**: σ를 train에서 캘리브레이션(현행도 train ✓)하되,
   noise **draw 자체는 test 구간 데이터 위에서** 이루어짐 — 이는 leakage가
   아니라 평가의 일부. 위험한 건 K-draw 중 좋은 것 선택 같은 후처리 — 금지
   규칙 명시.
2. **PCA reference에 test descriptor 혼입** (G3) — fit 입력을 valid로
   제한하는 규약 필요.
3. **HQ coverage threshold를 test 분포 보고 정하는 것** — threshold는 사전
   고정(manifest).
4. **B5 sign 복원 시 기간 실수** — train이 아닌 전체 기간으로 재평가하면
   soft leakage. run 메타데이터 매칭 자동화 필요.
5. near-dup 제거 기준(corr)을 test 신호로 계산하면 미세 leakage — valid
   신호로 계산 권장.

### T3. 정보가 겹칠 가능성이 높은 descriptor 쌍

(F4 예상 + 근거) ① RRE ↔ signal_weight_turnover — 둘 다 랭킹 시간 안정성,
강한 음상관 예상 → 하나만 core에. ② PFS_G ↔ PFS_t — 동일 σ·구조, min만
남기는 것도 방법. ③ Horizon ↔ turnover/RRE — 장호라이즌=저회전. ④
IC_liq contrast ↔ liquidity footprint — 정의는 다르나 실증 확인 전까지 둘
다 보존(F3 진단으로 판단). 최종 선택은 reference set에서의 상관 행렬을 보고
결정 — 그래서 F1의 set-교체 구조가 중요하다.

### T4. final pool이 작아 QD coverage 불안정?

**그렇다 — 그리고 이미 실증됐다.** pool은 seed당 10개인데 883929에서 unique
2개로 붕괴했다. bin 수십 개짜리 grid에서 점 2~10개의 coverage는 사실상
노이즈다. 대응: ① final-pool QD는 **seed 풀링**(10 seed × 10 = 100점)으로만
의미 있음, ② coverage보다 NN-distance·DE 같은 저표본 지표 우선, ③ L4
rarefaction으로 표본 보정.

### T5. final-pool QD와 search-QD는 별개 실험인가?

**별개로 보는 것이 적절하다.** 측정 대상이 다르다 — final-pool QD는
"산출물 포트폴리오의 다양성"(selection 이후, n≈10×seeds), search QD는
"알고리즘의 탐색 행동"(selection 이전, n≈수천, 예산 편향 L2 존재).
묶으면 L3 bias와 T4 불안정성이 서로 오염된다. 결과 파일도 scope 컬럼으로
분리(§S)했다.

### T6. 구현 난도가 예상보다 높아질 부분

1. **PFS 재설계 (D7)**: perturbed 패널 × K draws × 전 formula 재평가 —
   계산량이 K+1배. 1,675 formula × K=5 × ~2s ≈ 4.6시간/run/split. 캐시·
   샘플링 전략 필요.
2. **qlib native backtest (O8)**: 롱숏 커스텀 전략 작성 + 신호→포지션 변환
   어댑터 + qlib backtest 프레임의 학습 곡선 — simple 모드보다 며칠 단위.
3. **all_candidates descriptor (K3)**: 수천 formula × descriptor 세트 —
   TensorEvaluator로도 run당 수 시간. horizon 4개 × regime 분할이 곱해짐.
4. **AutoAlpha 궤적 로깅**: 우리 patch가 gplearn 경로에만 있음 — AutoAlpha는
   evolve 사본 작성 필요 + 비재현성(전역 random) 문제 동반.
5. DE의 0-채움 교정(J4)을 intersection으로 바꾸면 pool마다 공통 구간이
   달라져 비교 가능성 문제가 새로 생김 — 정의 확정이 먼저.

### T7. 코드만 보고 결정할 수 없는 hyperparameter/definition (연구자 결정 목록)

1. RRE rank 방향(ascending 유지?) 및 QD-RRE의 orientation(train_sign 적용 권장)
2. contrast `eps`(예: 1e-4)와 소분모 threshold
3. volatility regime: σ의 rolling window(예: 20d), 분위 경계(1/3·2/3 vs 1/2)
4. mid-tercile 제외 여부 (E7)
5. Horizon H의 스칼라 정의 (argmax k vs 장단 contrast)
6. liquidity 분할 기준 (median vs tercile) 및 footprint의 percentile 방향
7. PFS: σ 정의(지수 일수익률 σ 채택?), K, additive-input 채택 여부와
   legacy 병행 여부, Spearman 확정
8. label/execution: same-close 유지 vs next-open (O7), B8 경계 처리
9. grid 해상도·PC bounds·clip 규칙 (H1)
10. HQ threshold (metric, 값)
11. dedup: exact만 vs near-dup(corr 기준값, 계산 프록시)
12. MDD 부호, ICIR raw/ann 중 보고 기본값
13. QD reference set 구성 (어떤 method·seed·split을 좌표계 기준으로)
14. DE의 NaN 처리 교정 여부 (0-채움 유지=원본 재현 vs intersection=엄밀)

### T8. 구현 전 고정할 최종 design decisions 체크리스트

**(a) 계약 (전 파이프라인 공통)**
- [ ] splits: train/valid/test 날짜 확정 (예: 2010-16 / 2017-19 / 2021-24)
- [ ] market universe(들)와 매칭 벤치마크 지수
- [ ] label 정의 + B8 경계 규칙 + O7 execution 가정
- [ ] sign 규약: train_sign은 러너 memo 또는 B5 복원으로만; 평가기는 입력만
- [ ] missing/inf 규칙(B10 valid 스키마), manifest 파일 포맷(H1)

**(b) OOS**
- [ ] ICIR/RankICIR = raw (AlphaForge 관례), ann은 별도 컬럼
- [ ] daily series 저장 여부(권장: 저장)

**(c) QD**
- [ ] core descriptor set = [H, V, M, L, B] (Size 보류 — v1 §Q12)
- [ ] T7의 1-6, 9-13 값들
- [ ] RRE_qd = 교집합 재정규화 + oriented (C4/C5)
- [ ] PFS_qd = additive-input + Spearman + K-draw + min 저장 (D), legacy 병행 여부
- [ ] PCA fit = reference runs의 **valid** descriptor만 (G3)
- [ ] scope 우선순위: final_pool(즉시) → all_candidates(궤적 로깅 후)

**(d) Backtest**
- [ ] simple 모드 = 현행 20/20 구조 + cost config + 첫날 수정 + gross/net 분리
- [ ] qlib 모드 = 2단계로 (커스텀 롱숏 전략 필요)
- [ ] MDD/turnover 명명 확정 (P4/P5)

**(e) 인프라**
- [ ] pyarrow 설치 (parquet 전제)
- [ ] 궤적 로깅을 fast/tensor 러너에 추가 (K/L5의 전제)
- [ ] regression test 목록: verify_new_eval.py (A4/R5) + synthetic 5종 (R4)
- [ ] RNG 시드 규약 (R1) + cache key (R2) + provenance (R3)

---

## 부록 2: 후속 검증 5건 (논문 원문 대조 + 실측)

논문 원문(arXiv 2508.13174 HTML)을 직접 확인하고 3건을 추가 실측했다.

### (1) PFS paper_literal의 heterogeneous scale 문제 — **정규화 정의는 논문·공개코드 어디에도 없음 (최종 확인)**

- 논문 원문: "Let ε ∼ 𝒟 be a perturbation applied to the original **feature
  tensor X**" (X ∈ ℝ^{T×N×F}, raw financial features), σ = "the **average
  daily volatility** of the corresponding market index". **X의 정규화 언급
  없음** (전문 검색).
- 공개 코드(=이 저장소가 공식 구현): `noise_proc.py`가 유일한 노이즈 구현 —
  feature 정규화 없음. `my_modeltester.py`(AlphaEvolve 변형)도 diff 결과
  노이즈 방식 동일. 대신 **출력에 곱셈**(`df*(1+ε)`)이라 scale 문제를
  우회한 것으로 보인다(곱셈은 scale-free — 저자들이 additive-input의 scale
  문제를 이렇게 피해간 것으로 추정).
- 귀결: paper_literal `X+ε`에 절대 σ(≈지수 일변동성 ~0.01)를 그대로 쓰면
  **차원 부정합** — $volume(~1e8)·$close(~10²)에는 무의미하고
  $change(~0.01)에는 파괴적. paper_literal을 구현하려면 [결정] 필요:
  - (a) **곱셈-입력** `X·(1+ε)` — scale-free, 논문 의도(입력 섭동)에 가장
    가깝고 σ를 "상대 변동"으로 해석 (권장 후보)
  - (b) 필드별 상대 스케일링 `ε_f ~ N(0, (σ·scale_f)²)`, scale_f = 필드
    표준편차 또는 |X| — 덧셈 유지하되 필드별 보정
  - (c) 문자 그대로 절대 σ — 논문 표기와 일치하나 사실상 $change만 섭동

### (2) 논문 Eq.19–23 vs 코드 — 수치 예제 검증 완료

논문: Eq.19 `w=±1/K`(top/bottom-K), Eq.20 `r=wᵀy` (**gross 2, ÷2 없음**),
Eq.21 **AR = r̄·252 (산술 연환산 — CAGR 아님!)**, Eq.22 SR = r̄/σ·√252,
Eq.23 **Turn = mean‖w_t−w_{t−1}‖₁ (가중치 기반, 0.5 계수 없음)**, 거래비용
항 없음. K값·미명시, ΔT=1 기본.

수치 예제 (실행 검증):
```
하루: top {+2%,+4%}, bottom {−1%,+1%}
  paper r = 0.5·3% − 0.5·0% = 3.00%   |   code pnl = (3%+0%)/2 = 1.50%   → 정확히 2.0배
1년 시뮬레이션 (daily_paper = 2×daily_code):
  Sharpe  : 완전 동일 (scale-invariant) ✓
  AnnRet  : ×1.87 (CAGR 복리 때문에 정확히 2배 아님)
  MDD     : −18.5% vs −34.5%
```

코드와 논문의 차이는 결국 **4중**: ① 수익 스케일(gross 1 vs 2 — Sharpe만
불변), ② **AnnRet 정의 자체**(code CAGR vs paper 산술 r̄·252 — 같은
시계열에서도 다른 값), ③ turnover 정의(멤버십 카운트 비율 vs 가중치 ℓ1;
완전 교체 시 code 최대 2.0 vs paper 최대 4.0; 우리 제안
signal_weight_turnover=0.5·Σ|Δw|는 paper Eq.23의 절반), ④ 비용(코드만 차감).
→ §P1 권고 수정: **CAGR과 `AnnRet_arith(=r̄·252)`를 둘 다 저장**, AlphaEval
비교용은 arith 컬럼 사용.

### (3) DE_common의 common_cell_ratio — 실측 (test 2021–2024, market=all 그리드 969×5,655)

| pool | m | common/전체그리드 | common/union | factor별 유효비율 |
|---|---|---|---|---|
| 883883 random (all, 10개) | 10 | **2.4%** | 2.7% | **2.5%~87.5%** |
| 883929 gp (csi800, unique 3) | 3 | 0.3% | 99.9% | 0.3%~0.3% |

- **intersection 방식은 최악 factor가 지배한다**: random pool에서 유효비율
  2.5%짜리 factor 하나가 공통 셀을 2.4%로 끌어내림 (97% 이상의 데이터
  폐기). → DE_common은 pool 구성에 극도로 민감 — pairwise covariance
  (쌍별 교집합) 옵션이 실용적 대안 [결정 갱신].
- **부수 발견 (중요)**: 883929 승자 수식의 유효비율이 **0.3%**에 불과 —
  `Rsquare`가 rolling std≈0 구간을 NaN 마스킹(ops.py, atol=2e-5)하는데
  `Std(Var($factor,6),30)`은 기업행동 이벤트 부근을 제외하면 std≈0이라
  거의 전부 NaN이 된다. 즉 이 factor의 IC=0.075는 **일평균 ~수십 종목의
  초미니 cross-section**에서 계산된 값 — §B10의 `mean_cross_section_size`
  최소 기준이 필수적임을 실증 (예: 일평균 유효종목 < 30 → invalid).

### (4) same-close vs next-open — entry/exit timestamp와 return 식

신호는 항상 **t일 종가까지의 데이터**로 계산된다는 전제(현행 구조).

| 체결 방식 | 진입 시점 | 청산 시점 | return 식 (t행 기준) | qlib label 표현식 | 비고 |
|---|---|---|---|---|---|
| **same-close (현행)** | t일 15:00 종가 | t+1일 15:00 종가 | close_{t+1}/close_t − 1 | `Ref($close,-1)/$close - 1` | t 종가 정보로 t 종가 체결 — 실거래 불가능한 낙관적 가정 (look-ahead) |
| **next-open, O→O** | t+1일 09:30 시가 | t+2일 09:30 시가 | open_{t+2}/open_{t+1} − 1 | `Ref($open,-2)/Ref($open,-1) - 1` | 실행 가능. 오버나이트 갭(t종가→t+1시가)을 신호 수익에서 제외 |
| **next-open, O→C** | t+1일 09:30 시가 | t+1일 15:00 종가 | close_{t+1}/open_{t+1} − 1 | `Ref($close,-1)/Ref($open,-1) - 1` | 1일 내 체결·청산 — 일중 보유만 측정 |
| **delayed-close, C→C** | t+1일 15:00 종가 | t+2일 15:00 종가 | close_{t+2}/close_{t+1} − 1 | `Ref($close,-2)/Ref($close,-1) - 1` | 신호~체결 1일 지연 — 신호 감쇠 측정에 유용 |

- $open·$close 모두 번들에 있어 전부 즉시 계산 가능. label 문자열만 교체하면
  되므로 구조 변경 없음(§O7). qlib native 모드에서는 `deal_price="open"`이
  O→O에 대응.
- 주의: next-open 계열은 t+1 시가가 상하한가·정지면 체결 불가 — simple
  모드에서는 무시되고 qlib 모드에서만 처리됨(§O8).

### (5) search-QD core descriptor runtime — 1개 run 실측

test 그리드(969일×5,655종목, market=all), 883883 pool 10개 formula 평균:

| 구성요소 | formula당 |
|---|---|
| daily z-score | 110 ms |
| horizon IC ×4 (1/5/10/20d) | 485 ms |
| regime IC (vol/direction/liquidity) | 294 ms |
| breadth (N_eff) | 51 ms |
| signal_weight_turnover | 44 ms |
| **RRE_common (교집합 재정규화, 일별 rank 루프)** | **1,149 ms** |
| 소계 (frame 제외) | 2,133 ms |
| frame (신호 행렬 생성) | 벤치에선 캐시 적중(0ms) — 실제 **+0.5~3s** (수식 복잡도 의존) |

**현실 추정: formula당 ~3~5s → unique 1,675개(883929 규모) ≈ 1.5~2.5시간/run/split.**
지배 항은 RRE_common(54%) — rank 루프의 벡터화(예: bottleneck/argsort 2회)로
~3-5배 단축 여지 있음. PFS까지 포함하면 K+1배 재평가가 추가된다(§T6).

---

## 부록: 이 문서에서 수행한 실측 검증 로그

| 검증 | 방법 | 결과 |
|---|---|---|
| ICIR 관례 | 저장소 전체 grep | AlphaForge `icir=ic_mean/ic_std`(raw), `ricir` 존재 |
| RRE sign 불변성 | modeltester 로직 재현 수치실험 (T=60,N=40) | RRE(S)=0.698234 ≠ RRE(−S)=0.700572 |
| rank 방향/타이 | pandas 실측 | 작은값=1, tie=average |
| RRE universe | 결측 절반 날짜의 probs 합 | 일별 자기 유니버스 정규화(합=1) + 비재정규화 교집합 합산 |
| qlib backtest API | env에서 import + signature 검사 | backtest/Exchange(deal_price, limit_threshold, open/close/min_cost)/TopkDropoutStrategy 존재 |
| PFS 주입 지점 | qlib data.py 601-635행 + noise_proc.py 코드 확인 | 표현식 계산 **후** `df*(1+ε)` — 출력·곱셈 |
