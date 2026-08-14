# AlphaSearchBench TODO

상태: `[ ]` not started · `[-]` in progress · `[x]` completed · `[!]` blocked/issue
최종 갱신: 2026-08-14 — **v0.1 Core + Optional 전부 완료** (테스트 기록:
docs/IMPLEMENTATION_NOTES.md 하단 표)

## Phase 0 — Scaffold [완료]
- [x] 디렉토리 구조 + 패키지 뼈대
- [x] env audit (py3.8.20, qlib 0.9.0, pandas 1.5.3, numpy 1.24.3, scipy 1.10.1, sklearn 1.3.2, joblib 1.4.2, yaml 6.0.3)
- [x] pyarrow 17.0.0 + pytest 8.3.5 설치
- [x] git 기준선 스냅샷 (out/manifests/phase0_baseline_*.{diff,txt}, HEAD a9263be)
- [x] config.py + configs/{default,smoke}.yaml + examples/csi_example.yaml (default에 연구 split 없음)
- [x] cli.py (`python -m alphasearchbench --help`)
- [x] qlib bootstrap + universe/필드 1개 조회
- [x] tests/smoke/test_phase0_scaffold.py — 4/4 PASSED

## Phase 1 — SignalContext + Validity Gate [완료]
- [x] data/qlib_provider.py (FormulaEngine — tensor_eval 포팅, **silent fallback 제거**, 임의 구간 compute)
- [x] data/universe.py (PIT mask+hash), labels.py (forward/execution), signal_context.py
- [x] validity/ — hard invalid(코드 고정) vs research threshold(config) 분리
- [x] tests/smoke/test_phase1_signal_validity.py — 10/10 PASSED (synthetic 6종 + TensorEvaluator 공통컬럼 **비트 일치**)

## Phase 2 — OOS [완료]
- [x] oos/metrics.py (daily IC/RankIC series, ICIR raw+_ann — AlphaForge 관례), oos/evaluator.py (factor/pool)
- [x] tests/smoke/test_phase2_oos.py — 8/8 PASSED (perfect/inverse+sign/random/constant/tie 손계산/combined 손계산)

## Phase 3 — QD core descriptors [완료]
- [x] qd/descriptors.py — H(IC_1/5/10/20 + configurable reducer)/V/M/L/B + signal_coverage/weight_turnover/liq_footprint, contrast+denom_small
- [x] qd/rre.py — RRE_qd(교집합 재정규화·oriented·common_n 진단) + RRE_legacy(별도 이름)
- [x] tests/smoke/test_phase3_qd_core.py — 11/11 PASSED

## Phase 4 — QD projection / pool metrics [완료]
- [x] qd/projection.py (valid-fit PCA, persist/reload 재현, diagnostics)
- [x] qd/grid.py (overflow 기록·클리핑 금지, coverage/entropy/evenness/NN/HQ/rarefaction)
- [x] qd/diversity.py (DE_legacy + DE_common_valid + n_factors_used/dropped + insufficient→NaN+reason; pairwise 미구현 — 스펙)
- [x] tests/smoke/test_phase4_qd_pool.py — 9/9 PASSED

## Phase 5 — Search-QD / trajectory [완료]
- [x] inputs/schemas.py + loaders.py + trajectory.py (표준 스키마 — core는 miner 무관)
- [x] qd/trajectory.py (unique/budget/generation metrics, dedup은 분석 전용·원본 보존)
- [x] [Optional] instrumentation/gplearn.py (monkey-patch adapter) + autoalpha.py (LoggingEvaluator — 한계 문서화)
- [x] tests/smoke/test_phase5_trajectory.py — 5/5 PASSED (trajectory 부재 graceful 포함)

## Phase 6 — PFS (Core) [완료]
- [x] qd/pfs.py — legacy_alphaeval / paper_literal(기본) / relative_input(experimental) 분리, PerturbationPolicy 플러그, deterministic noise(method·formula 간 텐서 공유), K-draw, daily Spearman, PFS_min, σ=train 지수 일수익률 std
- [x] tests/smoke/test_phase6_pfs.py — 5/5 PASSED (ε=0→1, seed 재현, 텐서 공유, t(3) 스케일, legacy 네임스페이스)

