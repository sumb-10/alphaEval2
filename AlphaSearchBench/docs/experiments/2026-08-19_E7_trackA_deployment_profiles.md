# E7 — Track A 8구성 스윕 + 첫 배치 프로파일 (ASB-P1.0-draft)

| 항목 | 내용 |
|---|---|
| 실험 이름 | E7 Track A Common Deployment Suite 스윕 |
| **Alpha Mining Framework** | 없음 — 재평가 전용 (v1 pool 39개: gplearn_asb 38 + AlphaAgent_asb 1) |
| **평가 프레임워크** | `AlphaSearchBench` + protocol **ASB-P1.0-draft** — Track A 8구성(2 combiner × 2 rule × 2 cost, 동일 simple 엔진) + Track B anchor(qlib), family별 프로파일 집계 |
| 실험 세팅 | split train 2010–19/valid 2020/test 2021–24, 39 pool × 9 arm = 351 조합, `deployment_profile.py` 집계 |
| 목적 | backtest_design.md의 프로파일 보고(median/IQR/PDR/worst/gross→net) 첫 실증 — 단일 프로토콜 점수 대신 배치 강건성 측정 |
| 소모 시간 | 5h 33m (job 889221, cpu1 16c) |
| 결과 요약 | ① **PDR이 운/강건을 분리**: fbfit_42는 8구성 전부 흑자(PDR 1.0, worst Sharpe +0.66), 그 fixedhof판은 PDR 0.5 — 단일 점수로는 안 보이던 차이. ② **비용 민감도 정량화**: gross→net Sharpe 하락폭 ictstat 2.50 / strict 2.03 / off 1.61 vs fbfit 0.17. ③ Anchor에서 초과AR>0은 여전히 fbfit_42 단독(+17.2%, IR 1.29) — E3 재확인. **전부 development evidence**(v1 pool·소각된 기간). |

## 1–2. Context·판독 규칙
backtest_design.md 개정(GPT 피드백 반영)에 따른 Track A/B 분리·family 집계의
첫 실행. 사전 규칙: family 간 지표 혼합 금지, PDR은 분산 지표 동반 기술
진단으로만.

## 3. 세팅
3-A: 마이닝 없음(입력 pool은 E1~E5 보고서 참조). 3-B: Track A =
{raw_equal, train_signed_equal} × {LSQ 20/20 매일, LSK top50 5일 보유} ×
{0bps, 15bps} — 전부 simple 엔진, `protocol_version: ASB-P1.0-draft` manifest
스탬프. Track B = qlib top50/drop5 롱온리 5/15bps(집계 제외, anchor 전용).
3-C: job 889221, 산출 `out/protocol_sweep/trackA_p10_dev/metrics/
{protocol_sweep_pool,deployment_profiles}.parquet`.

## 4. 결과 (Common-LS 프로파일, 계열 평균)

| 계열 | n | median Sharpe | IQR | **PDR** | worst | **gross→net 하락** |
|---|---|---|---|---|---|---|
| fbfit | 10 | +0.01 | 1.36 | **0.53** | −0.92 | **0.17** |
| fbfitguard | 2 | −0.05 | 1.77 | 0.50 | −1.19 | 0.11 |
| nsguard | 2 | −0.11 | 1.70 | 0.50 | −1.18 | 0.22 |
| netsharpe | 6 | −0.18 | 1.49 | 0.44 | −1.46 | 0.29 |
| ictstat | 2 | −0.53 | 1.65 | **0.00** | −4.25 | **2.50** |
| strict | 10 | −0.56 | 1.31 | 0.11 | −3.60 | 2.03 |
| off | 5 | −0.56 | 1.05 | 0.06 | −2.87 | 1.61 |

개별 사례: fbfit_42 PDR 1.0(8/8 흑자, IQR 0.27) vs fbfit_42_fixedhof PDR 0.5 —
"3-수식 집중 pool의 흑자"가 배치 구성에는 강건하지만 pool 다양화에는 취약함을
프로파일이 그대로 드러냄. combiner 축(raw vs train_signed)의 효과는 |IC|계열
에서 미미(부호가 이미 절댓값 fitness로 정렬됨), 방향 미정의 pool 편입 시 재평가.

## 5–7. 해석·한계·연결
비용-인지 fitness 계열(저회전)과 |IC| 계열(고회전)의 차이가 median보다
**PDR·gross→net 축에서 선명**하다 — 프로파일 보고가 단일 점수보다 정보량이
많음을 실증. 한계: 전부 v1 pool + 소각된 기간 = development evidence
(Vanilla_GP_v2.md §0). n<3 계열은 기술통계만. 연결: v2 공식 실험(새 split)
확정 후 동일 프로파일로 confirmation 평가.
