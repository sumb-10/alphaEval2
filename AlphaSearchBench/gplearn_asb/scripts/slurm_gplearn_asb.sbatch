#!/bin/bash
#SBATCH --job-name=gplearn-asb
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log

# 사용법: sbatch [-p cpu1] scripts/slurm_gplearn_asb.sbatch <config> <mode> [seed] [run_id]
set -euo pipefail
CONFIG=${1:?config yaml}
MODE=${2:?off|hard_penalty|strict_penalty}
SEED=${3:-42}
RUN_ID=${4:-gplearn_asb_${MODE}_seed${SEED}_${SLURM_JOB_ID}}

cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
mkdir -p out/slurm
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

echo "host=$(hostname) config=$CONFIG mode=$MODE seed=$SEED run_id=$RUN_ID cpus=${SLURM_CPUS_PER_TASK}"
$PY -m gplearn_asb.cli mine --config "$CONFIG" --mode "$MODE" --seed "$SEED" --run-id "$RUN_ID"
echo "DONE rc=$?"
