# ASB Pilot Evaluation — 기존 pool 4개의 OOS 판정과 validity threshold 결정 재료

**실험일**: 2026-08-14 ·
**도구**: AlphaSearchBench v0.1 (`python -m alphasearchbench evaluate`) ·
**결과 원본**: `AlphaSearchBench/out/pilot/{gp_smoke,random,gp_main,gp_csi800}/`
(7종 parquet + manifest, 재현 가능) ·
**개정**: 2026-08-14 — 6개 지적 감사(`asb_pilot_verification.md`) 반영:
§3.1 소표본 IC 해석 격하, §4 threshold 근거를 train/valid 분포로 교체,
§6 train_sign 한계 해소.

## 1. 목적

1. 마이닝 in-sample |IC|가 컸던 승자 formula들이 **완전히 분리된 test
   구간(2021–2024)에서 예측력을 유지하는가** — 특히 883882/883929 승자의
   "Rsquare sparse-validity 아티팩트" 가설의 out-of-sample 판정
2. Validity Gate의 **research threshold**(coverage/유효종목수) 수치를
   정할 실측 분포 확보

## 2. 설정

| 항목 | 값 |
|---|---|
| split | train 2010–2016 / valid 2017–2019 / **test 2021–2024** (2020 완충) — `configs/examples/csi_example.yaml` |
| universe | 마이닝 universe와 일치 — 883881/882/883 → `all`, 883929 → `csi800`(`csi800_example.yaml`) |
| train_sign | 입력에 signed IC가 없어 **train(2010–2016) 재평가로 복원** (`train_sign_restored=True`) |
| pool weights | 미제공 → equal(1/n), manifest에 `weights_source: equal_default` 기록 |
| backtest | simple, **next_open_oo**, 20/20, 비용 15bp(oneway) |
| validity | `mode: report_only` — hard invalid만 제외, threshold는 이 pilot으로 결정 |

평가한 pool (마이닝 산출 CSV 그대로):

| run | method | 마이닝 설정 | 마이닝 best \|IC\| (in-sample 2010–2019) |
|---|---|---|---|
| 883881 | gp_smoke | pop=50 gens=2, all | 0.082 |
| 883883 | random | pop=1000 gens=1, all | 0.146 |
| 883882 | gp_main | pop=1000 gens=5, all | **0.565** |
| 883929 | gp_csi800 | pop=1000 gens=5, csi800 | 0.075 |

## 3. 핵심 결과 — 아티팩트 가설 **입증**

### 3.1 gp_main (883882) — 승자 전원 아티팩트 판정

| formula (요약) | validity | coverage | test IC (oriented) |
|---|---|---|---|
| `WMA(Rsquare(Div(Div(Mul(WMA(Slope…)…EMA($volume,30)…)` (train \|IC\| **0.565**) | **hard invalid — `no_correlatable_day`** | 0.01% | — (계산 불가) |
| `WMA(Rsquare(…Power($volume,$open)…))` ×3계열 (train signed +0.469) | 통과(report_only) | **0.00%** (median 일별 유효종목 **0**, IC 계산 가능일 969일 중 **44–47일**) | −0.35 ~ −0.39 (해석 불가 소표본 — 아래 주의) |

- in-sample 0.565의 절대 승자는 test에서 **상관 계산 가능한 날이 하루도
  없어** hard invalid로 걸러졌다. (검증 보고서 V2에서 확인: 이 fitness는
  마이닝 창에서도 **유효 셀 57개, IC 관측 23일, 0.565217 = 13/23** —
  2종목 상관 ±1이 +18일/−5일이라는 뜻의 산술이었다.)
- 나머지 승자들의 test IC −0.35~−0.39는 **44–47일 전부 n<5(대부분
  종목 2~3개, 그중 39일은 문자 그대로 \|IC\|=1)인 관측의 평균**이다
  (`asb_pilot_verification.md` V4). 즉 "유의미한 역방향 예측력"이 아니라
  **"신호 없음 + validity 실패"**로 읽어야 한다 — 아티팩트 판정은
  불변이며 오히려 강화된다.
- backtest: Sharpe −1.23, MDD 69%. pool IC −0.013.
- **결론: 5,000회 평가의 GP 본실험이 남긴 것은 전부 validity 루프홀
  (Rsquare std≈0 NaN 마스킹 + Power 오버플로)의 산물이다.**

### 3.2 gp_csi800 (883929) — 동일 병리, 완화판

- 승자 계열(train 0.075–0.101): 일별 **median 유효종목 2개**, coverage
  0.8%, IC 관측 520일. test IC +0.004~+0.023 — 크기 붕괴(그나마 관측
  표본이 무의미한 수준). backtest Sharpe −0.26~−0.93.

### 3.3 random (883883) — 예상대로 일반화 없음

- 10/10 validity 통과(1개는 coverage 2.7%의 Rsquare 계열). train signed
  +0.02~+0.10 → **test IC −0.010~+0.006** (전멸). pool IC −0.004.
- 이 대조군이 중요한 이유: **아티팩트가 아니어도 in-sample 상위 선별
  자체가 OOS에서 살아남지 않는다** — GP의 in-sample 우위(0.565 vs 0.146)는
  전부 selection/루프홀 효과.

### 3.4 유일한 생존자 — `Log($volume)` (gp_smoke)

| | train signed | test IC | test RankIC | test ICIR | backtest |
|---|---|---|---|---|---|
| `Log($volume)` (sign −1: 저거래대금 롱) | −0.047 | **+0.0216** | **+0.0564** | +0.249 | **Sharpe +0.85, CAGR +21.3%, MDD 7.0%** |

