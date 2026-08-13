# fast_opt_gplearn — gplearn 고속 실행 가이드 (fast / tensor 러너)

이 문서는 AlphaEval gplearn을 **원본 무수정**으로 빠르게 돌리는 두 러너의
실행 방법, 조건 변경, 결과 분석 방법을 정리한 것이다.

- 관련 파일: [`../scripts/`](../scripts/) (전부 신규 — 삭제하면 완전 원복)
- 병목 분석·클러스터 정보: [`../docs/PerformanceAndSlurm.md`](../docs/PerformanceAndSlurm.md)
- gplearn 알고리즘 자체: [`README.md`](README.md), [`../docs/AboutGPLearn.md`](../docs/AboutGPLearn.md)

---

## 1. 세 가지 실행 경로 비교

| | 원본 `gplearn.py` | **fast 러너** | **tensor 러너** |
|---|---|---|---|
| 파일 | [`../gplearn.py`](../gplearn.py) | [`../scripts/run_gplearn_fast.py`](../scripts/run_gplearn_fast.py) | [`../scripts/run_gplearn_tensor.py`](../scripts/run_gplearn_tensor.py) |
| 평가 방식 | 개체마다 Qlib 조회 3회 | Qlib 조회 chunk 배칭 + label 캐시 + 표현식 memo | **패널 1회 적재 + 연산자 직접 계산** |
| 개체당 비용 (all) | ~25.3s | ~4-8s | **~0.7-4.2s** (+시작 시 패널 ~50s) |
| 정확성 보증 | (기준) | **결과 불변** — 동일 seed → 동일 산출 ([`verify_equivalence.py`](../scripts/verify_equivalence.py) ALL PASS) | **검증된 일치** — 연산자 37/37 비트 일치, IC 오차 ≤1e-7 ([`verify_tensor_eval.py`](../scripts/verify_tensor_eval.py)) |
| 실행 가능 여부 | 그대로는 불가 (`fit()` 누락, placeholder 경로, `backtest/backtester.py` 부재) | 즉시 가능 | 즉시 가능 |

**어느 것을 쓰나:**
- 논문 재현·baseline 비교 등 **엄밀한 결과 불변**이 필요 → `fast`
- 대규모 탐색·스윕 등 **속도가 우선** → `tensor` (드물게 ~1e-7 IC 잔차가 tournament 순위를 바꿀 수 있어 결과 불변 "보장"은 아님 — 다만 실측에서는 pop=20·gens=2 동일 seed 실행이 **완전 동일한 factor를 산출**했다)

두 러너 모두 공통으로: `fit()` 호출 포함, placeholder 재-init 차단, 누락된 `backtest/backtester.py`를 `Alphaagent/backtester.py`로 보완(sys.modules), CSV+pickle 저장(이 env에 parquet 엔진 없음), `n_jobs=1` 고정(qlib 내부 병렬과의 중첩 금지 — 병렬성은 `kernels`가 담당).

---

## 2. 사전 준비 (1회)

```bash
# 환경: conda env AlphaEval38 (qlib 0.9.0 / pandas 1.5.3 / python 3.8)
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

# 데이터: 이미 로컬에 있음 (수정 불필요 — 러너 기본값이 이 경로)
#   /gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data
#   (989MB, 6016종목, 일봉 2005-01-04~2026-01-09)
# 주의: ~/.qlib/qlib_data/cn_data 는 깨진 심링크 — 쓰지 말 것

cd /gpfs/home1/sku07891/00.hojin/AlphaEval     # 반드시 저장소 루트에서 실행
mkdir -p out/slurm                              # sbatch 로그 디렉토리 (제출 전 필요)
```

정확성 검증을 직접 재현하려면:

```bash
$PY scripts/verify_equivalence.py      # fast 러너 결과 불변 (~5분, ALL PASS 기대)
$PY scripts/verify_tensor_eval.py      # tensor 연산자 37/37 비트 일치 (~4분)
```

---

## 3. 실행 방법

### 3.1 로그인 노드 스모크 (수 분)

```bash
$PY scripts/run_gplearn_fast.py   --start_time 2016-01-01 --end_time 2019-12-31 \
    --population_size 20 --hall_of_fame 10 --n_components 5 --generations 2 \
    --market csi300 --out out/smoke_fast

$PY scripts/run_gplearn_tensor.py --start_time 2016-01-01 --end_time 2019-12-31 \
    --population_size 20 --hall_of_fame 10 --n_components 5 --generations 2 \
    --market csi300 --out out/smoke_tensor
# 두 결과의 formula/IC가 동일한지 눈으로 확인 가능 (실측: 완전 동일)
```

### 3.2 Slurm 본 실행

[`../scripts/slurm_gplearn.sbatch`](../scripts/slurm_gplearn.sbatch) 인자:
`<start> <end> <pop> <gens> <hof> <ncomp> [seed=42] [market=all] [runner=fast|tensor]`

