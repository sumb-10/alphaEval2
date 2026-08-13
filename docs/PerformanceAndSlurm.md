# PerformanceAndSlurm — gplearn의 Qlib 병목 분석과 Slurm 실행

두 가지 질문에 대한 측정 기반 답변이다.

1. **gplearn이 Qlib를 매번 조회하는 것이 시간 병목을 얼마나 발생시키는가? 데이터를 미리 받아놓고 시작할 수 있는가?**
2. **AlphaEval의 gplearn을 Slurm에 제출할 수 있는가?**

측정 환경: 로그인 노드, conda env `AlphaEval38`(qlib 0.9.0 / pandas 1.5.3), `kernels=8`,
데이터 `/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data`, 기간 2010-01-01 ~ 2019-12-31.

---

## Q1. Qlib 반복 조회의 병목은 얼마나 되는가

### 1.1 실측: 쿼리 1회의 비용

| 항목 | csi300 | **all** (gplearn.py 기본) |
| --- | --- | --- |
| label 쿼리 1회 (`Ref($close,-1)/$close - 1`) | 1.0s | 4.3s |
| factor 쿼리 1회 (표현식 5종 평균) | 2.5s | 10.5s |
| 표현식 5개를 **한 번의 `D.features`로 배칭** 시 개당 | 1.9s | 7.8s |

(표현식 복잡도에 따라 편차가 크다 — 예: `Skew` 포함 수식은 all 기준 32s)

### 1.2 현재 구조가 개체 하나당 지불하는 비용

원본 경로는 개체(수식) 하나를 평가할 때 **Qlib 조회를 3회** 한다.

