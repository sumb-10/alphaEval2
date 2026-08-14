# gplearn_asb TODO

## Phase A — Audit
- [x] 원본 GP 스택 감사 (entrypoint/genetic loop/fitness 방향/병렬/캐시/seed/selection)
- [x] ASB 재사용 표면 확정 (FormulaEngine/validity/trajectory/config/schemas)
- [x] IMPLEMENTATION_PLAN.md 작성

## Phase B — Original-equivalent copy
- [x] vendored_gplearn 7파일 byte-identical 사본 + PROVENANCE.md (md5 대조)
- [x] config.py (yaml deep-merge, default.yaml — 연구값 hard-code 없음)
- [x] cli.py (qlib bootstrap → qlib.init no-op → backtest preseed → vendored import)
- [x] genetic.py off 모드 (phase-A RNG-보존 사본 + 배치 진단)
- [x] gen-0 동일성 테스트 (vendored vs 원본, seed 42, 200 프로그램 완전 일치)
- [x] **883881 조건 off-run 전체 재현**: 최종 pool formula 목록 완전 동일
      (HOF 중복 패턴 포함), IC 최대 차 9.7e-17, 100 evals
      — `out/replicate_883881_off/`
- [x] 발견·수정: `_daily_ic` 합산식이 드물게 r=±inf를 산출
      (`Min(Power($volume,$amount),12)`) → pandas corr 의미론(±inf 불가)에
      맞춰 non-finite→NaN 강등. 방치 시 stopping_criteria(1.0) 오발로
      1세대 조기 종료 — 재현 실패의 원인이었음 (evaluator.py 주석 참조)

## Phase C — Diagnostics only
- [x] evaluator.py: FormulaEngine + fast호환 IC + compute_validity_stats 상시 계산
- [x] cache.py: diagnostics memo (threshold 적용과 분리, context 기록)
- [x] off 모드 $close fallback 재현 + fallback_used 로깅

## Phase D — hard_penalty
- [x] fitness.py: hard invalid 4종 → worst sentinel (−1.0, config)
- [x] penalty 모드에서 fallback 차단 (eval 실패 = hard invalid)

## Phase E — strict_penalty
- [x] research threshold (>= pass, 경계값 통과) 적용
- [x] population 내 invalid 유지 (drop/resample 경로 없음 — 원본 구조 그대로)

## Phase F — Trajectory / diagnostics
- [x] trajectory row 전 필드 (스펙 #17 + fallback_used)
- [x] generation stats (스펙 #15/18) + parent diversity
      (n_unique_parents_selected / parent_selection_entropy / top_share)
- [x] budget: total/unique evaluations, memo_hits(마이닝 중), wall_clock

## Phase G — Tests
- [x] unit: sentinel ordering / threshold 경계(0.050·30·0.900 pass) /
      tournament가 effective 사용(#26) / off fallback / NaN threshold fail
- [x] regression: gen-0 동일성(#22), 합성 population 안정성(#25 — pop 100,
      invalid 89%, 다음 세대 100 유지 + invalid 잔존 + valid 부모 과대표집)
- [x] smoke: 3모드 미니 run (population 불변, trajectory 스키마,
      모드 간 gen-0 동일, invalid=worst, ASB load_result 호환)
- [x] regression: pathological fixture(#23 — 883929 winner 2종 + Log($volume)
      + window-0 eval 실패)
- [x] 전체 suite Slurm 확인: 19/19 PASS (two-pass·fixture 수정 후, job 884222+로컬)
- [x] check_original_untouched OK + ASB 80 테스트 회귀 없음 (job 884327)

## Phase H — Comparison pilot (사용자 지시: **csi800 only**)
- [x] pilot_csi800_base.yaml (= 883929 조건: pop1000 gens5 hof50 ncomp10
      seed42, 2010–2019) + slurm_gplearn_asb.sbatch
- [x] Slurm 3 arms 실행·완료 (884301-3, arm당 ~88분)
- [x] ASB evaluate ×3 완료 (884383)
- [x] 비교표 + REPORT.md 작성 완료
