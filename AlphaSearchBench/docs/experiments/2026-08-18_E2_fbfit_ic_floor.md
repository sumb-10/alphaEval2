# E2 — fb_fitness + IC-floor 가드

| 항목 | 내용 |
|---|---|
| 실험 이름 | E2 fb_fitness + IC-floor |
| **Alpha Mining Framework** | `gplearn_asb` (GP) |
| **평가 프레임워크** | `AlphaSearchBench` v0.1.0 (E4 체인 4-arm 스윕) |
| 실험 세팅 | E1과 동일 + `net_sharpe_min_abs_ic: 0.01`(유일한 축), seed 42 / 평가: E1과 동일 |
| 목적 | fb가 허용하는 저IC 승자(seed 42 승자 \|IC\| 0.006)를 IC 하한이 걸러내면 성과가 개선되는지 |
| 소모 시간 | 마이닝 1 job 3h20m (888254) + E4 체인 공유 |
| 결과 요약 | **개선 실패 — 오히려 흑자 소멸**(A1 Sharpe −1.19, A3 초과AR −8.4%). 가드는 unique의 63%(1,262/1,993)를 차단했고 승자 \|IC\|는 0.011로 올라갔지만 test 수익은 없음. 시사점: fbfit_42의 흑자는 IC를 경유하지 않는 수익이었고(가드가 그 계열을 차단), 그 수익 자체가 E1에서 비재현으로 판명 — 두 실험이 같은 결론("신호 없음")을 서로 다른 경로로 지지. |

## 1–3. Context·규칙·세팅

E3에서 fb 승자의 train \|IC\|가 0.006으로 nsguard의 "IC 없는 Sharpe" 병리와
동형임이 관찰됨 → IC 하한(≥0.01, nsguard와 동일 값)을 fb에 결합해 개선
여부를 검사. 구현: `fitness.py`의 B2 조건을 fb_fitness에도 적용(1줄 확장,
기본 null이라 기존 run 불변) + `configs/experiments/ablation_fbfit_guard.yaml`.
세팅 상세는 manifest(`out/pilot_csi800_fbfitguard_42/manifests/`) 참조.
사전 규칙: 개선 여부는 seed 42의 무가드 대비 A1 Sharpe·A3 초과AR로 비교.

## 4. 결과

| run (seed 42) | A1 Sharpe | A3 초과AR | 승자 \|IC\| | 가드 차단률 |
|---|---|---|---|---|
| fbfit (무가드) | +0.95 | +17.2% | 0.006 | — |
| **fbfitguard** | **−1.19** | **−8.4%** | 0.011 | 63% (1,262/1,993) |

## 5–7. 해석·한계·연결

가드는 설계대로 작동했다(저IC 후보 차단, 승자 IC 상승). 그럼에도 성과가
나빠진 것은 **흑자의 원천이 IC가 아니었기 때문** — 가드가 seed 42의 수익
계열(저IC $amount-분산)을 정확히 차단했다. E1이 그 수익 자체가 seed 행운임을
보였으므로, 두 실험의 합은 일관된다: **cross-sectional IC로도, fb로도, 이
탐색 공간의 GP가 2021–24 test에서 신뢰할 수익 신호를 찾지 못했다**.
한계: 1-seed(기술 기록만). 연결: IC-floor는 net_sharpe 계열의 병리 차단
장치로는 유효(nsguard에서 실증)하나 수익 창출 장치는 아님 — 다음 사이클
fitness 설계 시 "IC 경유 수익"과 "비-IC 수익"을 구분해 다뤄야 한다.