```bash
# fast 러너 (결과 불변) — 논문 기본 설정
sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10

# tensor 러너 — 같은 설정을 더 빠르게
sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10 42 all tensor

# Random Baseline (= gens 1)
sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 1 50 10

# 시드 스윕 (QoS: 동시 10 job / 640 CPU / walltime 2일)
for s in 0 1 2 3 4; do
  sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10 $s all tensor
done
```

- partition은 제출 시 `-p cpu1`(48c 노드) 또는 `-p cpu2`(256c 노드, 대개 여유). GPU 불필요.
- 코어 수 변경: `sbatch -p cpu2 -c 64 ...` — 러너가 `SLURM_CPUS_PER_TASK`로 `kernels`를 자동 설정.
- 모니터링: `squeue -u $USER`, `tail -f out/slurm/alphaeval-gp-<jobid>.log`, 취소는 `scancel <jobid>`.

### 3.3 CLI 옵션 (두 러너 공통)

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--start_time/--end_time` | 필수 | 마이닝(in-sample) 구간. 평가 구간(예: 2021–2024)과 겹치지 않게 |
| `--population_size` | 100 | 세대별 개체 수 |
| `--generations` | 10 | 세대 수. `1`이면 Random Baseline |
| `--hall_of_fame` / `--n_components` | 25 / 10 | 상관도 제거 대상 / 최종 alpha 개수 |
| `--market` | all | `all/csi300/csi500/csi800/csi1000/csiall` (편입이력 반영) |
| `--kernels` | SLURM_CPUS_PER_TASK 또는 8 | qlib 내부 워커 수 |
| `--seed` | 42 | 재현 seed |
| `--out` | out/gplearn_fast(tensor) | 출력 경로 prefix |
| `--chunk_size` (fast만) | 24 | D.features 1회당 표현식 수 |

### 3.4 실측 소요 시간 참고표

| 설정 | fast | tensor |
|---|---|---|
| pop=20, gens=2, csi300 (스모크) | 27s | 31s + 패널 49s |
| pop=50, gens=2, all (32코어) | 7분 55초 (job 883881) | — |
| pop=1000, gens=5, all (32코어) | 세대당 ~70분 실측(883882) → **~6시간** | 추정 1~2시간 (수식+IC 0.7–4.2s/개) |
| (참고) 원본 구조 | ~35시간 (kernels=8 환산) | |

tensor의 패널 적재(~50s)는 고정비라서 **작은 실험에서는 fast가, 큰 실험에서는 tensor가 유리**하다. hall-of-fame 최종 단계는 두 러너 모두 qlib 경로(개체당 1회 조회)를 쓴다.

---

## 4. 결과물과 분석 방법

### 4.1 출력 파일

| 파일 | 내용 |
|---|---|
| `out/gplearn_<runner>_<market>_seed<seed>_<jobid>.csv` / `.pkl` | `formula`(Qlib 수식), `IC`(=\|IC\|, in-sample) — `n_components`개 행 |
| `out/slurm/alphaeval-gp-<jobid>.log` | 로그 — 아래의 분석 재료가 전부 여기 있음 |

### 4.2 로그에서 바로 뽑는 분석

```bash
LOG=out/slurm/alphaeval-gp-<jobid>.log

# ① 세대별 population 전체 fitness (수렴 곡선의 원자료)
grep "final:" $LOG

# ② 세대별 평가 효율 (memo 적중 = GP의 표현식 중복도)
grep "fast_eval" $LOG

# ③ 총 소요/설정 확인
head -1 $LOG; grep "^\[run\]" $LOG
```

수렴 곡선 그리기 (python):

```python
import re, numpy as np, matplotlib.pyplot as plt
gens = [np.array(eval(l.split("final:")[1]))          # 세대별 fitness 리스트
        for l in open("out/slurm/alphaeval-gp-<jobid>.log") if "final:" in l]
best = [g.max() for g in gens]; mean = [g.mean() for g in gens]
plt.plot(best, label="best |IC|"); plt.plot(mean, label="mean |IC|")
plt.xlabel("generation"); plt.legend(); plt.savefig("convergence.png")
```

### 4.3 GP vs Random Baseline 비교

같은 pop·hof·ncomp에서 `gens=5` vs `gens=1`을 돌린 뒤:

1. **최종 pool IC 분포** — 두 CSV의 `IC` 컬럼 비교 (평균/최댓값). Random은 "랜덤 수식 1,000개 중 상위 선별"이므로, GP가 이를 못 이기면 진화가 기여하지 않은 것.
2. **수렴 곡선** — GP 로그의 `final:` 세대별 best가 세대 0(=Random과 동일한 출발점)보다 상승하는지.
3. **수식 복잡도** — formula 길이/깊이 비교 (bloat 여부).

### 4.4 out-of-sample 평가 (AlphaEval 본 평가)

마이닝 IC는 in-sample이다. 진짜 평가는 held-out 구간에서:

```python
import qlib
qlib.init(provider_uri="/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data",
          region="cn", kernels=16)
