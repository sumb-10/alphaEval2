# E3 — 프로토콜 4-arm 스윕 (측정 동등화 결정 게이트)

| 항목 | 내용 |
|---|---|
| 실험 이름 | E3 프로토콜 4-arm 스윕 |
| **Alpha Mining Framework** | 없음 — **재평가 전용**. 입력 pool 29개는 `gplearn_asb`(28: off/strict/hard/netsharpe/ictstat/nsguard/fbfit ± fixedhof)와 `AlphaAgent_asb`(1: Exp B, 빈 pool)의 기존 완주 run |
| **평가 프레임워크** | `AlphaSearchBench` v0.1.0 — validity gate + backtest만 (`scripts/protocol_sweep.py`, 공식 `EvaluationRun` 경로 재사용) |
| 실험 세팅 | 29 pool × 4 프로토콜(A1 현행 LS / A2 저회전 LS / A3 논문형 qlib long-only / A4 repo 원형), split = train 2010–19 / valid 2020 / test 2021–24, equal-weight 결합 |
| 목적 | 수익 격차(전 pool 손실 vs 참고연구 AR 11%)가 **포트폴리오 프로토콜**에서 오는지 **신호 부재**에서 오는지 판별 |
| 소모 시간 | 1h 59m (job 888258, cpu1; 116행 산출) |
| 결과 요약 | ① 게이트 통과 pool은 **fbfit_42 단 1개**(A3 초과AR **+17.2%**, IR 1.29 — 논문 CSI500 대역 도달). ② \|IC\| 계열은 회전을 159→23배로 눌러도(A2/A3) 전부 음수(초과AR −1~−13%) → **신호 부재 확정**. ③ 다음 행동: A3를 보고 프로토콜로 승격하되, "프로토콜 원인" 결론은 저회전-fb 계열에 한정. |

## 1. Context — 이 실험을 계획한 이유

