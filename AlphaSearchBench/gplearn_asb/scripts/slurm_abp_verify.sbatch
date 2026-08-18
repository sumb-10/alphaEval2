#!/bin/bash
#SBATCH --job-name=gplearn-abp-verify
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# A+B+P 검증: 전체 pytest(883881 재현 포함) + 신기능 smoke 3종
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

$PY -m pytest tests/ -v 2>&1
rc_tests=$?
echo "PYTEST_DONE rc=$rc_tests"

run_smoke () {
  local cfg=$1 rid=$2
  rm -rf out/$rid
  $PY -m gplearn_asb.cli mine --config configs/$cfg --run-id $rid --out out/$rid 2>&1 | tail -5
  echo "SMOKE_DONE rc=$? rid=$rid"
}
run_smoke smoke_fixedhof.yaml smoke_fixedhof_42
run_smoke smoke_ictstat.yaml  smoke_ictstat_42
run_smoke smoke_fbfit.yaml    smoke_fbfit_42

# fixed-HOF smoke 검증: pool unique == pool size + hof 컬럼 존재
$PY - <<'PYEOF'
import pandas as pd
df = pd.read_csv("out/smoke_fixedhof_42/metrics/final_pool_smoke_fixedhof_42.csv")
assert df["formula"].nunique() == len(df), (df["formula"].nunique(), len(df))
assert "hof_mode" in df.columns and (df["hof_mode"] == "fixed").all()
print("FIXEDHOF_POOL_OK unique=", len(df), "cols_ok")
t = pd.read_json("out/smoke_ictstat_42/trajectory/smoke_ictstat_42.jsonl", lines=True)
assert (t["fitness_metric"] == "ic_tstat").all()
valid = t[t["validity_pass"] == True]
assert (valid["raw_fitness"] >= 0).all()
print("ICTSTAT_TRAJ_OK n_valid=", len(valid))
t2 = pd.read_json("out/smoke_fbfit_42/trajectory/smoke_fbfit_42.jsonl", lines=True)
assert (t2["fitness_metric"] == "fb_fitness").all()
print("FBFIT_TRAJ_OK")
PYEOF
echo "VERIFY_ALL_DONE rc=$?"
