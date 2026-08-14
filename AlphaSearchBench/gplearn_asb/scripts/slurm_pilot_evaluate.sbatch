#!/bin/bash
#SBATCH --job-name=pilot-asb-eval
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
for ARM in off hard strict; do
  RID=pilot_csi800_${ARM}_42
  echo "== evaluate $RID =="
  $PY -m alphasearchbench evaluate \
      --config configs/examples/csi800_example.yaml \
      --input gplearn_asb/out/$RID/metrics/final_pool_$RID.csv \
      --trajectory gplearn_asb/out/$RID/trajectory/$RID.jsonl \
      --method gplearn_asb_$ARM --seed-id 42 \
      --out gplearn_asb/out/$RID/asb_eval 2>&1 | tail -4
done
echo "EVAL_ALL_DONE"
