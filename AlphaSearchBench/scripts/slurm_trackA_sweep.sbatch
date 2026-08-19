#!/bin/bash
#SBATCH --job-name=asb-trackA-sweep
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/out/slurm-%x-%j.log
# [P-7 / ASB-P1.0] Track A 8구성(2 combiner × 2 rule × 2 cost) + Track B anchor
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
$PY scripts/protocol_sweep.py --tag trackA_p10_dev \
  --arms \
    LSQ_c15_raw=configs/examples/csi800_trackA_lsq_c15.yaml \
    LSQ_c15_sgn=configs/examples/csi800_trackA_lsq_c15.yaml#backtest.combiner=train_signed_equal \
    LSQ_c0_raw=configs/examples/csi800_trackA_lsq_c0.yaml \
    LSQ_c0_sgn=configs/examples/csi800_trackA_lsq_c0.yaml#backtest.combiner=train_signed_equal \
    LSK_c15_raw=configs/examples/csi800_trackA_lsk_c15.yaml \
    LSK_c15_sgn=configs/examples/csi800_trackA_lsk_c15.yaml#backtest.combiner=train_signed_equal \
    LSK_c0_raw=configs/examples/csi800_trackA_lsk_c0.yaml \
    LSK_c0_sgn=configs/examples/csi800_trackA_lsk_c0.yaml#backtest.combiner=train_signed_equal \
    ANCHOR=configs/examples/csi800_ref_qlib.yaml \
  --pools "gplearn_asb/out/pilot_csi800_*/metrics/final_pool_pilot_csi800_*.csv" \
          "AlphaAgent_asb/out/alphaagent_asb_expB_csi800/metrics/final_pool_*.csv" \
  2>&1 | grep -avE "backtest loop|it/s\]$"
rc=${PIPESTATUS[0]}
$PY scripts/deployment_profile.py --sweep out/protocol_sweep/trackA_p10_dev 2>&1 | tail -40
echo "TRACKA_SWEEP_DONE rc=$rc"
