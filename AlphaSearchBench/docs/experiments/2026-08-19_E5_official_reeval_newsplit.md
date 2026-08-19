# E5 — 새 split 공식 재평가 (valid=2020 오염 제거)

| 항목 | 내용 |
|---|---|
| 실험 이름 | E5 새 split 공식 재평가 |
| **Alpha Mining Framework** | 없음 — **재평가 전용** (입력: `gplearn_asb` 38 run + `AlphaAgent_asb` 1 run의 기존 pool·trajectory) |
| **평가 프레임워크** | `AlphaSearchBench` v0.1.0, protocol ASB-P1.0-draft — 4축 전체(validity/OOS/QD/backtest), allcand 22건 + final_pool-scope 16건 |
| 실험 세팅 | split **train 2010–19 / valid 2020 / test 2021–24** (기존 valid 2017–19는 마이닝 창 내부 = 오염), A1 프로토콜, 산출은 `asb_eval_ref/`(구 split 산출 보존) |
| 목적 | ΔIC·retention 등 OOS 지표를 오염 없는 valid 기준으로 재산출 + 39-run 노트북 체제 정식화 |
| 소모 시간 | 39 job, 개별 2m~7h, 배치 wall ~19h (submitter 체인 888504·재제출 1회 — config 상대경로 실수로 1차 전건 즉시 실패 후 수정) |
| 결과 요약 | ① \|IC\| 계열(off/strict)은 **2020에 실재 OOS 신호**(factor IC 중앙값 0.033~0.035)가 있었고 test(2021–24)에서 절반 이하(0.013~0.017)로 **감쇠** — "신호 부재"가 아니라 "신호 감쇠"로 정정. ② fbfit 계열은 2020에도 신호 없음(−0.003) — seed 42 흑자가 비-IC 행운이라는 E1 판정 강화. ③ 노트북 39-run·§11 전부 통과, evidence class = **development**. |

## 1. Context

기존 평가 split의 valid(2017–19)가 마이닝 창(2010–19) 안에 있어 miner에게
out-of-sample이 아니었다(§6 ΔIC·retention의 해석 오염). backtest_design
§6.1의 분할 정의(train=마이닝 창 / valid=2020 배치 캘리브레이션 / test)로
전 run을 공식 재평가했다.

## 2. 사전 고정 판독 규칙

새 valid는 "마이닝 직후 첫 해"이므로: valid IC가 유의하게 양수이면 "신호는
존재했고 test에서 감쇠", valid IC부터 ~0이면 "애초에 신호 없음"으로 읽는다
(결과 확인 전 고정).

## 3. 실험 세팅

3-A: 마이닝 없음 — 39 run의 세팅은 각 manifest 참조(E1~E3 보고서와 동일 집합).
3-B: `configs/examples/csi800_ref.yaml`(allcand) / `csi800_ref_fp.yaml`
(fixedhof 파생 — trajectory 중복 재계산 방지). combiner=raw_equal,
execution=next_open_oo, 20/20 LS, 15bps·oneway.
3-C: jobs 888506–888523·888840–888877 계열 + aa_expB 889098, 산출
`out/pilot_csi800_*/asb_eval_ref/`, `protocol_version` manifest 스탬프.

## 4. 결과 (family 평균, factor-IC는 pool 내 중앙값의 평균)

| family (HOF) | n | factor IC @valid 2020 | factor IC @test 21–24 | pool IC @test | pool Sharpe |
|---|---|---|---|---|---|
| off (orig) | 5 | **+0.035** | +0.017 | +0.011 | −2.76 |
| strict (orig) | 5 | **+0.033** | +0.013 | +0.013 | −3.76 |
| strict (fixedhof) | 5 | +0.020 | +0.007 | +0.009 | −3.37 |
| hard | 1 | +0.031 | +0.023 | +0.000 | −0.45 |
| ictstat | 1 | +0.014 | +0.006 | +0.006 | −4.36 |
| netsharpe (orig) | 3 | +0.005 | +0.006 | −0.006 | −1.41 |
| fbfit (orig) | 5 | **−0.003** | +0.006 | −0.004 | −0.73 |
| fbfitguard | 1 | −0.005 | +0.009 | −0.010 | −1.19 |

## 5. 해석

* **"신호 부재" → "신호 감쇠"로 서사 정정**: \|IC\| 계열의 valid(2020) factor
  IC 0.033~0.035는 마이닝 창 밖 첫 해의 진짜 OOS 신호다. 이것이 2021–24에
  절반 이하로 줄어드는 것은 참고연구가 보고하는 alpha decay(AlphaAgent Fig 4:
  GP IC 0.022→~0) 곡선과 정합한다. 즉 GP는 "가짜 신호"가 아니라 "**빠르게
  감쇠하는 진짜 신호**"를 캔다 — E3의 수익 결론(비용·감쇠의 중첩으로 test
  수익 전환 실패)은 유지되되 원인 서술이 정밀해졌다.
* **fbfit의 역설 확정**: fb 계열은 2020에도 단면 IC가 없다. 수익(seed 42)은
  IC를 경유하지 않았고 재현되지 않았다(E1·E2와 3중 정합).
* fixedhof pool은 valid IC도 원본보다 낮다(0.033→0.020) — 원본 HOF의
  anti-selection이 우연히 "동일 fitness 꼬리 클러스터"를 뽑으면서 사실상
  단일-수식 복제 pool을 만들었고, 그 단일 수식의 valid IC가 높았던 것.
  다양화는 IC를 희석하지만 그것이 정직한 pool 값이다.

## 6. 한계

development-phase 증거다(ASB-P1.0 §7) — 이 split 정의 자체가 test 관찰 후
확정되었으므로, confirmation은 freeze 후 신규 대상(Alpha101·AlphaGen 등)
평가에서 얻는다. valid가 1년(2020)뿐이라 valid 지표의 표본 분산이 크다.

## 7. 연결

E6(39-run 노트북) 완료. 다음: P-7 Track A 8구성+Anchor 스윕(진행 중)으로
combiner 축(raw vs train_signed) 효과와 family 프로파일(PDR·IQR) 첫 산출.