4개 pool 40행 중 test에서 의미 있게 생존한 유일한 factor. 잘 알려진
저유동성/소형주 효과의 사소한 재발견이지만, **파이프라인이 진짜 신호와
아티팩트를 정확히 구분함**을 보여주는 대조 사례다.
(random의 `Div($close,$volume)`도 같은 계열로 Sharpe +0.56.)

## 4. Validity threshold 결정 재료 (핵심 산출)

> **[2026-08-14 수정]** 초판은 이 절의 근거로 test(2021–2024) 분포를
> 사용해 leakage 소지가 있었다(검증 보고서 지적 5). 아래 수치는
> **train(2010–2016)·valid(2017–2019) 분포만으로 재도출**한 것이다
> (`AlphaSearchBench/scripts/derive_thresholds_no_test.py`,
> `out/verification/validity_stats_train_valid.csv`). 이봉 구조와
> 권장값은 초판과 동일하게 유지된다.

train+valid의 coverage 분포는 **완전한 이봉(bimodal)** 이다:

| 그룹 (train+valid) | mean_daily_coverage | median_daily_n_valid |
|---|---|---|
| 정상 formula (n=15) | **0.477 ~ 0.997** | 1,176 ~ 3,535 |
| 아티팩트 (n=7: gp_main 4 + csi800 3) | **0.000 ~ 0.011** | 0 ~ 14 |
| 경계 (random의 Rsquare 1건) | train **0.038** / valid **0.057** | 83 / 202 |

**권장 threshold** (아티팩트 최대 0.011 ≪ 0.05 ≪ 정상 최소 0.477):

```yaml
validity:
  mode: strict
  min_mean_daily_coverage_ratio: 0.05
  min_median_daily_n_valid: 30
  min_valid_day_ratio: 0.90
```

- 이 세 값은 train/valid 통계만으로 **아티팩트 7건 전부 제외 + 정상
  15건 전부 유지**를 재현한다.
- **경계 1건의 단서**: coverage가 train 0.038 / valid 0.057로 0.05를
  걸친다. gate 통계의 기준 split을 **"train과 valid 모두 통과"**(권장)로
  명시하면 제외되고, threshold를 gap 중앙(≈0.15)으로 올려도 안정
  제외된다 — 선택은 연구자 결정 사항이며 값은 config로만 주입된다.
- 이 pilot에서 test 분포를 이미 관찰했으므로 2021–2024는 threshold
  선택에 노출된 구간이다. 최종 판정은 새 seed set(제안 job 2)의 test
  1회 평가로 확인할 것을 권장한다.

## 5. 부수 관찰

- **DE의 0-채움 왜곡 실증**: gp_main에서 `AlphaEval_DE_legacy 0.277` vs
  `DE_common_valid 0.077 (n_common_cells 163)` — 사실상 동일한 신호
  3개인데 legacy가 0-채움 때문에 다양성을 부풀린다. random에서는
  common_cell_ratio 2.7%(최악 factor 지배) — blueprint v2의 경고 그대로.
- **QD coverage는 예상대로(final pool n≤10) 무의미한 수준**(0.000~0.013)
  — pool-level 비교는 DE·NN 중심으로, coverage는 seed 풀링 후에.
- **descriptor drift**: gp_main은 valid→test에서 descriptor 자체가 NaN화
  (관측 부족) — drift 이전에 validity가 걸러야 할 대상임을 재확인.
- backtest 전반이 음수인 것은 2021–2024 CN 약세장 + equal-weight 결합 +
  아티팩트 포함 pool임을 감안해야 함 — 이 pilot의 목적은 절대 성과가
  아니라 판별력 검증.

## 6. 한계

- ~~train_sign 복원은 train 2010–2016 기준(마이닝 창 2010–2019의
  부분집합)~~ → **[해소]** 마이닝 창(2010–2019) 기준으로 전수 재복원한
  결과 **sign flip 0건, oriented test IC 완전 동일**
  (`asb_pilot_verification.md` V1, `out/pilot_signfix/`). 향후 실험은
  sign 복원 창=마이닝 창 규칙을 config로 강제.
- pool 결합은 equal weights (train 학습 weights 미보존) — pool 지표는
  참고용.
- gp_smoke/random pool은 소규모라 분포 추정의 표본이 작다 — threshold는
  seed 스윕(제안 job 2) 후 재확인 권장.
- **evaluator 경계조건**: overflow가 중간 노드에서 발생하는 병리 formula
  4개에서 ASB와 qlib native의 신호가 어긋난다(정상 17개는 비트일치,
  fitness 21/21 재현). 전부 validity gate가 걸러내는 대상이라 판정에는
  영향 없음 — 상세는 `asb_pilot_verification.md` V2와
  `AlphaSearchBench/docs/IMPLEMENTATION_NOTES.md` 구조적 제약 #3.

## 7. 결론과 다음 단계

1. **판정**: gplearn |IC| 마이닝의 고IC 승자는 전부 validity 루프홀의
   산물이며 OOS 예측력이 없거나 음수다. GP vs Random의 in-sample 격차는
   진짜 알파 발견이 아니었다.
2. **처방**: 위 §4 threshold를 `mode: strict`로 채택 → 이후 마이닝
   실험(제안 job 4·5: mutation/tournament 조정, `$factor` 제외)은 이
   게이트 아래에서 비교.
3. **후속**: seed 스윕(job 2)·csi800 random(job 3)으로 표본을 늘려
   threshold 안정성 확인 → search-QD(trajectory 로깅)로 루프홀 학습이
   세대 중 언제 시작되는지 추적.
