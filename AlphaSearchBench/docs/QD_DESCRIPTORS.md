# QD_DESCRIPTORS — behavioral descriptor 정의·수식·해석·한계

공통: oriented signal(= train_sign × S) 사용, regime threshold는 **train
split에서 캘리브레이션 후 freeze** (calibration split = train; manifest의
`qd.regime_thresholds`에 수치 기록). contrast는
`D(a,b) = (a−b)/(|a|+|b|+eps)` (eps config, `|a|+|b| < threshold`면
`*_denom_small` 플래그). 모든 intermediate는 항상 저장 — scalar 정의를 나중에
바꿔도 재평가 없이 재집계 가능.

## Core set (v0.1)

### H — Information Horizon
- intermediate: `IC_1d, IC_5d, IC_10d, IC_20d` (forward return
  `close_{t+k}/close_t − 1`)
- 기본 reducer `weighted_abs_ic`: `H = Σ_h h·|IC_h| / Σ_h |IC_h|`
  (분모 극소 → NaN + `horizon_denom_small`)
- 해석: 신호의 정보가 어느 horizon에 실려 있는가 (1≈단기, 20≈장기)
- 한계: k>1 forward return은 overlapping — IC 유의성 주장에는 부적합
  (fingerprint 용도로만)

### V — Volatility Regime Response
- benchmark: market 매칭 지수 (csi300→SH000300, csi500→SH000905,
  csi800→SH000906, csi1000→SH000852, all→SH000985)
- 지수 일수익률의 rolling σ(기본 20d) → train 1/3·2/3 quantile로 low/high
  (mid는 기본 제외 — config)
- `V = D(IC_high_vol, IC_low_vol)`; intermediate: `IC_high_vol, IC_low_vol,
  n_high_vol_days, n_low_vol_days`
- 해석: +1≈고변동장 특화, −1≈저변동장 특화

### M — Market Direction Response
- 지수 수익률 >0/<0 (0은 제외); `M = D(IC_up, IC_down)`

### L — Liquidity Response
- `ADV20 = rolling_mean($amount, 20)` → 일별 cross-sectional percentile →
  기본 tercile 분할 (**cell 단위** 조건 IC)
- `L = D(IC_liq_high, IC_liq_low)`; 해석: +1≈유동성 상위 특화

### B — Activation Breadth
- oriented daily z-score 가중 `w ∝ z`:
  `p_i=|w_i|/Σ|w_j|, N_eff=1/Σp_i², Breadth = mean_t N_eff/N_valid(t)`
- 20/20 quantile membership을 쓰지 않는 이유: 상수(≈0.4)로 퇴화
- 해석: 1≈균등 분산 베팅, →0≈소수 종목 집중

### R — RRE_qd
- METRICS.md 참조. oriented + 공통 universe 재정규화. 1≈랭킹 안정.

## Structural (항상 계산, PCA core 포함 여부는 manifest 선택)

| descriptor | 정의 | 주의 |
|---|---|---|
| `signal_coverage` | mean_t n_valid(t)/n_universe(t) | **Breadth와 다름** — coverage=값을 만들 수 있는 범위, breadth=만든 값의 분산도 |
| `signal_weight_turnover` | 0.5·Σ|w_t − w_{t−1}| (w=z-비례) | backtest의 `portfolio` turnover와 별개 명칭 |
| `liquidity_footprint` | mean_t Σ|w_i|·liq_pct_i | L(조건 IC 차이)과 별개 — 베팅 위치의 유동성 |

## 개념 구분 (재강조)

```
Signal Coverage ≠ Activation Breadth ≠ QD Coverage
AlphaEval DE (signal-space 통계 다양성) ≠ QD Coverage (behavior-space 다양성)
Final-Pool QD (남긴 것) ≠ Search-QD (탐색한 것)
```

## 알려진 한계 / 예상 중복 (F4 진단으로 확인할 것)

- RRE_qd ↔ signal_weight_turnover: 둘 다 랭킹/가중치의 시간 안정성 — 강한
  음상관 예상 → descriptor_diagnostics_* 산출물로 확인 후 set 조정
- PFS_G ↔ PFS_t: 동일 σ·구조 — 높은 양상관 예상 (min을 두는 이유)
- Horizon ↔ turnover: 장호라이즌 신호는 느리게 변함
- Size Response는 market cap 데이터 부재로 **미구현** (v1 blueprint §Q12)
- descriptor는 짧은 split에서 노이즈가 큼 — `n_*_days`, denom_small 플래그와
  함께 해석할 것