전 GP pool이 test(2021–24)에서 손실(A1 Sharpe −2.8~−4.4)이었고 fb_fitness(seed
42)만 흑자(+0.95)였다. gross/비용 분해(`backtest_pool_metrics`)에서 |IC| pool의
연회전(편도) 96~193배 × 15bps = 연 14~29%p 비용 드래그가 확인됐지만 gross도
~0이어서, "비용(프로토콜) 문제"와 "신호 문제"를 분리할 수 없었다. 참고연구
실측(AlphaAgent KDD'25 §4.1.2)에서 논문 프로토콜은 top-50/drop-5 long-only로
회전을 구조적으로 상한(일 ~10%)함을 확인 — 같은 pool을 프로토콜만 바꿔
재평가하면 두 원인이 분리된다.

## 2. 밝히고자 하는 목적과 사전 고정 판독 규칙

가설: 손실 = (i) 회전 상한 없는 프로토콜 × (ii) 약한 신호의 중첩.
판독 규칙(결과 확인 **전** 계획 파일에 고정):
* A3에서 **초과 AR ≥ +4%**(논문의 hit-ratio 바) 도달 pool 존재 → "격차는
  프로토콜" — A3를 ASB 기본 보고 프로토콜로 승격.
* A2에서 비용 드래그 ~1/5로 줄어도 net 음수 **그리고** A3 초과수익 <0 →
  "격차는 신호" — 다음 사이클을 miner 개선으로 전환.

## 3. 실험 세팅

### 3-A. Alpha Mining Framework 세팅

**이 실험은 마이닝 없음(재평가 전용).** 입력 pool 29개의 마이닝 세팅은 각
run의 `gplearn_asb/out/<run>/manifests/run_*.json`에 기록되어 있으며 공통:
csi800, 탐색 창 2010–2019, pop 1000×5세대, hall_of_fame 50→n_components 10.
계열별 차이는 fitness_metric(abs_ic/net_sharpe/ic_tstat/fb_fitness)과
constraint.mode(off/hard/strict), `_fixedhof` 접미사는 동일 run의 pool을
fixed-HOF로 재선발한 파생본(`scripts/repool_fixed_hof.py`).
AlphaAgent Exp B(빈 pool)는 `empty_pool`로 기록되고 수치에서 제외됐다.

### 3-B. AlphaSearchBench 평가 세팅 (manifest 자동 추출)

`scripts/manifest_to_report_table.py --sweep out/protocol_sweep/ws_a_e3` 출력:

| arm | config | backtest 핵심 |
|---|---|---|
| A1 | `csi800_ref.yaml` | simple, `next_open_oo`, 분위 20/20 LS, 매일, 15bps·oneway |
| A2 | `csi800_ref_lowturn.yaml` | simple, `next_open_oo`, **topk 50** LS, **5일 보유**, 15bps·oneway |
| A3 | `csi800_ref_qlib.yaml` | **qlib TopkDropout top50/drop5 long-only**, deal=open, 매수 5bps/매도 15bps, 지수(SH000906) 대비 초과 AR·IR |
| A4 | `csi800_ref_legacy.yaml` | simple, **`same_close`(무지연)**, 분위 20/20 LS, 15bps·**l1** |

공통: split train 2010-01-01~2019-12-31 / valid 2020 / test 2021-01-01~2024-12-31
(valid는 마이닝 창 밖 — 오염 없음), pool 가중 equal_default, validity gate
threshold는 마이닝과 동일 3종. 참고연구 대비 잔여 편차: universe csi800(논문
CSI500), benchmark SH000906(논문 SH000905), 결합층 equal-weight(논문 LightGBM).

### 3-C. 재현 정보

Slurm 888258(cpu1), 커맨드 `scripts/slurm_protocol_sweep.sbatch ws_a_e3`,
산출 `out/protocol_sweep/ws_a_e3/metrics/protocol_sweep_pool.parquet`(116행) +
`manifests/sweep_ws_a_e3.json`. 코드: WS-A/E0 변경분(runner qlib dispatch,
`qlib_native.evaluate_pool`, 초과수익 지표, simple의 topk/rebalance_days) —
단위 11 + ASB 회귀 90 통과 상태.

## 4. 결과 요약 (수치)

**게이트 판독: A3 초과 AR ≥ +4% 도달 pool = 1개 / 27개.**

| pool (A3) | 초과AR | IR | 절대AR | MDD | 연회전(편도) |
|---|---|---|---|---|---|
| **fbfit_42** | **+17.2%** | **+1.29** | +12.7% | 28.0% | 5.2× |
| ictstat_42 (2위) | −0.4% | −0.04 | −8.4% | 36.8% | 24× |
| … 나머지 25개 | −1.0% ~ −26.8% | 전부 음수 | | | |

**arm × 계열 평균** (fbfit=2 pool, strict=10 pool 등; 전표는 parquet):

| 계열 | A1 Sharpe (회전) | A2 Sharpe (회전) | A3 초과AR | A4 Sharpe |
|---|---|---|---|---|
| fbfit | +0.37 (4.7×) | +0.23 (5.1×) | **+7.1%** | +0.36 |
| strict (\|IC\|) | −3.56 (159×) | −0.86 (39×) | −13.3% | −6.22 |
| off (\|IC\|) | −2.76 (150×) | −0.85 (37×) | −13.4% | −4.92 |
| ictstat | −4.25 (172×) | −0.92 (37×) | −3.8% | −8.43 |
| netsharpe | −1.46 (25×) | −0.89 (16×) | −11.1% | −2.03 |

## 5. 결과의 정성적 해석

**두 결론이 동시에 참이다.**
① **프로토콜은 실재하는 격차 요인** — 단, 저회전 신호가 실존할 때만.
fbfit_42는 A1(가혹) +7.7% → A3(논문형) 초과 +17.2%/IR 1.29로, 논문의
AlphaAgent CSI500 수치(AR 11.0%/IR 1.49) 대역에 도달했다. 초과분 중 ~4.6%p는
2021–24 지수 하락분(롱온리의 초과수익 확대 효과)임을 명시한다.
② **\|IC\| 계열의 손실은 프로토콜로 구제 불가** — A2가 회전을 159→39배로,
A3가 23배로 눌러 Sharpe가 −3.6→−0.9까지 개선되지만 **0을 넘지 못한다**.
gross 분해(gross ~0)와 정확히 일치: 비용이 손실의 크기를 키웠을 뿐, 비용을
제거해도 초과수익을 만들 신호가 없다. 이는 참고연구 자신의 GP 베이스라인
붕괴(논문 Fig 4: IC 0.022→~0; AlphaEval 벤치마크 GP PPS 0.017)와 정합적이다 —
**우리 GP는 문헌의 GP 베이스라인을 재현하고 있다.**
③ 부수 발견: A4(repo 원형, same_close+l1)는 4-arm 중 최악(strict −6.2) —
무지연 체결의 낙관 편향보다 l1(왕복) 비용 부과가 지배해, 원조 repo 프로토콜이
오히려 가장 징벌적임이 드러났다.

## 6. 한계·교란변수

* fbfit의 게이트 통과는 **seed 42 단 1개** — 재현성은 E1(seed 0–3)이 판정하며,
  그 전까지 "프로토콜 원인" 결론은 fb 계열 잠정이다. fixedhof로 10수식
  다양화하면 A3에서도 음수(−3.0%) → 흑자가 소수(3개) 수식에 집중.
* A3는 롱온리라 시장 위험 내재(MDD 28% vs A1 9%) — Sharpe/MDD 직접 비교 금지.
* universe(csi800 vs 논문 CSI500)·benchmark·결합층(equal vs LightGBM) 편차 잔존.
* n<3인 계열(hard/ictstat/nsguard/fbfit)은 기술통계만 — inferential 주장 금지.

## 7. 다음 실험으로의 연결

* **E1/E2**(fb seed sweep + IC-floor, 실행 중) → 5-seed 중 3+에서 A3 초과AR>0
  이면 "재현" 판정 → E4에서 fixedhof repool 후 본 스윕에 편입.
* **E5**: A3를 승격 프로토콜로 공식 재평가(allcand 포함). \|IC\| 계열은 "신호
  문제" 확정이므로 다음 사이클 의제는 miner 개선(결합층·다양성 압력·기간)이다.
* REPORT.md §9와 로드맵 체크박스 갱신(규칙 ③).
