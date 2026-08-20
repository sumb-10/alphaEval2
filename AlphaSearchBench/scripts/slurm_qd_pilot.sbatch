#!/bin/bash
#SBATCH --job-name=qd-desc-pilot
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --partition=cpu1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:30:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/out/slurm/%x-%j.log
# [QD 설계] descriptor 후보 실측 파일럿 — scripts/qd_descriptor_pilot.py
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python scripts/qd_descriptor_pilot.py
echo "QD_PILOT_DONE rc=$?"
