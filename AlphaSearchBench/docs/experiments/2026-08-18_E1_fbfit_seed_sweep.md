# E1 — fb_fitness seed sweep (재현성 판정)

| 항목 | 내용 |
|---|---|
| 실험 이름 | E1 fb_fitness seed sweep |
| **Alpha Mining Framework** | `gplearn_asb` (GP, vendored 무수정) |
| **평가 프레임워크** | `AlphaSearchBench` v0.1.0 — E4 체인에서 fixed-HOF repool 후 4-arm 프로토콜 스윕 |
| 실험 세팅 | fb_fitness·strict_penalty·csi800·2010–19, **seed 0/1/2/3**(기존 42에 추가) / 평가: ASB-P 4-arm, split train 2010–19·valid 2020·test 2021–24 |
| 목적 | 유일한 test 흑자 pool(fbfit_42, A1 Sharpe +0.95 / A3 초과AR +17.2%)이 seed를 바꿔도 재현되는지 판정 |
| 소모 시간 | 마이닝 4 job 병렬 2h49m~3h33m (888250–3, cpu1) + E4 체인(repool·스윕) 1h9m (888350) |
| 결과 요약 | **재현 실패 — 5-seed 중 흑자 1개(42)뿐**(사전 규칙상 "seed 의존" 구간, 실질적으론 seed 42 행운). 단 **탐색 자체는 완전 재현**: 5 seed 전부 같은 $amount-분산 저회전 계열로 수렴(train fb 0.14–0.17). 다음 행동: "격차=신호 문제"를 최종 판정으로 확정, fb 계열은 "안정적으로 발견되나 OOS 수익성 없음"으로 기록. |

## 1. Context — 이 실험을 계획한 이유

E3(프로토콜 4-arm 스윕)에서 결정 게이트(A3 초과AR ≥ +4%)를 넘은 pool은
fbfit_42 하나였다(+17.2%, IR 1.29 — 논문 CSI500 대역). 그러나 1-seed 단발이라
"프로토콜이 격차 원인"이라는 결론이 이 run의 재현성에 조건부였다.
사전 판정 규칙: 5-seed 중 **3+에서 A3 초과AR>0 → 재현 / 1–2 → seed 의존 /
0 → seed 42 우연**.

## 2. 밝히고자 하는 목적과 사전 고정 판독 규칙

위 3구간 규칙(계획 파일 WS-B 절에 결과 확인 전 고정). 부가 관찰 목표:
seed별 승자 수식이 같은 계열인지(탐색 재현성)와 pool 수익 재현성을 분리 관찰.

## 3. 실험 세팅

### 3-A. Alpha Mining Framework 세팅 — `gplearn_asb`
`configs/experiments/ablation_fbfit.yaml` + `--seed {0,1,2,3}`. 핵심:
fitness_metric=fb_fitness(= net_sharpe×√(|AnnRet|/연회전, ASB 의미론)),
constraint.mode=strict_penalty, validity threshold(coverage 0.05/median_n 30/
valid_day 0.90), hof_mode=original(비교 일관성; fixedhof는 repool로 병행),
static_gate=true, pop 1000×5세대, hall_of_fame 50→n_components 10,
worst=-1e6, stopping=1e9. 세부는 각 run manifest
(`out/pilot_csi800_fbfit_{s}/manifests/run_*.json`) 참조.

### 3-B. AlphaSearchBench 평가 세팅
E3와 동일한 4-arm(A1/A2/A3/A4), split train 2010–19 / valid 2020 /
test 2021–24, equal-weight 결합, backtest-only 스윕
(`out/protocol_sweep/ws_b_e4/manifests/sweep_ws_b_e4.json`).

### 3-C. 재현 정보
마이닝 job 888250–888253(cpu1), repool+스윕 체인 job 888350,
산출 `out/protocol_sweep/ws_b_e4/metrics/protocol_sweep_pool.parquet`(48행 =
6 run×2 HOF×4 arm).

## 4. 결과 요약 (수치)

**pool 수익 (as-submitted, original HOF):**

| seed | A1 Sharpe | A3 초과AR | A3 IR | 승자 train fb | 승자 train \|IC\| |
|---|---|---|---|---|---|
| 0 | −1.21 | −4.2% | −0.33 | +0.154 | 0.011 |
| 1 | −1.13 | −5.9% | −0.42 | +0.167 | 0.005 |
| 2 | −1.28 | −7.3% | −0.62 | +0.171 | 0.004 |
| 3 | −0.99 | −3.6% | −0.27 | +0.144 | 0.010 |
| **42** | **+0.95** | **+17.2%** | **+1.29** | +0.151 | 0.006 |

fixedhof(10수식 다양화) 변형은 seed 42 포함 **전부 음수**. 게이트 판독:
**흑자 1/5 → 사전 규칙상 "seed 의존"** — 그리고 4개 seed가 명확한 음수(−3.6
~−7.3%)여서 실질 해석은 "seed 42의 행운"에 가깝다.

**탐색 재현성(대조적):** 5 seed 승자 전원이 $amount 분산·산포 계열
(`Std(Mad($amount,5),30)`, `EMA(Var($amount,12),30)`, `Std(WMA($amount,5),64)`
등), train fb 0.14–0.17로 균질, 연회전 3–8배.

## 5. 결과의 정성적 해석

fb_fitness는 **탐색 목표로서는 잘 작동한다** — 어느 seed든 같은 저회전
니치를 찾아낸다(niche 발견의 재현). 문제는 그 니치의 train-창 fb(~0.15)가
test(2021–24) 수익으로 **전이되지 않는다**는 것: 같은 계열 5개 표본 중 1개만
흑자라면 +17.2%는 계열의 실력이 아니라 표본 분산이다. E3의 "격차는 프로토콜"
결론은 이로써 **조건 탈락** — 종합 판정은 "프로토콜은 증폭기, 지배 원인은
신호 부재"로 수렴한다. 이는 참고연구 GP 베이스라인의 test-구간 붕괴(AlphaAgent
논문 Fig 4)와도 정합한다.

## 6. 한계·교란변수

seed 5개는 "재현 실패"를 말하기엔 충분하나 계열의 기대수익 추정에는 부족
(n=5 기술통계만). test 창이 단일(2021–24 약세장)이라 "계열이 영원히 무효"
가 아니라 "이 레짐에서 무효"까지만 주장 가능. fixedhof 다양화가 모든 seed에서
성과를 낮춘 것은 계열 내 중복이 아니라 계열 밖 잡음 수식 편입 때문일 수 있음
(pool 구성 분석은 E6 노트북에서).

## 7. 다음 실험으로의 연결

① 종합 판정 확정 → 다음 사이클 의제는 miner(신호) 개선: 결합층·다양성
압력·기간/universe 확장. ② E5(새 split 공식 재평가)는 계획대로 진행하되
"승격 프로토콜" 서사 없이 — A1을 기준 보고, A3는 논문 anchor로.
③ backtest_design.md의 DCS 관점에서 fbfit_42는 "12셀 중 소수 셀 흑자"형 —
프로파일 보고의 필요성을 보여주는 실례로 §6에 편입.
