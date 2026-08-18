# gplearn_asb 구현 계획 — Validity-aware GP with Worst-Fitness Penalty

목적: 원본 GP의 search mechanics(트리/유전연산/tournament/population)를 보존하면서,
invalid candidate가 높은 IC fitness로 선택되는 루프홀만 **worst-fitness penalty**로
통제하는 실험 variant. 원본 소스 무수정. drop/resample 금지. population size 불변.

## Phase A 감사 결과 (설계 근거 — 원본 file:line)

### 원본 GP 스택의 사실
| 항목 | 값 | 근거 |
|---|---|---|
| 선택 | `_tournament` = `fitness_` argmax, 복원추출 randint | `gplearn/genetic.py:60-68` |
| fitness_ | `raw_fitness_ − parsimony·len·sign` (sign=+1) | `gplearn/_program.py:556-574`, `genetic.py:495-496` |
| 러너 실효 하이퍼파라미터 | tournament=20, p=(cx .9, sub .01, hoist .01, point .01 → repro 7%), init (1,4)+1 half-and-half, const_range=None, parsimony=0.0, metric='pearson'(방향만), n_jobs=1 | `genetic.py:793-825`, `scripts/run_gplearn_fast.py:87-99` |
| population 유지 | reject 경로 없음 — 무조건 append | `genetic.py:157` |
| HOF | `raw_fitness_` argsort → decorrelation(중복 미제거 버그) → n_components | `genetic.py:550-580` |
| seed | 세대마다 `randint(MAX_INT, size=pop)` → 개체별 독립 RNG | `genetic.py:472,75` |
| **루프홀 1** | 평가 실패 formula가 `$close`의 IC를 상속 | `scripts/fast_eval.py:121-125`, `backtest/ictester.py:42-57` |
| **루프홀 2** | 극소 cross-section ±1 IC (Rsquare std≈0 마스킹) | pilot §3, 검증 V2/V4 |
| 알려진 버그(보존) | `point_mutation`이 터미널을 raw int로 치환(`Var($factor,6)`, `Power(2,…)`) | `gplearn/_program.py:746,753` |
| IC 집계 | 일별 Pearson(NaN 쌍별 제거·inf는 그 날 오염), NaN>50%→0, nanmean, NaN→0 | `backtest/ictester.py:66-82` = `scripts/tensor_eval.py:457-479` |
| signed IC | evaluator `ic_memo`에만 존재(CSV IC=절댓값) | `fast_eval.py:89,173,291` |

### RNG 소비 순서 (동등성의 핵심 — phase-A에서 절대 보존)
`uniform()`(method 추첨) → `_tournament()`(+crossover면 2회) → 유전연산 내부 RNG →
`get_all_indices()` (결과 미사용이어도 호출). 원본 `genetic.py:73-145` ==
`scripts/fast_eval.py:225-285` == `alphasearchbench/instrumentation/gplearn.py:59-104`.

## 아키텍처

```
gplearn_asb/
├── vendored_gplearn/   # 원본 7파일 byte-identical 사본 (PROVENANCE.md 참조)
├── config.py           # yaml deep-merge 로더 (ASB Config 재사용, default 경로만 교체)
├── evaluator.py        # MiningEvaluator: FormulaEngine 신호 + fast호환 IC + validity stats + memo
├── fitness.py          # constraint mode → effective fitness (worst sentinel, threshold >= pass)
├── genetic.py          # make_asb_parallel_evolve: phase-A 사본 + 배치평가 + penalty + 로깅
├── trajectory.py       # ASB TrajectoryWriter 재사용 + generation stats
├── cache.py            # formula → diagnostics memo (threshold 적용과 분리)
└── cli.py              # python -m gplearn_asb.cli mine --config ... [--mode ...]
```

데이터 흐름 (diagnostics는 **모드 무관 상시 계산**):
```
formula → FormulaEngine.compute(search window) → validity stats(PIT mask, search-window-only)
        → signed IC(fast호환) → cache(diagnostics)
constraint mode → effective_fitness → p.raw_fitness_ (selection·HOF 소비)
원시값 → trajectory row(raw_fitness=|IC|, effective_fitness, validity 전 필드)
```

## 핵심 설계 결정

1. **worst sentinel = −1.0** (config `constraint.worst_fitness`): 유한, |IC|≥0보다 항상
   작음, argmax/argsort 안전. parsimony≠0 config면 경고 (sentinel 분리 보장 조건:
   `parsimony·max_len < |sentinel|`).
