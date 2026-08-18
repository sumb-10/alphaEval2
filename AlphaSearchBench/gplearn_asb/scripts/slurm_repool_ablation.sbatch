#!/bin/bash
#SBATCH --job-name=gplearn-repool-abl
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python scripts/repool_fixed_hof.py \
    --runs out/pilot_csi800_ictstat_42 out/pilot_csi800_nsguard_42 out/pilot_csi800_fbfit_42 2>&1
echo "REPOOL_DONE rc=$?"
# 완료 즉시 fixedhof 평가 3건 제출 (final_pool scope — 저비용)
for r in ictstat nsguard fbfit; do
  sbatch -p cpu1 scripts/slurm_eval_fixedhof.sbatch pilot_csi800_${r}_42_fixedhof gplearn_asb_${r}_fixedhof
done
