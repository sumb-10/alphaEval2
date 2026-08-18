#!/bin/bash
#SBATCH --job-name=gplearn-repool
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# [A-소급] strict 5 seeds + netsharpe 3 seeds에 fixed-HOF repool
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
$PY scripts/repool_fixed_hof.py \
    --runs out/pilot_csi800_strict_0 out/pilot_csi800_strict_1 \
           out/pilot_csi800_strict_2 out/pilot_csi800_strict_3 \
           out/pilot_csi800_strict_42 \
           out/pilot_csi800_netsharpe_0 out/pilot_csi800_netsharpe_1 \
           out/pilot_csi800_netsharpe_2 2>&1
echo "REPOOL_DONE rc=$?"
