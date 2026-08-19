# BACKTEST — 포트폴리오 구성·체결 가정·비용·turnover

## 포트폴리오 (simple 모드, v0.1 확정)

```
top X% long / bottom X% short (기본 20/20, config)
equal weight — long gross 0.5 / short gross 0.5
Σ|w| = 1 (gross 1), Σw = 0 (dollar-neutral), daily rebalance
```

수학적 동치: AlphaEval `pnl = (long_ret + short_ret)/2` (Alphaagent/
backtester.py) — 단 논문 Eq.19-20의 w=±1/K는 **gross 2**라 일수익이 2배
(Sharpe는 scale-invariant로 동일).

## Signal timing과 execution timing (핵심 표)

신호는 항상 **t일 종가까지의 정보**로 계산된다.

| execution | 진입 | 청산/리밸런스 | return 식 (t행) | 성격 |
|---|---|---|---|---|
| `same_close` | t 15:00 종가 | t+1 종가 | close_{t+1}/close_t − 1 | **legacy/optimistic** — t 종가 정보로 t 종가 체결(실거래 불가) — 연구 기본값 금지 |
| **`next_open_oo`** (기본) | t+1 09:30 시가 | t+2 시가 | open_{t+2}/open_{t+1} − 1 | 실행 가능한 연구 기본값 |
| `next_open_oc` | t+1 시가 | t+1 종가 | close_{t+1}/open_{t+1} − 1 | 일중 보유 |
| `delayed_close_cc` | t+1 종가 | t+2 종가 | close_{t+2}/close_{t+1} − 1 | 신호 1일 감쇠 측정 |

OOS label(close→next-close)과 backtest execution은 **분리**되어 있다 —
OOS는 예측력, backtest는 집행 가정을 측정한다.

## Turnover / Cost

```
turnover_l1     = Σ|w_t − w_{t−1}|          (AlphaEval 논문 Eq.23 정의)
turnover_oneway = 0.5 × turnover_l1
cost_t          = transaction_cost_rate × turnover(config: oneway|l1)
net_t           = gross_t − cost_t          (셋 다 daily로 저장)
```

- 첫날은 무포지션→건립: l1 = Σ|w| = 1 → **건립 비용이 부과된다** (legacy의
  첫날 NaN cost 버그를 명시적 규칙으로 대체).
- full flip(전 종목 반전): gross-1 기준 l1 = 2, oneway = 1.
- 어느 정의로 비용을 계산했는지 manifest에 기록된다.

## 결측/정지 처리 (simple 모드 가정)

- 가중치는 signal-valid 종목으로 구성.
- execution return이 NaN인 보유 종목(정지 등)은 그날 손익 기여 0
  (포지션 유지·무손익 가정) — `n_missing_returns`로 기록.
- long 또는 short를 구성할 수 없는 날은 무포지션(`n_skipped_days`).

## 성과 지표

METRICS.md 참조 — `AnnRet_arith`(논문 비교)와 `CAGR`를 **둘 다** 저장,
MDD는 양수 크기, `mean_daily_turnover_*` / `annualized_turnover_*` 분리.

## qlib native 모드 [optional integration]

Phase 8 timestamp audit로 실증된 지원 범위:

- `deal_price="open"`: 주문이 해당 거래 스텝 날짜의 **시가로 체결**됨을
  가격 일치로 확인.
- **신호 t → t+1 시가 체결** (spike-신호 실험으로 lag 실증 —
  `tests/smoke/test_phase8_qlib_timestamp.py`).
- **naked short는 Exchange가 조용히 미체결 처리** → qlib native는
  **long-only**만 지원한다. long-short 연구 백테스트는 simple 모드 전용.
- suspension/limit-up-down/비용은 qlib Exchange가 처리
  (`limit_threshold`, `open_cost/close_cost/min_cost` — config `backtest.qlib.*`).

qlib 모드 결과는 `mode="qlib_long_only"`로 표기되어 simple 모드와 혼동되지
않는다.
