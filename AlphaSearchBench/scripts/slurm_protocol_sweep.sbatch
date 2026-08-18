#!/bin/bash
#SBATCH --job-name=asb-protocol-sweep
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=06:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/out/slurm-%x-%j.log
# [E3] 프로토콜 4-arm 스윕. 인자: <tag> [추가 pool glob ...]
set -uo pipefail
TAG=${1:?tag}; shift || true
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python scripts/protocol_sweep.py \
    --tag "$TAG" \
    --arms A1=configs/examples/csi800_ref.yaml \
           A2=configs/examples/csi800_ref_lowturn.yaml \
           A3=configs/examples/csi800_ref_qlib.yaml \
           A4=configs/examples/csi800_ref_legacy.yaml \
    --pools "gplearn_asb/out/pilot_csi800_*/metrics/final_pool_pilot_csi800_*.csv" \
            "AlphaAgent_asb/out/alphaagent_asb_expB_csi800/metrics/final_pool_*.csv" \
            "$@" 2>&1 | grep -avE "backtest loop|it/s\]$"
echo "SWEEP_DONE rc=${PIPESTATUS[0]} tag=$TAG"
