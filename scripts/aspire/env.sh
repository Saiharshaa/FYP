# Source me on ASPIRE 2A (login node or inside a PBS job).
# Paths and pins for model inference; candidate code is never executed here
# (labelling stays in WSL2, see README "Pipeline").
export FYP_PROJECT=${FYP_PROJECT:-personal-saiharsh}
export FYP_ENV=${FYP_ENV:-$HOME/envs/fyp-vllm}          # conda env (python 3.11 + vllm + this package)
export VLLM_VERSION=${VLLM_VERSION:-0.8.5}
# Big files (model weights) go to scratch, not the 50 GB home quota.
# Smoke test prints the real scratch path; override SCRATCH_DIR if it differs.
if [ -z "${SCRATCH_DIR:-}" ]; then
  for d in "/scratch/users/ntu/$USER" "/scratch/users/$USER" "/scratch/$USER"; do
    [ -d "$d" ] && SCRATCH_DIR=$d && break
  done
fi
export SCRATCH_DIR=${SCRATCH_DIR:-$HOME/scratch}
export HF_HOME=$SCRATCH_DIR/hf
# Model under test (proposal, not yet decided): Qwen2.5-Coder-7B-Instruct, bf16 (~15 GB),
# fits one A100-40GB. Change MODEL_ID/SERVED_NAME for other models.
export MODEL_ID=${MODEL_ID:-Qwen/Qwen2.5-Coder-7B-Instruct}
export SERVED_NAME=${SERVED_NAME:-qwen2.5-coder-7b-instruct}
export MODEL_DIR=${MODEL_DIR:-$SCRATCH_DIR/models/${MODEL_ID//\//__}}

# conda's activate scripts reference unset variables; relax `set -u` around them.
case $- in *u*) _fyp_u=1; set +u;; *) _fyp_u=0;; esac
module load miniforge3 >/dev/null 2>&1 || true
if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  if [ -d "$FYP_ENV" ]; then conda activate "$FYP_ENV"; fi
fi
[ "$_fyp_u" = 1 ] && set -u
unset _fyp_u
