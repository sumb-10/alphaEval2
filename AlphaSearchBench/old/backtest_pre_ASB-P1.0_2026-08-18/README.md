# Snapshot — backtest 층 개정 전 (pre ASB-P1.0)

생성 2026-08-18 · git commit `6085013` · 총 28개 파일

## 목적

`docs/research_docs/backtest_design.md`(ASB-P1.0 명세)에 따라 backtest 층을
개정하기 전 상태의 사본이다. 개정 범위가 결합기·프로파일 집계·크기 정규화·
purge/embargo·연산자 parity·버전 스탬프에 걸쳐 있어, 개정 전후 수치 대조와
회귀 원인 추적을 위해 원본을 보존한다.

* 디렉토리 구조는 저장소 상대경로를 그대로 유지한다(`cp --parents`).
* 전 파일 sha256 대조 완료(불일치 0건, 아래 목록의 해시로 재검증 가능).
* `old/conftest.py`가 `collect_ignore_glob = ["*"]`로 pytest 수집을 차단한다
  (사본 테스트 파일이 이중 수집되는 것을 방지).

## 개정 예정 항목과 대응 파일

| 개정 항목 (design §13 체크리스트) | 주 대상 파일 |
|---|---|
| `train_signed_equal` combiner + 부호 정책(τ_sign) | `alphasearchbench/data/signal_context.py` |
| family별 프로파일 집계(median/IQR/PDR/worst) | `alphasearchbench/backtest/metrics.py`, `scripts/protocol_sweep.py` |
| rarefaction 기반 pool 크기 정규화 | `alphasearchbench/qd/grid.py`(패턴 참조), `scripts/protocol_sweep.py` |
| purge/embargo 적용·기록 | `alphasearchbench/data/labels.py`, `alphasearchbench/runner.py` |
| `protocol_version` manifest 스탬프 | `alphasearchbench/manifest.py` |
| Track A 8구성 재정의 / Track B 분리 | `configs/examples/csi800_ref*.yaml`, `configs/default.yaml` |
| 연산자 parity 테스트 | `tests/` (신규), 기존 smoke 2본 참조 |

## 복원 방법

```bash
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
# 단일 파일
cp old/backtest_pre_ASB-P1.0_2026-08-18/<상대경로> <상대경로>
# 전체 (주의: 개정분 전부 되돌림)
rsync -a --exclude conftest.py old/backtest_pre_ASB-P1.0_2026-08-18/ ./
```

## 파일 목록 (sha256)

```
e41c500d2a778dcc  docs/METRICS.md
a2f6fe4f3999789f  docs/BACKTEST.md
edde59cd3cc1a332  configs/default.yaml
04c6d3e9341fa494  alphasearchbench/manifest.py
03d5773cbb484057  alphasearchbench/runner.py
1ee6b2ae458a6e09  scripts/slurm_protocol_sweep.sbatch
d618bab6f28b61a0  scripts/manifest_to_report_table.py
9034333e556c9e85  scripts/protocol_sweep.py
af579dc652741412  tests/smoke/test_phase8_qlib_timestamp.py
186c2ae87ef40fc8  tests/smoke/test_phase10_qlib_native_fallback.py
08355deb4e7ba425  tests/unit/test_protocol_arms.py
29922703b35f4c56  docs/research_docs/backtest_design.md
f3d9b8b37b6d2d8a  gplearn_asb/scripts/slurm_eval_one.sbatch
2db23074273bca30  configs/examples/csi800_ref.yaml
d6d5b7d4897cd781  configs/examples/csi800_ref_legacy.yaml
a3aa783fac81996a  configs/examples/csi800_ref_fp.yaml
2bcbac397947f951  configs/examples/csi800_ref_lowturn.yaml
ef39bc92317bc4e5  configs/examples/csi800_allcand.yaml
10becad3d5759b16  configs/examples/csi800_example.yaml
630da8bb7a05665b  configs/examples/csi800_ref_qlib.yaml
4f705e196571bbf1  alphasearchbench/qd/grid.py
e7f1b5e583e4b55b  alphasearchbench/backtest/simple.py
e3b0c44298fc1c14  alphasearchbench/backtest/__init__.py
aa081d6e5d663aa4  alphasearchbench/backtest/qlib_native.py
87bed3af3218481c  alphasearchbench/backtest/metrics.py
6d8fbbec57e1d4e3  alphasearchbench/data/labels.py
972c46f3cdee235d  alphasearchbench/data/signal_context.py
1ee6b2ae458a6e09  scripts/slurm_protocol_sweep.sbatch
```
