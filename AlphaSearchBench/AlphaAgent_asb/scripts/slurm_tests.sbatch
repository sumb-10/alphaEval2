#!/bin/bash
#SBATCH --job-name=alphaagent-asb-tests
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/AlphaAgent_asb/out/slurm/%x-%j.log
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/AlphaAgent_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
$PY -m pytest tests/ -v 2>&1
echo "TESTS_DONE rc=$?"
