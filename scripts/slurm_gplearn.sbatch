#!/bin/bash
#SBATCH --job-name=alphaeval-gp
#SBATCH --cpus-per-task=32
#SBATCH --output=out/slurm/%x-%j.log
#
# AlphaEval gplearn (fast runner) — one mining run per invocation.
#
#   sbatch -p cpu1 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10
#   sbatch -p cpu2 scripts/slurm_gplearn.sbatch 2010-01-01 2019-12-31 1000 5 50 10 7 csi300
#
# args: <start> <end> <pop> <gens> <hof> <ncomp> [seed=42] [market=all]
#
# * partition은 제출 시 -p 로 지정 (cpu1: 48c/노드, cpu2: 256c/노드; GPU 불필요)
# * out/slurm/ 은 제출 전에 존재해야 함 (Slurm이 로그 파일을 먼저 연다)
# * qlib kernels 는 SLURM_CPUS_PER_TASK 를 자동으로 따라감
# * QoS(node10_cpu640_gpu12): 최대 walltime 2일, 동시 10 job / 640 CPU

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"
mkdir -p out/slurm out

START="${1:?usage: sbatch -p <cpu1|cpu2> scripts/slurm_gplearn.sbatch <start> <end> <pop> <gens> <hof> <ncomp> [seed] [market]}"
END="${2:?missing <end>}"
POP="${3:?missing <pop>}"
GENS="${4:?missing <gens>}"
HOF="${5:?missing <hof>}"
NCOMP="${6:?missing <ncomp>}"
SEED="${7:-42}"
MARKET="${8:-all}"

PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

echo "host=$(hostname) start=${START} end=${END} pop=${POP} gens=${GENS} hof=${HOF} ncomp=${NCOMP} seed=${SEED} market=${MARKET} cpus=${SLURM_CPUS_PER_TASK:-?}"
$PY -c "import qlib, pandas, numpy, sklearn; print('preflight ok: qlib', qlib.__version__)"

$PY scripts/run_gplearn_fast.py \
    --start_time "${START}" \
    --end_time "${END}" \
    --population_size "${POP}" \
    --generations "${GENS}" \
    --hall_of_fame "${HOF}" \
    --n_components "${NCOMP}" \
    --seed "${SEED}" \
    --market "${MARKET}" \
    --out "out/gplearn_fast_${MARKET}_seed${SEED}_${SLURM_JOB_ID:-local}"
