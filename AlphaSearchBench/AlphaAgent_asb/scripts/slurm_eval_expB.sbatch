#!/bin/bash
#SBATCH --job-name=asb-eval-aa-expB
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/AlphaAgent_asb/out/slurm/%x-%j.log
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
RID=alphaagent_asb_expB_csi800
/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python -m alphasearchbench evaluate \
    --config configs/examples/csi800_allcand.yaml \
    --input AlphaAgent_asb/out/$RID/metrics/final_pool_$RID.csv \
    --trajectory AlphaAgent_asb/out/$RID/trajectory/$RID.jsonl \
    --method alphaagent_asb --seed-id 42 \
    --out AlphaAgent_asb/out/$RID/asb_eval 2>&1 | tail -6
echo "EVAL_ONE_DONE rc=${PIPESTATUS[0]} rid=$RID"