qlib.init = lambda *a, **k: None          # modeltester/combo의 placeholder 재-init 차단

import sys, pandas as pd
sys.path.insert(0, "backtest")
from qlib.data import D
from modeltester import AlphaEval

exprs = pd.read_csv("out/gplearn_fast_all_seed42_<jobid>.csv")["formula"].tolist()
ev = AlphaEval(factor_expressions=exprs, weights=None,   # None → 학습구간에서 가중치 산출
               train_start_date="2010-01-01", train_end_date="2019-12-31",
               test_start_date="2021-01-01",  test_end_date="2024-12-31",
               instruments=D.instruments(market="all"))
ev.run(); ev.summary()
```

시드 여러 개를 돌렸다면 시드별 out-of-sample 지표의 평균±표준편차로 보고하는 것이 안전하다 (단일 시드는 운의 영향이 큼).

### 4.5 두 러너 교차 검증

중요한 실험이라면 동일 seed로 fast·tensor를 모두 돌려 CSV를 대조하라:

```python
import pandas as pd
a = pd.read_csv("out/gplearn_tensor_all_seed42_<job1>.csv")
b = pd.read_csv("out/gplearn_fast_all_seed42_<job2>.csv")
print((a["formula"] == b["formula"]).all(), (a["IC"] - b["IC"]).abs().max())
```

실측(pop=20, gens=2, csi300, seed=42): **formula 완전 일치, IC 차이 0.0**.

---

## 5. 동작 원리 요약

```
run_gplearn_fast.py / run_gplearn_tensor.py
   1) qlib.init(실경로, kernels) → 이후 qlib.init을 no-op으로 스텁
      (backtest/ictester.py가 import 시점에 placeholder로 재-init하는 것 차단)
   2) sys.modules["backtest.backtester"] ← Alphaagent/backtester.py
      (저장소에 없는 모듈 보완 — 원본 import 성립)
   3) gplearn.genetic._parallel_evolve ← make_fast_parallel_evolve(evaluator)
      · 개체 생성 루프는 원본과 동일 (개체별 seeds[i] RNG → 동일 프로그램 생성)
      · 평가만 배치: 세대의 표현식을 모아 evaluator.evaluate(exprs)
        - fast   : FastICEvaluator  — chunk 단위 D.features + label 캐시 + memo
        - tensor : TensorEvaluator  — 패널에서 직접 계산 (qlib 의미론 미러링)
   4) transformer.fit() → _best_programs → CSV/pickle 저장
```

tensor 평가기의 일치 원리(요약): rolling `min_periods=1`, 트리별 warm-up **좌·우 절단** 미러링(pandas roll_skew/kurt는 배열 전체 평균 중심화라 **질의 끝점이 과거 값에 영향**), `rolling.apply`는 float64 창 전달, 시리즈 시작은 bin 커버리지 기준, `Power`는 pd.Series dispatch 경유, `Slope/Rsquare/Resi`는 qlib Cython 직접 호출, 최종 float32 캐스팅. 상세는 [`../scripts/tensor_eval.py`](../scripts/tensor_eval.py) 모듈 docstring과 [`../docs/PerformanceAndSlurm.md`](../docs/PerformanceAndSlurm.md) 참고.

---

## 6. 알려진 한계 / 문제 해결

| 증상/한계 | 설명·해결 |
|---|---|
| tensor가 fast보다 느리다 (작은 실험) | 패널 적재 ~50s 고정비. csi300 소규모는 fast 사용 |
| `WMA(x, 120)` 등 큰 창이 tensor에서 느림 | 탐색 공간 창은 `[5,12,30,64]`라 실전 무관. 큰 창 실험 시 fast 사용 |
| hall-of-fame 단계가 여전히 오래 걸림 | 두 러너 모두 원본 execute()(qlib 조회) 유지 — hof 50이면 all 기준 ~9분 |
| `sbatch: error ... out/slurm` | 제출 전 `mkdir -p out/slurm` (Slurm이 로그 파일을 먼저 연다) |
| `to_parquet` 실패 | 정상 — env에 pyarrow 없음. CSV/pkl은 항상 저장됨 |
| `n_jobs>1`로 바꾸고 싶다 | 불가 — qlib 내부 병렬과 중첩되어 daemonic 오류. 병렬화는 `kernels`(job 내)와 **여러 job 제출**(job 간)로 |
| 수식이 Qlib에서 거절됨 | 원본과 동일하게 `$close`로 조용히 대체 후 낮은 IC로 도태. 로그의 fallback 카운트로 빈도 확인 |
| 구간이 다른 실험 간 factor 값 비교 | 주의 — qlib의 Skew/Kurt 값은 질의 구간(끝점 포함)에 의존한다. IC 비교는 무방 |
| 완전 원복 | `scripts/`, `docs/PerformanceAndSlurm.md`, `gplearn/fast_opt_gplearn_readme.md`, `out/` 삭제 (원본 파일 무수정) |
