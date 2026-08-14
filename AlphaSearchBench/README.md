# AlphaSearchBench

**alpha search/mining method가 생성한 formula와 alpha pool을 공통 기준에서
평가하는 독립 benchmark/evaluation framework** (v0.1).

기존 AlphaEval 평가 코드의 확장이 아니라, 그 조사 결과
([blueprint v1](../docs/new_Eval_blueprint.md) ·
[v2](../docs/new_Eval_blueprint_v2.md))를 바탕으로 한 독립 재구현이다.
AlphaEval 원본 소스는 수정하지 않으며, production 런타임은 AlphaEval 내부
모듈을 import하지 않는다 (`scripts/check_no_alphaeval_imports.py`로 검사).

```
Alpha Mining Result (formulas / pool / weights / trajectory)
        │  표준 입력 스키마 (docs/DATA_CONTRACT.md)
        ▼
  SignalContext ─ formula 평가·PIT universe·train sign·label·benchmark
        ▼
  Validity Gate ─ hard invalid는 downstream 제외 / research threshold는 config
        │
   ┌────┼─────────┐
   ▼    ▼         ▼
  OOS   QD     Backtest (simple / [opt] qlib-native long-only)
   └────┼─────────┘
        ▼
  Standardized parquet + provenance manifest
```

## 설치 / 요구사항

- conda env `AlphaEval38` (python 3.8, qlib 0.9.0, pandas 1.5.3, numpy,
  scipy, scikit-learn, joblib, pyyaml) + `pyarrow`, `pytest`
- Qlib CN 일봉 번들 (기본 경로는 `configs/default.yaml`의
  `dataset.provider_uri`)

## Quick start

```bash
cd AlphaEval/AlphaSearchBench
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

# 전체 파이프라인 (validity → OOS → QD → simple backtest)
$PY -m alphasearchbench evaluate \
    --config configs/smoke.yaml \
    --input path/to/miner_result.csv \
    --method gp --seed-id 42 \
    [--weights weights.json] [--trajectory traj.jsonl]

# 개별 모드
$PY -m alphasearchbench oos      --config ... --input ...
$PY -m alphasearchbench qd       --config ... --input ...
$PY -m alphasearchbench backtest --config ... --input ...
$PY -m alphasearchbench validity --config ... --input ...
```

입력은 `formula` 컬럼을 가진 csv/pkl/parquet — miner가 무엇이든 무방하다.
연구 split은 `configs/default.yaml`에 없고(의도적), experiment config에서
지정한다 (`configs/examples/csi_example.yaml` 참조).

## 출력

```
out/metrics/   validity_factor_metrics.parquet
               oos_factor_metrics.parquet / oos_pool_metrics.parquet
               qd_factor_descriptors.parquet / qd_pool_metrics.parquet
               (qd_generation_metrics.parquet — trajectory 제공 시)
               backtest_factor_metrics.parquet / backtest_pool_metrics.parquet
out/daily/     oos_daily / backtest_daily (일별 시계열 — 재집계용)
out/manifests/ run_<method>_<seed>.json + qd_projection/{scaler,pca,qd_manifest}
               + descriptor_diagnostics_*
```

## 세 파이프라인의 역할 (혼동 금지)

| 파이프라인 | 측정 대상 | 지표 |
|---|---|---|
| **OOS** | signal 자체의 out-of-sample 예측력 | IC · RankIC · ICIR · RankICIR (raw; `_ann` 별도) |
| **QD** | 행동 특성과 pool의 행동공간 다양성 | H/V/M/L/B/RRE_qd + coverage/entropy/NN/HQ + DE |
| **Backtest** | 명시적 포트폴리오·체결 가정 하의 투자 성과 | AnnRet_arith · CAGR · Sharpe · MDD · turnover · cost |

개념 구분 (docs/QD_DESCRIPTORS.md 상세):

- **Signal Coverage ≠ Activation Breadth ≠ QD Coverage** — 값 생성 범위 /
  가중치 분산도 / 행동공간 점유율.
- **AlphaEval DE = signal-space 통계적 다양성**, **QD Coverage =
  behavior-space 다양성** — 같은 "diversity"가 아니다.
- **Final-Pool QD**("무엇을 남겼는가") ≠ **Search-QD**("어떤 공간을 어떻게
  탐색했는가") — 별개 분석 (`scope` 컬럼으로 분리).

## 핵심 원칙

- **silent fallback 금지** — formula 평가 실패는 `$close` 대체가 아니라
  `invalid_reason`으로 보고된다.
- **train_sign은 train에서만** — 평가기는 sign을 입력으로만 받는다.
  입력에 signed_train_IC가 없으면 train split 재평가로 복원한다.
- **weights freeze** — pool 결합은 train에서 학습된 weights를 그대로 사용.
- **legacy / paper / research 분리** — `RRE_legacy` vs `RRE_qd`,
  `PFS_*_legacy` vs `PFS_Gaussian`(paper_literal) 등 이름을 섞지 않는다.
- **재현성** — 모든 난수는 시드 고정, 동일 config+seed 재실행 = 동일 metric
  parquet (Phase 9 테스트로 보증).

## 테스트

```bash
$PY -m pytest tests/ -q                        # 전체
$PY scripts/check_no_alphaeval_imports.py      # core의 AlphaEval import 금지 검사
$PY scripts/check_original_untouched.py        # 원본 무수정 검사 (Phase 0 기준선 대비)
```

instrumentation/(gplearn·AutoAlpha adapter)과 qlib-native backtest는
**optional integration**이다 — 지원 범위와 제약은
docs/IMPLEMENTATION_NOTES.md, docs/BACKTEST.md 참조.