| 조회 | 어디서 | 용도 | 비용(all) |
| --- | --- | --- | --- |
| factor ① | [`gplearn/_program.py:546`](../gplearn/_program.py#L546) `execute()` | **길이 검증에만 쓰이고 버려짐** | 10.5s |
| factor ② | [`backtest/ictester.py:43`](../backtest/ictester.py#L43) | IC 계산의 실제 입력 | 10.5s |
| label | [`backtest/ictester.py:58`](../backtest/ictester.py#L58) | **매 개체마다 동일한 데이터를 재조회** | 4.3s |

**개체당 ~25.3s 중 ~14.8s(58%)가 순수 낭비**다 (execute 중복 10.5 + label 재조회 4.3).
필요 최소치는 factor 1회 = 10.5s이고, 배칭하면 7.8s 이하로 내려간다.

총량으로 보면 (README 예시 `pop=1000, gens=5` = 5,000 evals, 직렬):

| | 개체당 | 총 시간 (kernels=8 기준) |
| --- | --- | --- |
| 현재 구조 | 25.3s | **~35시간** |
| 중복 제거 + label 캐시 | 10.5s | ~15시간 |
| + 배칭(chunk=24) + 표현식 memo | ≤7.8s | **~11시간 이하** |
| + 전용 노드에서 `kernels` 32~46 | — | 추가 단축 (아래 실측) |

여기에 GP 특성상 세대가 지나며 **동일 표현식이 반복 등장**하므로(reproduction, 동일 crossover 결과) 표현식→IC 메모가 추가로 평가 횟수 자체를 줄인다.

### 1.3 "미리 데이터를 받아놓고 시작"에 대한 답

**데이터는 이미 전부 로컬에 있다.** 네트워크는 병목이 아니다.

- 로컬 번들: `/gpfs/home1/sku07891/00.hojin/QuantaAlpha/data/qlib/cn_data`
  (989MB, 종목 6,016개, 필드 10개, 일봉 2005-01-04 ~ 2026-01-09, universe: all/csi300/500/800/1000)
- Qlib은 항상 이 로컬 `.bin` 파일을 읽는다. BaoStock은 **번들을 만들 때만** 필요하며, 기간 2010–2019는 이미 포함되어 있으므로 재다운로드할 것이 없다.
- ⚠️ `~/.qlib/qlib_data/cn_data`는 **깨진 심링크**다(상대 링크가 잘못된 곳을 가리킴). `alphaagent.py` 등이 이 경로를 기본값으로 쓰므로, 반드시 위의 절대경로를 사용해야 한다.

그렇다면 병목의 정체는 **매 호출마다 반복되는 계산 구조**다. `D.features` 1회는
"6,016개 종목 각각에 대해 표현식 재파싱·재계산 + 워커 프로세스 팬아웃 + 결과 concat"을 수행한다.
즉 "미리 받아놓기"에 해당하는 올바른 처방은 다운로드가 아니라 **호출 중복 제거·캐싱·배칭**이며, 이것이 `scripts/fast_eval.py`가 하는 일이다.

> 참고 — 더 근본적인 대안(구현됨): raw 패널을 **한 번만** 메모리에 올리고 29개 연산자를 직접 계산하는 텐서 트랙이 [`scripts/tensor_eval.py`](../scripts/tensor_eval.py)에 있다. qlib 0.9.0 소스의 의미론(min_periods=1, warm-up 좌/우 절단, Greater/Less=max/min, 최종 float32 캐스팅, Slope/Rsquare/Resi는 qlib Cython 직접 호출 등)을 미러링해 [`scripts/verify_tensor_eval.py`](../scripts/verify_tensor_eval.py) 기준 **연산자·합성식 37/37 float32 비트 단위 일치, IC 오차 ≤ 1e-17**(csi300, 일부 복합식은 all universe에서 ~1e-7)을 달성했다. 속도는 market=all에서 수식+IC 한 사이클 **12.9~41s → 0.7~4.2s (10~18×)**, 패널 적재 1회 ~49s. 단 이 트랙은 '결과 불변' **보장**이 아니라 '검증된 일치'이며, GP 실험에 쓰려면 fast runner의 평가기를 교체하는 추가 작업이 필요하다.
>
> 이 과정에서 발견한 qlib 재현성 특성 두 가지: (1) pandas `roll_skew`/`roll_kurt`가 배열 전체 평균으로 중심화하므로 **Skew/Kurt 값이 질의 구간의 오른쪽 끝(end_time)에 의존**한다 — 같은 날짜의 값이 질의 구간에 따라 달라질 수 있다. (2) rolling var/skew/kurt·EMA·Slope류는 스트리밍 누적이라 **warm-up 절단 위치(=트리의 extended window)에 값이 의존**한다. 원본 파이프라인도 동일 조건이므로 실험 내 일관성은 유지되지만, 구간이 다른 실험 간 factor 값 비교에는 주의.

### 1.4 구현: 결과 불변 최적화 (`scripts/`)

원본 파일은 **하나도 수정하지 않았다.** 원복 = `scripts/` 신규 파일 삭제.

| 파일 | 내용 |
| --- | --- |
| [`scripts/fast_eval.py`](../scripts/fast_eval.py) | label/`$close` 패널 캐시, 표현식 chunk 배칭(+실패 시 개별 폴백→`$close` 대체, 원본과 동일), `ICBacktester.calculate1`의 **정확한 수식 재현**, 표현식→IC 메모 |
| [`scripts/run_gplearn_fast.py`](../scripts/run_gplearn_fast.py) | 러너. 실경로 `qlib.init`(+`kernels`) → placeholder 재-init 차단 → `_parallel_evolve` monkey-patch → **`fit()` 호출 포함** → CSV+pickle 저장 |
| [`scripts/verify_equivalence.py`](../scripts/verify_equivalence.py) | 동등성 검증 (아래) |
| [`scripts/slurm_gplearn.sbatch`](../scripts/slurm_gplearn.sbatch) | Slurm 제출 스크립트 (Q2) |

**결과 불변의 근거**: `_parallel_evolve`는 개체마다 `seeds[i]`로 독립 RNG를 만들고, offspring 생성은 이전 세대의 fitness만 참조한다. 따라서 "세대 전체를 먼저 생성 → 표현식을 모아 배치 평가"로 순서를 바꿔도 RNG 소비열과 생성 프로그램이 동일하고, IC는 표현식의 결정적 함수이므로 memo/배칭도 값을 바꾸지 않는다.

**검증 결과** (`python scripts/verify_equivalence.py`, csi300 2018–2019):

```
[1] 표현식 10종(Qlib 거절 수식의 $close 폴백 포함) IC: 원본 vs fast 10/10 일치 (atol=1e-12)
    timing: original 16.9s → fast 8.6s
[2] 동일 seed 진화(pop=10, gens=2): 마지막 세대 10개 프로그램 수식·raw_fitness 완전 일치,
    _best_programs 3개 수식·fitness_ 완전 일치
    timing: original fit 48.7s → fast fit 13.3s  (×3.7)
ALL PASS — fast path is result-invariant
```

실행 방법 (저장소 루트에서):

```bash
/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python scripts/run_gplearn_fast.py \
    --start_time 2010-01-01 --end_time 2019-12-31 \
    --population_size 1000 --hall_of_fame 50 --n_components 10 --generations 5 \
    --market all --kernels 32
```

부수적으로 러너가 함께 해결하는 원본의 실행 차단 요소: `gplearn.py`의 `fit()` 누락, placeholder 데이터 경로 2곳, `backtest/__init__.py`가 import하는 `backtest/backtester.py` **부재**(동일 내용의 `Alphaagent/backtester.py`를 `sys.modules`에 사전 등록해 보완), `to_parquet` 엔진(pyarrow/fastparquet) 부재 → CSV+pickle로 저장.

남은 한계: 마지막 hall-of-fame 상관도 단계는 원본 `execute()` 경로를 그대로 쓰므로 `hall_of_fame`회의 개별 조회(50회 ≈ 9분)가 남아 있다. `n_jobs`는 반드시 1로 둔다(병렬성은 qlib `kernels`가 담당 — joblib 다중 프로세스 안에서 qlib의 내부 병렬이 중첩되면 daemonic process 오류).

---

## Q2. Slurm 제출 — 가능하며, 스크립트가 준비되어 있다

### 2.1 이 클러스터에서 쓸 수 있는 자원

| 항목 | 값 |
| --- | --- |
| 계정 / QoS | `uos` / `node10_cpu640_gpu12` |
| 한도 | walltime **최대 2일**, 동시 실행 10 job / 제출 20 job / 640 CPU |
| CPU 파티션 | `cpu1` 48코어×10노드(대체로 혼잡), `cpu2` 256코어×10노드(여유) |
| GPU | **불필요** — gplearn은 CPU(Qlib I/O + pandas)만 쓴다 |

gplearn 실행은 (a) 단일 노드에서 qlib `kernels`로 병렬화되는 단일 프로세스이고 (b) 대형 설정도 최적화 후 2일 한도 안에 들어오므로 Slurm 배치에 적합하다. 시드 여러 개를 **독립 job으로** 던지는 것이 남는 병렬화 축이다.

### 2.2 제출 방법

`alphagen/scripts/slurm_gp.sbatch`와 같은 관례를 따랐다: 헤더에 partition 없음(제출 시 `-p`), conda activate 대신 절대경로 python, 로그는 `out/slurm/%x-%j.log`.

```bash
cd /gpfs/home1/sku07891/00.hojin/AlphaEval        # out/slurm/ 이 존재해야 함

# 기본형: <start> <end> <pop> <gens> <hof> <ncomp> [seed=42] [market=all]
sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10

# 시드 5개를 독립 job으로 (QoS상 동시 10개까지)
for s in 0 1 2 3 4; do
  sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10 $s
done

# Random Baseline (= generations 1)
sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 1 50 10

# cpu1이 꽉 찼으면 cpu2로
sbatch -p cpu2 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10
```

모니터링:

```bash
squeue -u $USER                        # 대기/실행 상태
tail -f out/slurm/alphaeval-gp-<jobid>.log
scancel <jobid>                        # 취소
```

동작 방식: `--cpus-per-task=32`(헤더)로 코어를 할당받고, 러너가 `SLURM_CPUS_PER_TASK`를 읽어 qlib `kernels`를 자동으로 맞춘다. 로그 1행에 `host=... pop=... seed=...`가 찍히고, preflight(`import qlib, pandas`)가 통과해야 본 작업이 시작된다. 결과는 `out/gplearn_fast_<market>_seed<seed>_<jobid>.csv/.pkl`.

### 2.3 실측 소요 시간

| 설정 | 어디서 | 시간 |
| --- | --- | --- |
| 동등성 검증(pop=10, gens=2, csi300) | 로그인 노드, kernels=8 | 원본 fit 48.7s → fast fit 13.3s (**×3.7**) |
| 스모크(pop=50, gens=2, hof=20, **all**) | cpu1(n046), 32코어, job 883881 | **7분 55초** (원본 구조 추정 ~35–45분) |
| 대형(pop=1000, gens=5, hof=50, all) | cpu1/cpu2, 32코어 | **추정 2–6시간** (아래 외삽) — 2일 한도 대비 충분 |

스모크에서 확인된 상세 (job 883881):

- 100회 평가 요청 중 **유일 표현식 69개만 실제 조회** — 세대 1의 50개 중 24개가 memo 적중, 7개는 세대 내 중복. GP의 표현식 중복이 실제로 크다는 증거.
- chunk 4회 호출, 실패 폴백 0회. 32코어에서 **표현식당 ~1.7s** (kernels=8 로그인 노드의 7.8s 대비).
- 외삽: pop=1000×gens=5 → 유일 표현식 ≈ 1000 + 4×400 ≈ 2,600개 × 1.7s ≈ 74분 + hall-of-fame 50회 ≈ 5분. 세대가 깊어지면 수식이 복잡해져(예: `Skew` 포함 수식은 개당 30s+) 늦어질 수 있어 **2–6시간**으로 잡는 것이 안전하다.
- 참고: 같은 노드에서 원본 구조는 개체당 3회 조회 × memo 없음이므로 5,000회 × (3×1.7s~) ≈ 7시간+, kernels=8 환경이면 ~35시간.

### 2.4 원복(rollback)

이번 작업은 기존 파일을 수정하지 않았다. 다음 신규 파일을 지우면 완전 원복이다.

```
scripts/fast_eval.py  scripts/run_gplearn_fast.py  scripts/verify_equivalence.py
scripts/slurm_gplearn.sbatch  docs/PerformanceAndSlurm.md  out/
```