## Phase 7 — Simple backtest [완료]
- [x] backtest/simple.py (20/20·0.5/0.5·gross1·net0, exec 4모드 — 기본 next_open_oo, 첫날 건립비용 명시) + metrics.py (AnnRet_arith+CAGR+Sharpe+MDD양수+turnover l1/oneway)
- [x] tests/smoke/test_phase7_backtest_simple.py — 5/5 PASSED (손계산 대조, full flip l1=2/oneway=1)

## Phase 8 — Qlib native [Optional — 완료·지원범위 문서화]
- [x] timestamp audit: 신호 t → **t+1 시가 체결** 실증, deal_px == $open 일치
- [x] naked short 미체결 확인 → **long-only 지원**으로 문서화 (backtest/qlib_native.py, BACKTEST.md, IMPLEMENTATION_NOTES.md)
- [x] tests/smoke/test_phase8_qlib_timestamp.py — 2/2 PASSED

## Phase 9 — 통합 [완료]
- [x] runner.py (validity→OOS→QD(+PFS)→backtest→outputs) + outputs/writer.py(parquet+pkl폴백) + manifest.py(provenance 전체)
- [x] tests/smoke/test_phase9_integration.py — 7/7 PASSED (E2E 1커맨드, 7 parquet, manifest, **결정론 재실행 exact**)

## Phase 10 — Regression / synthetic / docs [완료]
- [x] tests/regression/test_legacy_alphaeval.py — 4/4 PASSED (IC/RankIC는 실제 ictester와 1e-9 일치; RRE/DE는 verbatim 스니펫과 1e-12; PFS_legacy는 동일 ε 주입 시 완전 일치)
- [x] tests/synthetic/test_synthetic_suite.py — 6/6 PASSED
- [x] scripts/check_no_alphaeval_imports.py — OK (instrumentation/ 예외)
- [x] scripts/check_original_untouched.py — OK (Phase 0 기준선 대비 추가 변경 없음)
- [x] README.md + docs/{METRICS, QD_DESCRIPTORS, BACKTEST, DATA_CONTRACT, REPRODUCIBILITY, IMPLEMENTATION_NOTES, IMPLEMENTATION_PLAN}.md

## 잔여 (pilot 이후 결정 — 스펙 §C)
- [ ] validity research threshold 수치 — **재료 확보**: train/valid 분포만으로
      (0.05/30/0.90) 재도출 완료(`docs/experiment/asb_pilot_verification.md` V5).
      결정 필요: gate 기준 split 규칙(권장: train+valid 모두 통과), 경계 대비
      threshold 상향(0.05→0.15) 여부
- [ ] `oos.min_daily_n_for_ic` config 신설 여부 (기본 2 유지 시 기존 결과 불변 —
      검증 V4에서 소표본 ±1 IC 실증)
- [ ] sign 복원 창=마이닝 창 규칙의 config 강제 여부 (검증 V1: 이번 pool은
      flip 0건이었으나 창 불일치는 구조적 위험)
- [ ] QD grid 해상도·PC bounds 확정 (여러 run 공용 좌표계는 qd.projection.load_from 사용)
- [ ] HQ coverage threshold
- [ ] PFS_research perturbation policy 확정 (paper_literal vs relative_input — pilot)
- [ ] pairwise/대안 DE 검토 (experimental)
- [ ] Horizon reducer 최종 선택

## Pilot 신뢰성 검증 (2026-08-14, 6개 지적 감사 — 전부 완료)
- [x] V1 train_sign 창 재복원 (마이닝 창 2010–2019) → flip 0건, 결론 불변
- [x] V2 신호 동등성 + fitness 재현 → 21/21 fitness 6자리 재현, 정상 17개
      비트일치; overflow 병리 4개의 경계 편차는 IMPLEMENTATION_NOTES #3 문서화
- [x] V3 coverage 분모 PIT 실측 확인
- [x] V4 소표본 IC(±1) 실증 → pilot §3.1 서술 격하
- [x] V5 threshold를 train/valid 분포만으로 재도출 → pilot §4 근거 교체
- [x] V6 orientation 단일 적용 감사 + 회귀 테스트 추가
- [x] V7 헤드라인 수치 독립 재계산 (ASB 미사용) → 소수점 6자리 일치
