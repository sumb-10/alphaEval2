#!/bin/bash
#SBATCH --job-name=gplearn-asb-reverify
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

echo "== (a) two-pass Div-formula 값 확인 =="
$PY - <<'PYEOF'
import os, sys
PKG=os.path.abspath("."); sys.path[:0]=[PKG, os.path.dirname(PKG), os.path.dirname(os.path.dirname(PKG))]
from gplearn_asb.config import load_config
from alphasearchbench.data.qlib_bootstrap import bootstrap_qlib
cfg = load_config(overrides={"market":"csi800","search":{"start_date":"2010-01-01","end_date":"2019-12-31"},
                             "gp":{"population_size":1,"generations":1}})
bootstrap_qlib(cfg["dataset.provider_uri"], cfg["dataset.region"], 8)
from gplearn_asb.evaluator import MiningEvaluator
ev = MiningEvaluator(cfg)
for f in ["Rsquare(Std(Var($factor, 6), 30), 5)",
          "Div(Less(Power($high, $change), Less(Rsquare(Std(Var($factor, 6), 30), 5), Power($high, $change))), Rsquare(Std(Var($factor, 6), 30), 5))"]:
    d = ev.diagnose(f)
    print(f"{f[:45]}... signed={d['signed_train_IC']:+.6f} n_obs={d['n_ic_obs']}")
PYEOF

echo "== (b) 883881 재현 (two-pass) =="
rm -rf out/replicate_883881_off
$PY -m gplearn_asb.cli mine --config configs/experiments/replicate_883881.yaml 2>&1 | tail -8
$PY - <<'PYEOF'
import pandas as pd, numpy as np
a = pd.read_csv('../../out/gplearn_fast_all_seed42_883881.csv')
b = pd.read_csv('out/replicate_883881_off/metrics/final_pool_replicate_883881_off.csv')
same = list(a.formula)==list(b.formula)
print('REPLICATION formula 목록 동일:', same)
if same: print('REPLICATION IC max diff:', np.abs(a.IC.values-b.IC.values).max())
PYEOF

echo "== (c) 전체 테스트 =="
$PY -m pytest tests/ -q 2>&1 | tail -4
echo "REVERIFY_DONE rc=$?"
