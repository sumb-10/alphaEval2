#!/bin/bash
#SBATCH --job-name=e5-submitter
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# [E5] 제출 상한(AssocMaxSubmitJobLimit) 우회 — 슬롯이 비는 대로 잔여 18건 제출
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
REF=configs/examples/csi800_ref.yaml
FP=configs/examples/csi800_ref_fp.yaml

submit_throttled () {  # rid method cfg timelimit
  until [ "$(squeue -h -u sku07891 | wc -l)" -lt 19 ]; do sleep 60; done
  until sbatch -p cpu1 --time=$4 scripts/slurm_eval_one.sbatch "$1" "$2" "$3" asb_eval_ref; do
    sleep 120
  done
}

for r in off_0 off_1 off_2 off_3 off_42 \
         strict_0 strict_1 strict_2 strict_3 strict_42 hard_42 \
         netsharpe_0 netsharpe_1 netsharpe_2 ictstat_42 nsguard_42 \
         fbfit_42 fbfit_0 fbfit_1 fbfit_2 fbfit_3 fbfitguard_42; do
  m=$(echo $r | sed 's/_[0-9]*$//')
  submit_throttled pilot_csi800_$r gplearn_asb_$m $REF 10:00:00
done
for r in strict_0 strict_1 strict_2 strict_3 strict_42 \
         netsharpe_0 netsharpe_1 netsharpe_2 ictstat_42 nsguard_42 \
         fbfit_42 fbfit_0 fbfit_1 fbfit_2 fbfit_3 fbfitguard_42; do
  m=$(echo $r | sed 's/_[0-9]*$//')
  submit_throttled pilot_csi800_${r}_fixedhof gplearn_asb_${m}_fixedhof $FP 03:00:00
done
echo "E5_ALL_SUBMITTED"
# 전 평가 종료 대기 (자기 자신 제외 = 1)
until [ "$(squeue -h -u sku07891 | wc -l)" -le 1 ]; do sleep 300; done
echo "E5_ALL_FINISHED"
n_ok=$(ls -d out/pilot_csi800_*/asb_eval_ref/manifests/run_*.json 2>/dev/null | wc -l)
echo "manifests: $n_ok / 38"
