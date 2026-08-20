#!/bin/bash
#SBATCH --job-name=gp-v2-c2a3
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --partition=cpu1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# [C-2a.3] bloat-control screening 1 run — $1 = configs/v2/c2a3/*.yaml
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
echo "C2A3_CONFIG=$1"
$PY -m gplearn_asb.cli mine --config "$1"
echo "C2A3_DONE rc=$?"
