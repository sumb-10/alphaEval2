# Clean Vanilla GP v2 — 수정 명세 (Modification Specification)

상태: **Phase B 구현·검증 완료 (2026-08-19)** · profile: `vanilla_v2-draft`
검증 실측: Slurm 889597 — 전체 스위트 **76 passed**(legacy 무회귀 + v2 신규
regression 7본) + v2 smoke green(vendored HOF qlib 재조회 0행) + manifest
계약 검사 통과. 잔여 freeze 조건은 ①(L/D, C-2)뿐.
관련: `GP_asb_design.md`(v1 실측 설계), `GP_asb_design_v2.md`(v2 설계),
`search_spaces/gp_native_v1.md`(문법 기록), `backtest_design.md` §7(evidence 프로토콜)

---

## 0. 공식 선언

1. **GP v1 및 기존 기간의 모든 결과는 legacy/development evidence다.**
   test 2021–2024를 포함한 기존 전 기간은 설계 결정(프로토콜 개편, canonical
   fitness 선택 등)에 사용되었으므로 development information으로 격하한다.
   기존 결과는 폐기가 아니라 **설계 선택의 근거 기록**으로 보존한다.
2. **Clean GP v2 + 새 temporal split이 새로운 공식 실험의 시작점이다.**
   canonical fitness(fb_fitness)의 채택 근거가 기존 test 성과이므로, v2의
   공식 결과는 새 split의 동결된 OOS 구간에서만 생산한다: **2024–2026 전체를
   OOS 평가 구간으로 사용하고, 2025-01-21 이후의 구성상 미접촉 구간을 별도
   confirmation subset으로 보고한다**(§6 — 전체 test를 '완전 untouched
   confirmation set'으로 표현하지 않는다). `backtest_design.md` §7
   development/confirmation 프로토콜의 첫 적용.
3. **ASB는 이번 작업에서 제외한다.** 본 명세의 범위는 GP v2의 mining
   correctness와 설정 확정까지이며, `alphasearchbench/`는 무수정이다.
   v2 산출물의 ASB 평가 통합·최종 test 평가는 **Phase D**(ASB integration
   & final evaluation)로 분리한다 — Phase C는 GP v2 spec freeze + 공식
   mining까지만.
4. **v2 spec freeze 조건**: ① complexity bound(L/D) 확정(§8) ② 새 temporal
   split 확정(§6). 두 조건 충족 전까지 manifest profile은
   `vanilla_v2-draft`이며, draft 상태의 모든 run은 correctness 검증용이다.

## 1. 배경과 원칙

v1(`gplearn_asb` 현행)은 "AlphaEval 원본의 충실 재현 + 결함의 계측"이라는
목적을 완수했다: 3-arm 비교, HOF anti-selection 정량화(pool = 최고 1 +
꼬리 9), $close fallback 발동률 실측(off 5-seed 중 2), point mutation의
문법 이탈 실물 확인. 그 과정에서 원본 재현용 축(mode·fallback·버그 보존)과
연구용 축(fitness 확장·게이트)이 한 config 네임스페이스에 섞였다.

v2의 원칙: **legacy reproduction과 clean baseline의 분리.**
* legacy = 현행 코드·config·산출물 전부, **동결**(이동·수정 없음).
* v2 = 새 config 네임스페이스(`configs/v2/`) + 새 run ID 체계
  (`v2_<market>_<fitness>_<seed>`) + 결함 부재 + 최소 public config.
* 정상 gplearn mechanics(tournament·crossover·mutation 확률·전량 교체·
  no elitism·중복 허용·train-only 탐색·worst-fitness 도태)는 그대로 유지 —
  upstream gplearn 표준과 일치함이 확인된 부분이다.

## 2. 항목별 분류표

분류: **유지** / **수정** / **legacy 이동**(v2 경로에서 도달 불가, 코드는
테스트용 잔존) / **내부 고정**(public 키 제거, 상수화) / **연기**.

### 2.1 유지 (변경 없음)

| 항목 | 근거 | 파일 |
|---|---|---|
| tournament(20, 복원추출), p_crossover 0.9, subtree/hoist/point mutation 각 0.01, p_point_replace 0.05, half-and-half, init_depth [1,4] | upstream gplearn 기본값과 동일 — 정석 | `vendored_gplearn/` (무수정) |
| 세대 전량 교체, elitism 없음 | vanilla mechanics. trajectory archive가 우수 개체 보존을 대신함 | `genetic.py` |
| 중복 후보: 시도 예산에 포함, 캐시로 재계산 방지, 최종 pool에서만 exact dedup | 중복 수렴 자체가 탐색 붕괴의 신호(연구 데이터) — 인위적 exploration 주입 금지 | `cache.py`, `hof.py` |
| invalid 후보를 삭제·재생성하지 않고 worst fitness로 도태 | population 동역학 보존 + 결정성 | `fitness.py` |
| train-only 탐색(validation을 fitness에 사용하지 않음) | validation은 벤치마크 hyperparameter 결정용으로만(§6, C-1) | — |
| trajectory 전 후보 기록, 개체별 seed RNG, memo 캐시 | 재현성·search-QD의 기반 | `genetic.py`, `trajectory.py` |
| 정적 사전검증(static_check: 상수식 조기 차단, flag 기록) | static ⊂ hard 증명으로 행동 불변, 비용만 절감 | `static_check.py` |

### 2.2 수정 (v2 신규 구현)

| 항목 | 현행(v1) | v2 | 구현 변경 | 테스트 영향 |
|---|---|---|---|---|
| **point mutation** | vendored `_program.py:708-755` — terminal 교체 시 정수 인덱스를 그대로 대입(`$close→3`, window에 0~9 유입) | **typed mutation**: feature→다른 feature 이름, window 정수→`window_lengths` 내 다른 값, 연산자→동일 arity군(현행 유지) | 신규 `gplearn_asb/mutation.py::typed_point_mutation(program, random_state, p_point_replace)`. `genetic.py`의 phase-A가 profile에 따라 vendored/typed 디스패치(vendored 무수정) | 신규 `tests/unit/test_typed_mutation.py`. legacy 재현 테스트(883881)는 vendored 경로로 계속 통과 |
| **HOF / pool 선택** | vendored `fit()` 내부: NaN corrcoef → anti-selection. `hof_mode: fixed`는 사후 재선택이지만 vendored HOF 블록(qlib 재조회 50회 + $close fallback)은 여전히 실행됨 | fixed HOF(`hof.select_pool_fixed`)가 **pool의 유일한 source**. vendored HOF 블록은 v2에서 `_Program.execute` 런타임 더미 패치로 무력화(qlib 재조회 0회) | `cli.py` v2 분기에서 `_Program.execute` 패치(cli 내부, vendored 파일 무수정). `gp.hof_mode` 키는 v2 스키마에서 금지 | **HOF 격리 regression 2본**(§9-iv): ⓐ sentinel — vendored `_best_programs`에 표식 심고 pool 미혼입 확인, ⓑ 패치 무해성 — 동일 seed에서 패치 on/off의 trajectory·세대통계·최종 population 완전 일치 대조 |
| **admissibility (단일 규칙)** | `constraint.mode: off/hard/strict` 3분기 | 모드 개념 제거. 항상: 문법 invalid ∨ 평가 실패 ∨ all_nonfinite ∨ zero IC obs ∨ threshold 위반 → **worst fitness** (v1 strict 의미론과 동치) | `cli.py` v2 분기가 내부적으로 strict 경로 호출. `constraint.*` 키가 v2 config에 존재하면 에러 | 기존 mode 교차 테스트는 legacy 경로로 유지(무수정) |
| **complexity bound** | `gp.max_program_length`(기본 null, penalty 모드 전용; 깊이 bound 없음) | v2 config에 `gp.max_program_length`(L)·`gp.max_program_depth`(D) **둘 다** 노출, **값은 '결정 대기'**(freeze 조건 ①). 초과 시 worst (`static_invalid:too_long`/`too_deep`). parsimony는 0 내부 고정 | 값 결정은 C-2(교차 방법 문법 대조 후). 문서에 결정 대기 명시 | — |
| **label tail exclusion** | 창 마지막 날 label이 우측 버퍼(경계 밖 1일)를 사용 — train-only 계약의 1-day leakage | train 마지막 `horizon` 거래일을 fitness label에서 제외 (§6 caveat 4) | `evaluator.apply_label_tail_exclusion`(모듈 함수) + v2 cli가 내부 키 `label.tail_exclusion=True` 주입. legacy 기본 off — 동결 불변. 캐시 네임스페이스 분리(조건부 ctx 키). manifest `label_tail_exclusion` 스탬프 | 신규 `tests/unit/test_label_tail_exclusion.py` + regression manifest 계약 |

### 2.3 Legacy 이동 (v2 경로에서 도달 불가)

| 항목 | 코드 처리 | v2에서의 상태 | 접근 경로 |
|---|---|---|---|
| `$close` silent fallback (off 모드의 `fallback_used`) | `fitness.apply_constraint` off 분기 **잔존**(테스트 15곳 참조) | mode 개념이 없어 도달 불가 | legacy config + 재현 테스트만 |
| `constraint.mode: off/hard_penalty/strict_penalty` | cli의 legacy 경로 잔존 | v2 config에 키 존재 시 **SystemExit** | `configs/`(기존)·`configs/experiments/`(기존) |
| original HOF (`hof_mode: original`) | cli legacy 경로 잔존 | 금지 키 | 883881 재현·3-arm 재현 테스트 |
| buggy point mutation | vendored 무수정이므로 자동 잔존 | typed로 대체 | legacy 경로의 디스패치 |
| metric 의존 early stopping | vendored `fit()` 내장 | v2는 `stopping_criteria = math.inf` 주입으로 무력화(§2.4) | legacy config의 `gp.stopping_criteria` |

### 2.4 내부 고정 (public 키 제거 → 상수)

| v1 public 키 | v2 내부 상수 | 근거 |
|---|---|---|
| `gp.stopping_criteria` | `math.inf` (early stop 금지) | budget 무결성 — 조기 종료는 방법 간 예산을 어긋나게 함. IC=inf 불가 가드 기확보로 안전 |
| `gp.metric` | `'pearson'` | vendored 배관(argmax 방향·parsimony 부호)일 뿐 점수 아님 |
| `gp.max_samples` | `1.0` | OOB 경로가 원본에서 이미 죽어 있음 |
| `gp.parsimony_coefficient` | `0.0` | hard bound(L/D) 채택 시 이중 패널티 금지 |
| `constraint.worst_fitness` | metric별 맵: `abs_ic/ic_tstat → −1.0`, `net_sharpe/fb_fitness → −1e6` | 순수 구현 세부. `check_sentinel_separation` 내부 유지 |
| `gp.static_gate` | 항상 ON | admissibility 상시이므로 분기 불필요(static ⊂ hard) |
| `gp.hall_of_fame` | 상수 `50` — 단 vendored 제약(HOF ≤ population)상 `min(50, population)`으로 클램프. canonical 조건(population ≥ 250)에서는 항상 50, smoke급 소형 config에서만 축소 | pool 선택의 중간 폭. 결과 영향은 fixed HOF의 dedup 폭뿐 |
| `gp.tournament_size`, `p_*`, `init_*` | upstream 기본값 상수(20 / 0.9 / 0.01×3 / 0.05 / half-and-half / [1,4]) | canonical GP profile — §3 상수표 |

### 2.5 유지하되 계층화 / 명시-고정

| 항목 | 처리 |
|---|---|
| **fitness 4종** | 코드 전부 유지. **canonical v2 = `fb_fitness`** (net_sharpe×√(\|AnnRet\|/연환산 편도회전)). `abs_ic`/`ic_tstat`/`net_sharpe`(+B2 가드 키)는 `configs/v2/ablations/` 전용. ※ fb 채택의 공식 효력은 새 split 확정과 동반(§0-2) |
| **fb의 비용 파라미터** | v2 config에 **명시-고정**: `fitness.transaction_cost_rate: 0.0015`, `fitness.long_short_quantile: 0.2` + "benchmark spec — 튜닝 금지" 주석. fitness 정의의 일부라 숨기면 불투명해짐 |
| **fb pathological 가드** | ① 내부 상수 `fb_min_annual_turnover = 0.01`: fb=ns×√(\|AnnRet\|/연회전)의 분모 폭발 차단. **연구 threshold가 아니라 구조 하한 아래의 수치 가드** — 건립비용 의미론상 포지션을 한 번이라도 보유하면 연회전 ≥ 126/T (T=탐색창 거래일; 10y창 0.052, 50y창에서야 0.01) → 현행 엔진에서 **도달 불가**, development 실측 8,431 unique 후보 중 구속 0건(valid 최소 연회전 6.18). legacy 경로는 기본 0.0으로 의미론 불변. ② config 명시-고정 `fitness.net_sharpe_min_traded_days: 252`: **포지션 보유일**(`np.abs(W).sum(axis=1)>0` — 매매 발생일 아님) 기준 Sharpe/AnnRet **추정 최소 표본**(연환산 지표의 최소 1거래년). 저회전 퇴화 가드가 아님(역할 분리) — development 실측 구속 0건(valid 최소 2,223일/2,431일 창), 사전등록 성격의 하한. ①은 public tuning parameter가 아닌 **v2 내부 상수(invariant guard)**로 유지 — 두 값 모두 성격 구분 검토 후 유지 확정(2026-08-19) |
| **validity thresholds** | v2 config에 **명시-고정**: `min_mean_daily_coverage_ratio: 0.05`, `min_median_daily_n_valid: 30`, `min_valid_day_ratio: 0.90` + 유도 출처 주석(v1 파일럿 검증 V5 재도출 — artifact coverage ≤0.011 vs 정상 ≥0.477 gap의 하단). 자유 튜닝 옵션이 아니라 고정 benchmark specification |
| **generations** | public 키 제거 → **`budget.candidates`에서 파생**: `generations = candidates // population_size`, 나머지 ≠ 0이면 명시적 에러. 예산이 최상위 개념 |

### 2.6 연기

| 항목 | 시점 | 지금 하는 것 |
|---|---|---|
| search space 외부화(`alpha_space_v1`) | Controlled Benchmark(L3) 단계 | 각 방법의 문법을 `search_spaces/*_native_v1.md`로 기록·버전링. 공통 spec은 **mining method와 evaluator 모두로부터 독립**된 명세로 설계 예정 |
| `alphacore` 분리(FormulaEngine·labels·universe의 공용 라이브러리화) | 장기 | §7에 경계 문서화. 현행 miner→`alphasearchbench.data` import는 **데이터 계층 공유이며 평가 의존이 아님**(ASB의 OOS/QD/backtest 지표는 GP selection에 불개입). parity regression이 경계 계약 |
| L/D(complexity bound) 값 | C-2 (문법 대조 후) | 키만 노출, null |

## 3. v2 내부 canonical profile (상수표)

```
init_method            = half and half
init_depth             = (1, 4)
tournament_size        = 20
p_crossover            = 0.90
p_subtree_mutation     = 0.01
p_hoist_mutation       = 0.01
p_point_mutation       = 0.01   (typed)
p_point_replace        = 0.05
reproduction           = 0.07   (파생)
parsimony_coefficient  = 0.0
max_samples            = 1.0
metric                 = pearson (배관용)
stopping_criteria      = +inf   (early stop 없음)
hall_of_fame           = min(50, population)  (canonical 조건에선 50)
fitness (canonical)    = fb_fitness
fb_min_annual_turnover = 0.01   (구조 하한 126/T 아래의 수치 가드 — §2.5)
worst_fitness          = {abs_ic,ic_tstat: −1.0 | net_sharpe,fb: −1e6}
admissibility          = hard invalid ∨ threshold 위반 → worst (상시)
static gate            = 상시 ON
HOF                    = hof.select_pool_fixed (유일 경로)
point mutation         = typed (mutation.py)
duplicate 정책          = attempt 포함·캐시·pool만 dedup
label tail exclusion   = horizon일 (train-only 계약 — §6 caveat 4)
```

이 상수들은 manifest에 `gp_profile: vanilla_v2-draft` + 전체 echo로
스탬프된다(실험 보고서 3-A 자동표 호환).

## 4. v2 public config 스키마 (전문)

```yaml
# configs/v2/vanilla_baseline.yaml — Clean Vanilla GP v2 (draft)
profile: vanilla_v2-draft      # freeze(C-3) 전 유일한 실행 가능 표기.
                               # 'vanilla_v2'는 cli가 거부(SystemExit) — 승격은 C-3에서만.

market: csi800                 # universe
search:                        # 마이닝 창 — C-0 확정(§6)
  start_date: "2015-01-01"
  end_date: "2021-12-31"
label:
  horizon: 1

budget:
  candidates: 5000             # 최상위 예산 개념. generations = candidates // population
gp:
  population_size: 1000
  max_program_length: null     # [결정 대기 — freeze 조건 ①] hard bound (L)
  max_program_depth: null      # [결정 대기 — freeze 조건 ①] hard bound (D)
pool:
  size: 10                     # 최종 alpha pool 크기 (구 n_components)

# ---- benchmark specification (고정 — 튜닝 금지) ----
fitness:
  metric: fb_fitness           # canonical. ablation은 configs/v2/ablations/
  transaction_cost_rate: 0.0015   # fb 정의의 일부 (v1 실측·ASB 규약과 동일)
  long_short_quantile: 0.2
  net_sharpe_min_traded_days: 252 # Sharpe 추정 최소 표본(포지션 보유일) — §2.5 가드 ②
validity:                      # 유도 출처: v1 파일럿 V5 재도출 (artifact gap 하단)
  min_mean_daily_coverage_ratio: 0.05
  min_median_daily_n_valid: 30
  min_valid_day_ratio: 0.90

seed: 42
run_id: null                   # null → v2_<market>_<fitness>_<seed>
output:
  root: null
```

**스키마 규칙**: 위 화이트리스트 외 키(특히 `constraint.*`, `gp.hof_mode`,
`gp.stopping_criteria`, `gp.fitness_metric`, `gp.generations`)가 v2 config에
존재하면 **명시적 에러**. `dataset.*` 블록은 `configs/default.yaml`에서
상속(경로류만).

## 5. Legacy 계층 — 동결 원칙

* 기존 config(`configs/default.yaml`, `configs/smoke*.yaml`,
  `configs/experiments/*`)·산출물(`out/pilot_*`)·테스트 경로는 **일체
  이동·수정하지 않는다.** 과거 report·manifest가 경로를 참조하므로 재현성
  보호가 우선이다.
* 신설 `configs/LEGACY_INDEX.md`: (파일 → 용도 → 재현 대상 run/보고서/테스트)
  표 + "동결 선언, 신규 실험에 사용 금지" 문구.
* `configs/default.yaml` 상단에 헤더 주석 1줄 추가(값 무변경): legacy 기본값
  선언 + v2는 `configs/v2/` 참조.
* legacy 접근 = ① 기존 config 파일로 `cli mine` 실행(현행과 동일 동작)
  ② regression 테스트. 새 문서·실험에서 legacy 경로 사용 시 명시 의무.

## 6. 새 temporal split — **확정 (2026-08-19, 사용자 결정 → freeze 조건 ② 충족)**

| 구간 | 기간 | 용도 |
|---|---|---|
| **Train / Search** | 2015-01-01 ~ 2021-12-31 | GP candidate fitness의 유일한 데이터. 2015 급락·2016 서킷브레이커·2018 조정·2020 COVID·2021 회복 포함, 기존 10y 창 대비 계산량 ~30% 절감 |
| **Validation** | 2022-01-01 ~ 2023-12-31 | **GP 설정 결정 전용**(C-1 budget 배분, C-2 L/D 등). 개별 candidate fitness에 절대 불개입. train과 regime이 다름(부동산 위기·제로코로나 종료) |
| **Test** | 2024-01-21 ~ 2026-06-30 | **동결** — freeze(C-3) 후 1회 평가. 약 2.4년(~590거래일) |

**test 오염 구조 (정직 기재)**: test 전반부 2024-01-21~2025-01-20은 현행
번들에 존재하며 v1 development 과정(old test 2021–24)에서 관측된 기간과
겹치는 **부분 오염** 구간이다. 사용자가 test 통계력 확보를 위해 명시적으로
감수함(2026-08-19). 후반부 2025-01-21~2026-06-30은 번들(2025-01-20 종료)에
존재한 적 없는 **구성상 미접촉** 구간 — 어떤 development 실험도 물리적으로
계산할 수 없었다.

**사전 등록 판독 규칙 (구간 명명 확정, 2026-08-19)**:
* **Primary Full OOS** = 2024-01-21 ~ 2026-06-30 (주 평가 구간 — 표본 확보)
* **Strict Untouched Subset** = 2025-01-21 ~ 2026-06-30 (구성상 미접촉 —
  confirmation subset, 반드시 병기하여 부분 오염 robustness 확인)
전체 test를 '완전 untouched confirmation set'으로 표현하지 않는다.
연환산 지표는 CI 병기, 이진 pass/fail 지양(~590거래일의 Sharpe 표준오차
반영).

**caveat 대장 (evidence ledger)**:
1. validation 2022–23은 v1 old test(2021–24)의 부분집합 — fb_fitness
   canonical 채택 근거와 비독립. **validation 수치는 일반화 증거로 인용
   금지**(설정 결정 전용).
2. test 전반부 부분 오염 — 위 오염 구조 참조.
3. **번들 갱신(→2026-06-30+)은 test 평가의 선행 게이트**. train/validation은
   전부 현행 번들(≤2025-01-20) 안이므로 **C-1·C-2는 번들 갱신 없이 진행
   가능**. 갱신 후 구간 겹침 parity check(동일 수식·기간 신호 대조) +
   manifest 번들 버전 스탬프 필수 — 과거 구간의 조용한 수정은 legacy 재현성
   선언을 깨뜨린다.
4. label k=1의 경계 누출(train 마지막 날 label이 validation 첫 거래일
   수익률 사용) — **v2에서 즉시 해결(2026-08-19 결정)**: train의 마지막
   `horizon` 거래일을 fitness label에서 제외(**label tail exclusion**).
   이는 purge/embargo 연구(P-4)가 아니라 train-only 계약을 정확히 지키는
   기본 처리다. **구현 완료**: `evaluator.apply_label_tail_exclusion` —
   v2 경로 전용(legacy 기본 off — 동결 불변), manifest `label_tail_exclusion`
   스탬프, unit + regression 계약으로 고정. 참고: validation(~2023-12-31)과
   test(2024-01-21~) 사이에는 3주의 자연 gap이 있어 그 경계는 이미 embargo가
   확보돼 있다.

**잔여 freeze 조건은 ①(L/D, C-2)뿐**이다. 이 split 확정 이후에도 draft
run의 성과 수치는 freeze 전까지 공식 결과가 아니다.

## 7. GP↔ASB 경계 (문서화)

miner가 import하는 ASB 모듈 전수: `alphasearchbench.data.qlib_provider`
(FormulaEngine·parse_expression), `data.universe`(build_universe_mask),
`data.qlib_bootstrap`, `validity.metrics`(compute_validity_stats),
`inputs.trajectory`(TrajectoryWriter), `outputs.writer`(OutputWriter).
전부 **데이터·직렬화 계층**이며, ASB의 평가 정책(OOS/QD/backtest 지표,
게이트 판정, split 정의)은 GP selection에 들어가지 않는다. 따라서 이 공유는
mining leakage가 아니다. 다만 패키지 의존 방향(miner→ASB)은 남으므로
장기적으로 `alphacore` 공용 계층으로 분리한다(연기). 경계 계약 = 두 엔진의
formula semantics parity regression(883881 재현 + phase10 fallback 테스트).

## 8. 마이그레이션·검증 계획

Phase B 구현(계획 파일 참조: mutation.py, cli v2 분기, configs/v2 4~5본,
LEGACY_INDEX, 테스트 5본) 후:

1. 기존 스위트 **무수정 전부 green** (gplearn 45 + ASB 90+) — legacy 동결 증명.
2. 883881 재현 테스트 통과 유지 — v2 도입이 legacy 불변임의 증거.
3. v2 신규 테스트: typed mutation / 스키마 검증(금지 키·나머지 에러) /
   결정성 fixture(seed 42 미니 run formula 목록 동결 — v2의 883881 대체물) /
   HOF 격리 2본(sentinel·패치 무해성) / smoke(pool unique=size,
   "executing:" 로그 0행).
4. manifest 검사: `gp_profile: vanilla_v2-draft`, canonical 상수 echo,
   generations 파생값.
5. **Phase C 순서 (2026-08-19 개정 확정)**: C-0(split — 완료, §6) →
   **C-2a.1(구조 파일럿 screening: 3 arms × s0)** →
   **C-2a.2(tail confirmation: 250×20 × s1,s2)** →
   **C-2b(L/D 확정 — 사용자 게이트)** → **C-1(budget 배분 검증)** →
   C-3(freeze). L/D가 탐색공간·중복률·crossover·수렴속도를 바꾸므로
   budget 배분은 최종 L/D 조건 아래에서 골라야 하고(순서 역전 금지),
   L/D 자체도 세대수 증가에 따른 bloat tail을 실측(C-2a)한 뒤 확정한다.
   **Phase C 경계**: Phase C에서는 GP 내부 mining/validation semantics만
   사용하여 specification을 확정한다. shared data/utility 계층
   (FormulaEngine, daily_zscore 등)의 재사용은 허용하되 **ASB evaluation
   policy는 사용하지 않는다**. Phase D에서 freeze된 GP 산출물을 ASB가
   독립 평가한다.
6. **C-1 사전 등록 (2026-08-19 개정 확정)**: 5,000 후보 고정,
   {1000×5, 500×10, 250×20} × seeds **{0, 1, 2}**(42 제외 — v1 development
   evidence 중복 회피; 세 arm 동일 seed set = paired 비교).
   **평가 = GP-side validation scorer**(`validation_scorer.py`, ASB
   evaluation policy 불참 — 위 5의 Phase C 경계): train pool을
   validation(2022–23)에서 동일 GP semantics로 점수화하는 내부 도구.
   **primary = validation pool-level fb** — canonical candidate fitness와
   동일한 risk/return/turnover functional form(net_sharpe×√(|AnnRet|/
   연회전))을 적용하되 **평가 객체는 개별 factor가 아니라 GP의 최종
   산출물인 alpha pool**이다. budget allocation은 최종 pool의 validation
   utility 기준으로 결정한다. **secondary = validation pool net Sharpe**
   (병기 전용 — primary 판정 번복에 사용 금지). 탐색 진단은 참고 전용.
   **판정**: arm별 3-seed median → provisional winner가 **다른 각 arm에
   대해** paired 3 seeds 중 ≥2 우세여야 채택; 실패 시 inconclusive →
   pre-specified reference allocation **1000×5** 유지. **orientation
   계약**: sign은 train 확정값 고정(validation 재추정 금지). 실패 규약·
   integrity gate·상세 절차는 `docs/experiments/2026-08-19_C1_runbook_draft.md`
   (사전 동결본)를 규범으로 한다. validation 수치는 설정 결정 전용 —
   일반화 증거로 인용 금지(§6 caveat 1).
7. freeze(C-3): C-2·C-1 완료 시 `vanilla_v2`로 승격, 본 문서와
   GP_asb_design_v2.md 최종화, 공식 v2 mining(seed sweep) 개시.
   **공식 mining 기간 (2026-08-19 확정 — refit 프로토콜)**: freeze된 config
   그대로 search 창만 **2015-01-01~2023-12-31**(pre-test 전체)로 확장해 최종
   공식 alpha pool을 재마이닝한다. 근거: ① v1 E5에서 실측된 신호
   감쇠(valid IC 0.033 → 2년 후 0.013) — 2021년에 끝난 pool로 2024~26을
   평가하면 staleness 핸디캡, ② ASB가 "test 이전 전체 = mining 기간"으로
   취급하는 원칙과 정합. 규약: refit은 freeze 이후이므로 validation이
   candidate fitness에 들어가도 설정 선택 피드백이 불가능하다(표준
   train+val refit). refit run의 진단으로 config를 수정하는 것은 금지(freeze
   위반). label tail exclusion은 2023-12-31 경계에 적용되고 test까지 3주
   gap이 있다. **내재 한계(정직 기재)**: C-1 배분은 7y 창(2015–21)에서
   검증되고 refit은 9y 창 — 조건 차이는 refit 프로토콜의 알려진 한계로
   ledger에 기재한다.
8. **Phase D (분리)**: 번들 갱신(→2026-06-30+) + parity check + 번들 버전
   스탬프 → ASB 평가 통합 범위 결정(ASB-P1.0 Track 적용 선언) → 동결 test
   1회 평가(Primary Full OOS + Strict Untouched Subset 병기, §6).
