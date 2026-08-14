# DATA_CONTRACT — 입력/출력 스키마

AlphaSearchBench core는 **표준 스키마에만 의존**한다. 특정 miner(gplearn,
AutoAlpha, LLM miner, …)의 내부 구현과 결합되는 코드는
`alphasearchbench/instrumentation/`(optional adapter)에만 존재한다.
스키마만 만족하면 어떤 miner의 산출물도 평가할 수 있다.

## 입력 1 — miner result (`--input`, csv/pkl/parquet)

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `formula` | ✓ | Qlib 표현식 문자열 (엔진이 파싱 — 실패 시 hard invalid) |
| `signed_train_IC` | | train split의 signed daily-IC 평균. **없으면 train 재평가로 복원**(복원 여부는 `train_sign_restored`로 기록) |
| `train_sign` | | ±1 (signed_train_IC가 있으면 무시 가능) |
| `IC` | | 레거시 \|IC\| (참고용 — ASB는 사용하지 않음) |
| `method`, `seed` | | 없으면 CLI `--method/--seed-id` 또는 파일명에서 유추 |

행 중복(동일 formula 반복)은 허용 — pool 결합에는 행 순서대로 weights가
대응되고, QD point는 exact dedup된다(원본 기록은 보존).

## 입력 2 — weights (`--weights`, json/csv, optional)

`{"weights": [...]}` json 또는 1열 csv. 길이 = result 행 수.
**미제공 시 equal weights(1/n)로 대체**되며 manifest에
`weights_source: "equal_default"`로 기록된다 (train-학습 weights 사용 권장).

## 입력 3 — trajectory (`--trajectory`, jsonl, optional)

한 줄 = 평가된 후보 하나:

| 필드 | 필수 | 설명 |
|---|---|---|
| `run_id, method, seed` | ✓ | run 식별 |
| `generation` | ✓ | 세대 (int) |
| `idx_in_population` | ✓ | 세대 내 위치 |
| `formula` | ✓ | |
| `raw_fitness` | ✓ | miner의 적합도 (예: \|IC\|) |
| `signed_train_IC` | | |
| `operation, parent_idx, donor_idx` | | 유전 연산 계보 |
| `program_length, program_depth` | | |
| `memo_hit` | | 캐시 적중 여부 |

trajectory가 없으면 Search-QD는 생략되고 final-pool QD만 수행된다(graceful).
gplearn/AutoAlpha용 수집 어댑터: `instrumentation/gplearn.py`(monkey-patch),
`instrumentation/autoalpha.py`(LoggingEvaluator) — 원본 miner 소스 무수정.

## 출력 (out/)

### metrics/*.parquet

- `validity_factor_metrics`: formula, valid, hard_valid, invalid_reason,
  formula_eval_failed + 통계 전체(n_valid_days, coverage 분포,
  const_day_ratio, nan/inf_cell_ratio, …) + research_fail_*
- `oos_factor_metrics`: method, seed, formula, signed_train_IC, train_sign,
  train_sign_restored, IC/RankIC/ICIR/RankICIR/ICIR_ann/RankICIR_ann
  (+horizon별 `_kd` suffix), n_ic_obs, valid, invalid_reason
- `oos_pool_metrics`: 결합 신호 기준 동일 지표 + n_factors,
  n_unique_factors, weights_source, n_factors_dropped_by_gate
- `qd_factor_descriptors`: raw descriptor 전체(IC_kd, IC_high/low_vol,
  IC_up/down, IC_liq_*, 각 contrast+denom_small, breadth,
  signal_coverage, signal_weight_turnover, liquidity_footprint,
  rre_qd+common_n 진단) × {test(무prefix), valid_ prefix} + drift_* +
  PCA1/PCA2/valid_PCA1/valid_PCA2/projected +
  descriptor_drift_raw/pca (+PFS_* — pfs.enabled 시)
- `qd_pool_metrics`: scope, coverage, occupancy_entropy_global/evenness,
  overflow_ratio, pca2d_nn_*/rawstd_nn_*, hq_coverage,
  rarefaction(expected/std@N), AlphaEval_DE_legacy,
  de_common_valid(+n_common_cells/common_cell_ratio/
  n_factors_used/dropped/reason), budget_*(trajectory 제공 시)
- `qd_generation_metrics`(trajectory 시): 세대별 n_candidates/n_unique/
  valid_rate/quality/coverage/entropy/new·cumulative bins/centroid(+이동)
- `backtest_factor_metrics` / `backtest_pool_metrics`: AnnRet_arith, CAGR,
  Sharpe, MDD(양수), mean/annualized_turnover_l1/oneway,
  total_transaction_cost, gross/net cumulative, execution, cost config

### daily/

`oos_daily`(date, formula_id, horizon, IC, RankIC, n_valid, coverage_ratio),
`backtest_daily`(date, formula_id, gross/cost/net, turnover_l1/oneway,
long/short_count, gross/net_exposure, n_missing_returns, cumulative_return)

### manifests/

`run_<method>_<seed>.json`(REPRODUCIBILITY.md), `qd_projection/`
(scaler.pkl, pca.pkl, qd_manifest.json), `descriptor_diagnostics_*`
