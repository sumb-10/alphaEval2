#!/bin/bash
#SBATCH --job-name=abp-chain
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# ablation mining(884717-9) 완료 → evaluate(allcand) 체인 제출 → 전체 eval 종료 대기
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
declare -A METHOD=( [884717]=gplearn_asb_ictstat [884718]=gplearn_asb_nsguard [884719]=gplearn_asb_fbfit )
declare -A RID=( [884717]=pilot_csi800_ictstat_42 [884718]=pilot_csi800_nsguard_42 [884719]=pilot_csi800_fbfit_42 )
pending="884717 884718 884719"
while [ -n "$pending" ]; do
  still=""
  for j in $pending; do
    st=$(sacct -j $j -X -n -o State 2>/dev/null | head -1 | tr -d ' ')
    case "$st" in
      COMPLETED)
        if grep -q "DONE rc=0" out/slurm/*-$j.log 2>/dev/null; then
          nj=$(sbatch -p cpu1 scripts/slurm_eval_one.sbatch ${RID[$j]} ${METHOD[$j]} | awk '{print $4}')
          echo "MINING_OK $j ${RID[$j]} -> eval $nj"
        else
          echo "MINING_BAD $j ${RID[$j]}"
        fi ;;
      FAILED|CANCELLED*|TIMEOUT|OUT_OF_MEMORY) echo "MINING_FAIL $j state=$st" ;;
      *) still="$still $j" ;;
    esac
  done
  pending=$(echo ${still# })
  [ -n "$pending" ] && sleep 120
done
until ! squeue -h -u sku07891 -o "%j" | grep -qE "asb-eval"; do sleep 180; done
echo "ALL_EVALS_FINISHED"
for l in $(ls -t out/slurm/asb-eval-*.log); do grep -H "EVAL_ONE_DONE" $l 2>/dev/null | tail -1; done | head -16
