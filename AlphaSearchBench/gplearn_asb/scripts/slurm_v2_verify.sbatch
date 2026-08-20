#!/bin/bash
#SBATCH --job-name=gp-v2-verify
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb/out/slurm/%x-%j.log
# [Vanilla GP v2 / Phase B 검증] 전체 스위트(legacy 무회귀 + v2 신규) + v2 smoke
set -uo pipefail
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/gplearn_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python

$PY -m pytest tests/ -q --tb=short -rE 2>&1 | tail -120
echo "PYTEST_DONE rc=${PIPESTATUS[0]}"

# v2 smoke 단독 실행 + 계약 검사 (qlib 재조회 부재 = "executing:" 0행)
rm -rf out/v2_smoke_verify
$PY -m gplearn_asb.cli mine --config configs/v2/smoke.yaml \
    --run-id v2_smoke_verify --out out/v2_smoke_verify > /tmp/v2smoke.log 2>&1
rc=$?
n_exec=$(grep -c "^executing: " /tmp/v2smoke.log || true)
tail -30 /tmp/v2smoke.log
echo "V2_SMOKE_DONE rc=$rc executing_lines=$n_exec"
$PY - <<'PYEOF'
import json, glob, pandas as pd
man = json.load(open(glob.glob("out/v2_smoke_verify/manifests/run_*.json")[0]))
pool = pd.read_csv("out/v2_smoke_verify/metrics/final_pool_v2_smoke_verify.csv")
assert man["gp_profile"] == "vanilla_v2-draft", man["gp_profile"]
assert man["label_tail_exclusion"] == 1, man.get("label_tail_exclusion")
assert pool["formula"].nunique() == len(pool)
print("V2_CONTRACT_OK profile=", man["gp_profile"],
      "gens=", man["gp_params"]["generations"],
      "pool_unique=", pool["formula"].nunique(), "/", len(pool))
PYEOF
echo "V2_VERIFY_ALL_DONE rc=$?"
