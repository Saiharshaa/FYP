# Source me on ASPIRE 2A (login node or inside a PBS job).
# Paths and pins for model inference; candidate code is never executed here
# (labelling stays in WSL2, see README "Pipeline").
export FYP_PROJECT=${FYP_PROJECT:-personal-saiharsh}
export FYP_ENV=${FYP_ENV:-$HOME/envs/fyp-vllm}          # conda env (python 3.11 + vllm + this package)
export VLLM_VERSION=${VLLM_VERSION:-0.8.5}
export VERIFIER_CONFIG=${VERIFIER_CONFIG:-configs/aspire_a100.toml}   # concurrency for vLLM
# Big files (model weights) go to scratch, not the 50 GB home quota.
# Smoke test prints the real scratch path; override SCRATCH_DIR if it differs.
if [ -z "${SCRATCH_DIR:-}" ]; then
  for d in "/scratch/users/ntu/$USER" "/scratch/users/$USER" "/scratch/$USER"; do
    [ -d "$d" ] && SCRATCH_DIR=$d && break
  done
fi
export SCRATCH_DIR=${SCRATCH_DIR:-$HOME/scratch}
export HF_HOME=$SCRATCH_DIR/hf
# Models (decision 2026-11-18): 2x2 self/cross design, both bf16 on one A100-40GB.
#   short name -> Hugging Face id   (Llama is gated: accept the licence on HF first)
declare -A FYP_MODELS=(
  [q7b]=Qwen/Qwen2.5-Coder-7B-Instruct
  [l8b]=meta-llama/Llama-3.1-8B-Instruct
)
# Fallback if Llama access is not granted: [d7b]=deepseek-ai/deepseek-coder-6.7b-instruct
export FYP_MODEL_KEYS="${FYP_MODEL_KEYS:-q7b l8b}"
model_id() { echo "${FYP_MODELS[$1]:?unknown model key $1}"; }
# Model served by a job: MODEL_KEY (preferred) or MODEL_ID.
if [ -n "${MODEL_KEY:-}" ]; then MODEL_ID=$(model_id "$MODEL_KEY"); fi
export MODEL_ID=${MODEL_ID:-${FYP_MODELS[q7b]}}
_base=${MODEL_ID##*/}
export SERVED_NAME=${SERVED_NAME:-${_base,,}}
unset _base
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
