# AlphaSearchBench 구현 계획

스펙: `../../docs/alphasearchbench.md` (사용자 확정). 설계 근거:
`../../docs/new_Eval_blueprint.md`(v1), `../../docs/new_Eval_blueprint_v2.md`(v2 — 실측 검증 포함).

## 아키텍처

```
Alpha Mining Result (formulas/pool/weights/trajectory — 표준 스키마)
        │  inputs/loaders.py  (miner 무관)
        ▼
SignalContext (data/) — market·splits·PIT universe mask·formula 평가·
        │                oriented signal·forward returns·benchmark·ADV20·z-score·combined
        ▼
Validity Gate (validity/) — hard invalid는 downstream 제외, research threshold는 report/strict
        │
   ┌────┼──────────┐
   ▼    ▼          ▼
  OOS   QD       Backtest(simple / [opt] qlib native)
   └────┼──────────┘
        ▼
outputs/ (parquet+daily+trajectory) + manifest.py (provenance)
```

## 핵심 계약

1. **원본 AlphaEval tracked 파일 무수정.** 기준선: `out/manifests/phase0_baseline_*.{diff,txt}` (HEAD a9263be). 종료 검사는 이 스냅샷과의 차분으로 수행.
2. **production 패키지(`alphasearchbench/`)는 AlphaEval 내부 모듈 import 금지.** 포팅은 재구현 + provenance 주석. `qlib.*`(qlib.data._libs 포함)은 외부 dependency로 허용. regression test의 reference import는 허용.
3. **instrumentation/은 optional adapter** — core는 표준 input/trajectory 스키마에만 의존. Search-QD는 스키마만 맞으면 어떤 miner든 평가 가능해야 함.
4. **silent fallback 금지** — formula 평가 실패 = hard invalid + reason.
5. **train_sign / weights / regime threshold / PCA fit 전부 train(또는 valid) 고정** — test에서 재추정하는 API를 만들지 않는다.
6. **legacy vs paper vs research 네임스페이스 분리** (RRE_legacy/RRE_qd, PFS_legacy/PFS_paper_literal/PFS_research 등).
7. **연구 미결정값은 config로** (validity threshold, grid, HQ threshold, cost rate, PFS policy, reducer 등) — magic number 금지.
8. **최적화는 정확성 다음** — RRE/RankIC 벡터화는 reference 구현과 equivalence 테스트 통과 후에만 (rank tie=average, NaN, PIT semantics 보존).

## v0.1 완료 계층

- Core: Validity / OOS / QD(final+search) / PFS infra / Simple Backtest / CLI / manifests / tests·docs
- Optional: Qlib native backtest, gplearn/AutoAlpha instrumentation — 제약 발견 시 IMPLEMENTATION_NOTES.md에 지원 범위 문서화로 종결

## Phase 계획 및 테스트 게이트

| Phase | 내용 | 게이트 |
|---|---|---|
| 0 | scaffold, env, git 기준선, config, CLI --help, qlib init+universe 조회 | test_phase0_scaffold.py |
| 1 | provider(포팅)+SignalContext+Validity(hard/research) | synthetic 6종 + TensorEvaluator 동등성 |
| 2 | OOS daily series+집계+combined | synthetic + 손계산 |
| 3 | QD core descriptors + RRE_qd | synthetic 방향성 + RRE equivalence |
| 4 | projection/grid/pool metrics + DE 2종 | synthetic pool + PCA reload 재현 |
| 5 | trajectory 로더/세대 지표 (+opt instrumentation) | synthetic 3세대 + graceful degradation |
| 6 | PFS 3모드 + deterministic noise + K-draw | ε=0→1, seed 재현, 텐서 공유 |
| 7 | simple backtest 4 exec 모드 | 손계산 + full-flip turnover |
| 8 | [opt] qlib native + timestamp audit | audit 로그 or NOTES 문서화 |
| 9 | 통합 CLI + outputs + manifest | smoke E2E + 결정론 |
| 10 | regression/synthetic/docs + 원본 무수정 검사 | 전체 스위트 |

## 환경

- conda env `AlphaEval38` (`/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python`)
- py3.8.20 / qlib 0.9.0 / pandas 1.5.3 / numpy 1.24.3 / scipy 1.10.1 / sklearn 1.3.2 / joblib 1.4.2 / yaml 6.0.3 / **pyarrow 17.0.0, pytest 8.3.5 (Phase 0에서 설치)**
- Qlib 데이터: `/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data` (지수 SH000300/905/906/852/985 포함)
- python 3.8 제약: 모듈에 `from __future__ import annotations` 사용

## 포팅 provenance 요약

| ASB 모듈 | 참고 원본 (AlphaEval 내부 — 재구현) |
|---|---|
| data/qlib_provider.py | scripts/tensor_eval.py `TensorEvaluator` (qlib 0.9.0 의미론 37/37 비트일치 검증본) — $close 폴백 제거 |
| data/universe.py | scripts/tensor_eval.py `_build_universe_mask` |
| qd/rre.py (legacy) | backtest/modeltester.py 313-327 |
| qd/pfs.py (legacy) | backtest/noise_proc.py + modeltester 76-113,306-311 |
| qd/diversity.py (legacy) | backtest/modeltester.py 202-229 |
| backtest/simple.py | Alphaagent/backtester.py 104-221 (수학 검증: v2 §O1-O3) |
| oos/metrics.py | backtest/ictester.py calculate1 집계 로직 |
