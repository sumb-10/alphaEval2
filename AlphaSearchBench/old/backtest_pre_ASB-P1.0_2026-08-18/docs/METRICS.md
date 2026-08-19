# METRICS — 전 지표의 수식과 정의

표기: `S`=signal 행렬(일×종목), `y_k`=k일 forward return, `U`=point-in-time
universe mask, valid cell = `finite(S) ∧ U`. 일별 지표는 valid cell에서 계산.

## OOS

| 지표 | 정의 |
|---|---|
| daily IC_t | Pearson corr( oriented S[t,·], y_k[t,·] ) — 유효쌍<2 또는 퇴화 시 NaN |
| daily RankIC_t | 위와 동일하되 일별 rank(ascending, tie=average) 후 Pearson (=Spearman) |
| IC / RankIC | finite 일별 값의 평균 |
| **ICIR** | mean(IC_t)/std(IC_t, ddof=1) — **raw, √252 없음** (AlphaForge `train_AFF.py` 관례) |
| ICIR_ann | ICIR × √252 (별도 컬럼) |

oriented S = train_sign × S, `train_sign = sign(signed_train_IC)` (train에서만).

legacy와의 문서화된 차이: AlphaEval `ictester.calculate1`은 ±inf 셀을 corr에
포함시키고(그날 IC가 NaN이 됨) NaN일 비율>50%면 0.0을 반환한다. ASB는 inf를
invalid cell로 제외하고 병리는 validity로 보고한다. inf 없는 formula에서는
legacy와 1e-9 이내 일치 (regression 테스트 실증).

## Validity

- **hard invalid** (mode와 무관하게 downstream 제외): `formula_eval_failed`,
  `all_nonfinite`, `no_correlatable_day`(유효쌍≥2·분산>0인 날 0일),
  `zero_ic_observations`
- research threshold: config (`validity.*`, 기본 null=report only)
- 통계 정의: `daily_signal_coverage = n_valid_signal(t)/n_universe(t)`;
  일별 통계(mean/median/p10/min)는 split 전체 거래일 기준(무신호일 = 0);
  `const_day_ratio`는 유효쌍≥2인 날 중 분산 0인 날의 비율.

## QD — RRE

**RRE_qd (research)**: 날짜쌍마다 공통 universe `Uc = valid_t ∩ valid_{t−1}`
에서 rank(tie=average)를 다시 계산,

```
p_t(i) = rank_t(i)/Σ_j rank_t(j)     (i ∈ Uc)
KL_t   = Σ_i p_t(i)·log(p_t(i)/p_{t−1}(i))
RRE_qd = mean_t 1/(1+KL_t)
```

oriented signal 사용 (RRE는 sign 반전에 **불변이 아님** — 수치 실증:
blueprint v2 §C5). `rre_mean_common_n / rre_min_common_n / n_pairs_*` 병행 저장.

**RRE_legacy**: AlphaEval 공개코드(modeltester 313-327행) 재현 — union 그리드
pandas rank, eps=1e-8이 분자·분모에 삽입, universe 변경 시 재정규화 없는
교집합 합산(진짜 KL 아님). regression 테스트로 스니펫과 1e-12 일치 확인.

## QD — PFS

3개 모드를 이름으로 분리한다:

| 모드 | 섭동 | 상관 | 결과 컬럼 |
|---|---|---|---|
| `legacy_alphaeval` | **출력** S·(1+ε) | 일별 Pearson | `PFS_*_legacy` |
| `paper_literal` (기본) | **입력** X+ε (raw feature tensor) | 일별 **Spearman** | `PFS_Gaussian/PFS_t/PFS_min` |
| `relative_input` (**experimental**) | 입력 X·(1+ε) | 일별 Spearman | `PFS_*_relative_input` |

- σ = train benchmark **일수익률** std ("corresponding market index average
  daily volatility"의 해석), train-frozen.
- Student-t: ν=3, `t·σ·√((ν−2)/ν)`로 Gaussian과 동일 std.
- `PFS = mean_t Spearman(S[t,·], S'[t,·])`의 K-draw 평균 —
  **flatten-all-cells 방식이 아님**. `PFS_min = min(G, t)`.
- 결정론: noise는 (market, split, noise_type, seed, draw, dataset_version,
  mode) 키의 `default_rng`로 생성 — **모든 formula/method가 동일 perturbed
  tensor를 공유**한다.

> **scale ambiguity (필수 고지)**: 논문은 heterogeneous raw feature X의
> normalization을 정의하지 않는다 (원문·공개코드 전수 확인 — blueprint v2
> 부록 2). 따라서 `paper_literal`의 절대 σ 덧셈은 $volume(~1e8)에는 사실상
> 무영향, $change(~σ 스케일)에는 지배적이다. `PFS_research`의 최종 섭동
> semantics는 pilot 후 결정하며, experimental policy를 기본값으로 쓰지 않는다.

## QD — Diversity Entropy (pool 전용)

`AlphaEval_DE_legacy`: 일별 z-score → NaN→0 → (time·asset) flatten →
`np.cov` → eigvalsh → 음수 0 클립 → `−Σ p·log p / log(m)`
(modeltester 202-229행 재현; NaN→0 채움이 DE를 부풀릴 수 있음 — 문서화).

`DE_common_valid`: validity 통과 factor들이 **모두 valid한 common cell**에서
동일 절차. `n_common_cells / common_cell_ratio / n_factors_used /
n_factors_dropped` 병행 저장, 표본<2면 **NaN + reason**. pairwise DE는 v0.1
공식 metric이 아니다 (PSD 문제).

## QD — pool 공간 지표

- `QD Coverage = occupied_bins / total_bins` (고정 grid, overflow는 클리핑
  않고 `overflow_ratio`로 기록)
- `H_global = −Σ p·log p / log(N_total_bins)`,
  `H_even = −Σ p·log p / log(N_occupied)` (N_occupied=1 → 1.0)
- NN distance: PCA 2D와 표준화 raw descriptor 공간 각각 mean/median
- HQ coverage: config의 (metric, threshold)로 필터 후 coverage —
  threshold를 test 분포로 자동 결정하지 않는다
- Rarefaction: 고정 N, R회 비복원 subsampling(시드 고정) →
  `E[coverage@N] ± std`

## Backtest

| 지표 | 정의 |
|---|---|
| **AnnRet_arith** | mean(daily net) × 252 — AlphaEval 논문 Eq.21 비교용 |
| **CAGR** | (1+cum_net)^(252/n) − 1 |
| Sharpe | mean(net)/std(net, ddof=1) × √252, rf=0 (인터페이스 개방) |
| **MDD** | 누적곡선 낙폭의 **양수 크기** |
| turnover_l1 | Σ|w_t − w_{t−1}| (논문 Eq.23 정의) |
| turnover_oneway | 0.5 × l1 |
| cost | rate × turnover(config: oneway\|l1) — gross/cost/net 분리 저장 |

주의: 논문 포트폴리오(w=±1/K)는 gross 2, ASB simple은 gross 1 — 일수익이
2배 관계(Sharpe는 불변). full flip 시 gross-1 기준 l1=2, oneway=1.