2. **off 모드는 원본 의미론 재현** — 평가 실패 시 `$close` signed IC 상속(fallback
   사용 사실은 로깅). penalty 모드에서는 fallback 차단 → hard invalid.
3. **IC 집계 = fast/ictester 호환** (isnan 마스킹 → inf가 그 날을 오염, >50% NaN→0.0):
   ASB `masked_daily_corr`(isfinite)와 다르다 — 마이닝은 원본 호환이 우선.
4. **validity는 search window 전체에서 단일 계산** (train-only, ASB split과 독립).
   threshold 규약: `value >= threshold → pass` (경계값 통과).
5. **모드 간 공정성**: 같은 seed → gen 0 동일, diagnostics 동일 계산. 다른 것은
   effective fitness 하나뿐. budget 로깅(total/unique evals, memo_hits, wall_clock).
6. hard invalid = `formula_eval_failed` / `all_nonfinite`(전 구간 non-finite) /
   `no_correlatable_day` / `zero_ic_observations` — ASB와 동일 4종.

## 구현 중 발견 (Phase B/G에서 확정)

1. **one-pass IC 합산식의 파국적 상쇄**: tensor_eval `_daily_ic`의
   sum(x²)−sum(x)²/n 식은 |값|~1e130 병리 신호(예: `Power($high,$change)`)
   에서 상쇄/overflow로 pandas corr와 다른 NaN 패턴을 만든다.
   실측: 883929 winner `Div(Less(Power(...)))`의 CSV fitness 0.074644는
   pandas 값과 6자리 일치하지만, 같은 코드(login node)의 one-pass 재계산은
   NaN 과반(65.7%) → 0.0 — 이 영역에선 결과가 합산 순서/하드웨어에 민감.
   → gplearn_asb는 **two-pass(중심화) Pearson**을 채택 (canonical 원본인
   fast runner/ictester = pandas corr와 동일 의미론; evaluator.py 주석).
2. **r=±inf 경로**: one-pass에서 inf−(−inf) 조합이 r=+inf를 만들 수 있고
   (`Min(Power($volume,$amount),12)`), |IC|=inf가 stopping_criteria(1.0)를
   오발시켜 진화가 조기 종료된다. pandas corr는 ±inf를 반환하지 않으므로
   non-finite r → NaN 강등 가드를 둔다.
3. **`Mean($close, 0)`은 유효**(qlib 의미론 N=0 → expanding) — eval 실패
   fixture로는 미지 연산자(`Quantile(...)`)를 써야 한다.

## 확장 (2026-08-14, 실험2용): fitness_metric = net_sharpe

- `gp.fitness_metric: abs_ic(기본) | net_sharpe`. net_sharpe = oriented 신호의
  search-창 일별 20/20 long-short **net Sharpe** (ASB simple backtest와 동일
  수학: gross 1=0.5/0.5, turnover_oneway=l1/2, 첫날 건립 비용, ddof=1, ×√252;
  비용률·quantile은 `backtest.*` config 주입). 부호는 train IC로 고정(oriented).
- 스케일 가드(cli 강제): worst_fitness ≤ −100 요구(음수 Sharpe도 valid),
  stopping_criteria ≥ 100 요구(원본 1.0은 Sharpe≥1 조기 종료 오발).
  net_sharpe NaN(무거래 등)은 `fitness_undefined:net_sharpe_nan`으로 worst.
- 진단 캐시에는 net_sharpe·연환산수익·turnover가 함께 저장되고, trajectory에
  `fitness_metric`/`net_sharpe` 컬럼 추가. IC 필드 의미는 불변.

## Phase 순서
A 감사(본 문서) → B vendored copy + off 동등성(gen-0 + 883881 재현) → C diagnostics
상시화 → D hard_penalty → E strict_penalty → F trajectory/gen-stats/parent diversity
→ G 테스트(unit/smoke/regression) → H 3-arm pilot(Slurm) + ASB evaluate + REPORT.md

## 확장 (2026-08-14, A+B+P): fixed HOF · 신뢰도 fitness · 정적 사전검증층

기본값은 전부 원형 유지(기존 run 재현성 불변 — 883881 재현 테스트가 강제),
vendored_gplearn 무수정.

