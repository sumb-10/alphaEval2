#!/bin/bash
#SBATCH --job-name=e4-chain
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# [E4] E1/E2 마이닝 완료 대기 → fixedhof repool → fb 계열 4-arm 스윕
set -uo pipefail
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb

until ! squeue -h -j 888251,888252,888254 2>/dev/null | grep -q .; do sleep 120; done
for j in 888250 888251 888252 888253 888254; do
  st=$(sacct -j $j -X -n -o State | head -1 | tr -d ' ')
  echo "MINING $j state=$st"
done

$PY scripts/repool_fixed_hof.py \
    --runs out/pilot_csi800_fbfit_0 out/pilot_csi800_fbfit_1 \
           out/pilot_csi800_fbfit_2 out/pilot_csi800_fbfit_3 \
           out/pilot_csi800_fbfitguard_42 2>&1 | tail -15
echo "REPOOL_DONE rc=$?"

cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
$PY scripts/protocol_sweep.py --tag ws_b_e4 \
    --arms A1=configs/examples/csi800_ref.yaml \
           A2=configs/examples/csi800_ref_lowturn.yaml \
           A3=configs/examples/csi800_ref_qlib.yaml \
           A4=configs/examples/csi800_ref_legacy.yaml \
    --pools "gplearn_asb/out/pilot_csi800_fbfit*/metrics/final_pool_pilot_csi800_fbfit*.csv" \
    2>&1 | grep -avE "backtest loop|it/s\]$" | tail -50
echo "E4_DONE rc=${PIPESTATUS[0]}"
