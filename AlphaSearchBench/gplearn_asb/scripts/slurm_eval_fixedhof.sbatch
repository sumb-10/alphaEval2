#!/bin/bash
#SBATCH --job-name=asb-eval-fixedhof
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# fixedhof 파생 run 평가 — trajectory는 원본과 동일하므로 allcand 재계산 없이
# final_pool scope(csi800_example)로 pool/factor 지표만 산출.
set -uo pipefail
RID=${1:?run_id}; METHOD=${2:?method label}
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
SEED=$(echo "$RID" | grep -oE '_[0-9]+(_|$)' | tail -1 | tr -d '_')
$PY -m alphasearchbench evaluate \
    --config configs/examples/csi800_example.yaml \
    --input gplearn_asb/out/$RID/metrics/final_pool_$RID.csv \
    --trajectory gplearn_asb/out/$RID/trajectory/$RID.jsonl \
    --method $METHOD --seed-id $SEED \
    --out gplearn_asb/out/$RID/asb_eval 2>&1 | tail -3
echo "EVAL_ONE_DONE rc=${PIPESTATUS[0]} rid=$RID"