### A. `gp.hof_mode: original(기본) | fixed` (hof.py)
- 근거: seed sweep 실측 — 원본 HOF exact-dup 미제거로 strict pool 유효 unique
  1–2/10 (seed 1, 2). HOF는 fit 이후 선택 단계 → vendored 무수정, RNG 불소비
  (탐색 재현성 불변, pool 구성만 교체).
- fixed 알고리즘: 최종 population(=trajectory 마지막 세대) → exact-dup 선제거
  (formula 문자열, best effective 유지) → effective 상위 hall_of_fame → NaN-safe
  decorrelation(일별 z-score 신호의 공통 finite 셀 Pearson; 퇴화 쌍=공통 셀
  <min_common_cells(100) 또는 corr NaN은 0 취급+`decorr_degenerate_pairs` 기록;
  |corr| 최대 쌍에서 낮은 eff 제거) → n_components.
- 소급: `scripts/repool_fixed_hof.py` — 완주 run의 trajectory 마지막 세대에
  오프라인 적용, `final_pool_<rid>_fixedhof.csv` + 파생 run 디렉토리 생성
  (원본 pool CSV 보존).

### B. fitness 계열 확장 (fitness.py / evaluator.py)
- **B1 `ic_tstat`** = |mean(daily IC)|/(std(daily IC, ddof=1)/√n_obs). `_daily_ic`가
  (ic, n_obs, daily_std) 3-튜플 반환으로 확장(AA diagnostics 호출부 동반 수정),
  진단에 `ic_daily_std`/`ic_tstat` 상시 저장. 판정 불가(n<2, std=0)는 NaN→worst
  (`fitness_undefined:ic_tstat_nan`). cli 가드: stopping ≥ 100 (t=1은 사소).
- **B2 net_sharpe 부가 조건** (기본 null=off): `gp.net_sharpe_min_traded_days`,
  `gp.net_sharpe_min_abs_ic` — 규약 value ≥ threshold → pass. 판정은 fitness.py
  (진단 캐시 순수 유지). 모드 무관(=fitness 정의의 일부), raw는 보존(스펙 #19),
  effective만 worst + `fitness_condition_failed` 기록.
- **B3 `fb_fitness`** = net_sharpe×√(|net_ann_ret_arith|/ann_turnover_oneway) —
  원본 backtester의 미사용 Fitness의 **ASB 의미론 재정의**(원본은 카운트
  turnover·기하 AnnRet — 수치 다름). turnover≤0/구성 NaN → worst
  (`fitness_undefined:fb_fitness_nan`). cli 가드 = net_sharpe와 동일.
- off-모드 $close fallback은 활성 metric 기준(`evaluator.close_raw_fitness`).

### P. 정적 사전검증층 (static_check.py, `gp.static_gate: true`)
- 2단 게이트: 생성 → [P1 문법(기존 파서) + P2 정적 규칙] → 합격만 데이터 접근
  → [P3 데이터 validity(기존 strict)]. **static ⊂ hard 증명이 성립하는 규칙만
  invalid로 승격** — 그래서 penalty 모드에서 effective fitness 불변(사유
  문자열·데이터 비용만 변화), off 모드는 원형(기록만, fallback 경로 불변).
  게이트 켠 evaluator는 캐시 네임스페이스 분리(`static_gate` 키 조건부 추가 —
  기존 run fingerprint 불변).
- 규칙: ① 상수식(`Sub(x,x)`/`Div(x,x)`/전-인자-상수 전파) →
  `static_invalid:constant_expression`. ② `gp.max_program_length`(기본 null) 초과
  → `static_invalid:too_long`(fitness.py 판정, penalty 모드 전용).
  ③ flag 전용(탐색 불개입): `static_flag_constant_subtree`,
  `static_flag_nonstd_window`, `program_size` 상시 기록.
- **정정 2건 (구현 중 실측)**: (a) Greater/Less는 qlib에서 element-wise
  max/min → f(x,x)=x 항등, 상수 아님 — 초안 판정기의 오판 101건/13 run을
  단위테스트로 고정. (b) window 0=expanding, 0<w<1 float도 엔진이 유효 평가 →
  "bad window" invalid 규칙은 static ⊂ hard를 깨므로 flag로 강등.
- 사전 실측(scripts/measure_static_savings.py, 13 run/22,539 unique): 진짜
  상수식 72(0.32%), bad-window 0, canonical 병합 271(1.2%) → **canonical memo
  키(P2-4)는 보류**(절감 대비 캐시 이중 키 복잡성).
