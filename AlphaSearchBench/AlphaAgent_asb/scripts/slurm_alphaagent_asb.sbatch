#!/bin/bash
#SBATCH --job-name=alphaagent-asb
#SBATCH --account=uos
#SBATCH --qos=node10_cpu640_gpu12
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=06:00:00
#SBATCH --output=/gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/AlphaAgent_asb/out/slurm/%x-%j.log

# 사용법: sbatch [-p cpu1] scripts/slurm_alphaagent_asb.sbatch <config> <fake|live|replay:PATH> [run_id]
set -euo pipefail
CONFIG=${1:?config yaml}
MODE=${2:?fake|live|replay:PATH}
RUN_ID=${3:-alphaagent_asb_${SLURM_JOB_ID}}
cd /gpfs/home1/sku07891/00.hojin/AlphaEval/AlphaSearchBench/AlphaAgent_asb
PY=/home1/sku07891/miniconda3/envs/AlphaEval38/bin/python
# live 모드용 API key: ~/.openai.env (chmod 600, `export OPENAI_API_KEY=...` 한 줄)
[ -f "$HOME/.openai.env" ] && source "$HOME/.openai.env"
ARGS=(mine --config "$CONFIG" --run-id "$RUN_ID")
case "$MODE" in
  fake) ARGS+=(--fake);;
  replay:*) ARGS+=(--replay "${MODE#replay:}");;
  live) : ;;   # OPENAI_API_KEY는 환경에서 (사용자 승인 후)
esac
echo "host=$(hostname) config=$CONFIG mode=$MODE run_id=$RUN_ID"
$PY -m alphaagent_asb.cli "${ARGS[@]}"
echo "DONE rc=$?"
