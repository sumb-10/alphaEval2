# REPRODUCIBILITY — seed / cache / manifest / versioning

## 결정론 보증

동일 (config, input, seed)로 재실행하면 **metric parquet 내용이 완전히
동일**하다 — Phase 9 통합 테스트(`test_deterministic_rerun`)가
DataFrame 단위 exact 비교로 보증한다. timestamp는 manifest에만 기록되고
metric 파일에는 들어가지 않는다.

## 난수 통제

모든 stochastic 요소는 명시적 시드를 갖는다:

| 요소 | 시드 | 방식 |
|---|---|---|
| PFS Gaussian/Student-t noise | `pfs.seed` | `default_rng(sha256(market\|split\|noise_type\|seed\|draw\|dataset_version\|mode))` — method·formula 무관하게 동일 텐서 공유 |
| QD rarefaction subsampling | `qd.rarefaction.seed` | `default_rng(seed)` |
| PCA | 결정적 (`sklearn PCA` full SVD) | reference 데이터로 고정 |
| (참고) legacy AlphaEval PFS | 원본은 **무시드 + 멀티프로세스 fork RNG** — 비재현. ASB의 `legacy_alphaeval` 모드는 시드 고정 재구현 | |

## Cache key

formula 값/IC 캐시의 유효 범위: `(formula, start, end)` — 패널(engine)
인스턴스에 귀속되며, 패널은 (provider_uri, warmup_start, panel_end)로
정의된다. perturbation cache는 위 표의 noise 키를 그대로 사용한다.
서로 다른 dataset/market/split 간에 캐시가 재사용되지 않는다.

## Manifest (out/manifests/run_<method>_<seed>.json)

기록 항목: ASB 버전·git commit, python/qlib/numpy/pandas/scipy/sklearn/
pyarrow/joblib 버전, dataset 경로+버전 식별자(기간·종목수), market·benchmark,
train/valid/test split, label 정의(+`label_uses_post_end_price`), execution
정의(모드·비용·turnover 정의·MDD/연환산 convention), train_sign_rule,
validity config(+hard rule 목록), QD descriptor set·regime threshold 수치·
projection·grid·quality·dedup, PFS 설정 전체, run 정보(method/seed/formula
수/weights 출처/trajectory 유무/산출 파일 목록/parquet 폴백 목록), timestamp.

QD 좌표계는 `manifests/qd_projection/`(scaler.pkl + pca.pkl +
qd_manifest.json — descriptor 순서·reference runs/split·explained variance·
sklearn 버전)에 고정된다. 새 method는 `qd.projection.load_from`으로 이
좌표계를 재사용해야 동일 지도에 투영된다.

## Leakage 방지 규약 (재확인)

- train_sign: train에서만 산출 (입력 or 재평가 복원) — 평가기에 test 기반
  방향 결정 API 없음
- pool weights: train 학습값 freeze (미제공 시 equal — manifest 기록)
- regime threshold·PFS σ: train 캘리브레이션 후 valid/test 공용
- PCA/scaler fit: validation descriptor만 (`reference_split` 기록)
- HQ threshold: config 사전 지정 — test 분포로 자동 결정 금지

## 검사 스크립트

```bash
python scripts/check_no_alphaeval_imports.py   # core의 AlphaEval import 금지
python scripts/check_original_untouched.py     # Phase 0 기준선 대비 원본 무수정
```
