#!/bin/bash
#SBATCH --job-name=asb-eval-one
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# 사용법: sbatch scripts/slurm_eval_one.sbatch <RUN_ID> <METHOD_LABEL>
set -uo pipefail
RID=${1:?run_id}; METHOD=${2:?method label}
CFG=${3:-configs/examples/csi800_allcand.yaml}
OUTSUB=${4:-asb_eval}
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
# seed = run_id의 마지막 숫자 토큰 (…_fixedhof 같은 접미사 허용)
SEED=$(echo "$RID" | grep -oE '_[0-9]+(_|$)' | tail -1 | tr -d '_')
SEED=${SEED:-${RID##*_}}
$PY -m alphasearchbench evaluate \
    --config $CFG \
    --input gplearn_asb/out/$RID/metrics/final_pool_$RID.csv \
    --trajectory gplearn_asb/out/$RID/trajectory/$RID.jsonl \
    --method $METHOD --seed-id $SEED \
    --out gplearn_asb/out/$RID/$OUTSUB 2>&1 | tail -3
echo "EVAL_ONE_DONE rc=${PIPESTATUS[0]} rid=$RID"
