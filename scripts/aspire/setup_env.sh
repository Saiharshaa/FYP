#!/usr/bin/env bash
# One-time setup on the ASPIRE 2A LOGIN node (it has internet; compute nodes
# may not). Downloads only, no computation:
#   cd ~/FYP && bash scripts/aspire/setup_env.sh
# Sizes: conda env with vllm + torch ~8-10 GB in $HOME; model ~15 GB in scratch.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/aspire/env.sh
say() { echo "[$(date '+%H:%M:%S')] $*"; }
command -v conda >/dev/null || { echo "conda not found: check 'module avail miniforge'"; exit 1; }

if [ ! -d "$FYP_ENV" ]; then
  say "create conda env $FYP_ENV (python 3.11)"
  conda create -y -p "$FYP_ENV" python=3.11
fi
conda activate "$FYP_ENV"
say "install vllm==$VLLM_VERSION and this package"
pip install --upgrade pip
pip install "vllm==$VLLM_VERSION"
pip install -e .            # pins evalplus to the same commit as WSL (pyproject)

say "cache HumanEval+ for offline compute nodes"
python -c "from evalplus.data import get_human_eval_plus as g; print(len(g()), 'problems cached')"

say "download $MODEL_ID -> $MODEL_DIR"
mkdir -p "$MODEL_DIR"
huggingface-cli download "$MODEL_ID" --local-dir "$MODEL_DIR"

python - <<'EOF'
import vllm, torch, evalplus
print("vllm", vllm.__version__, "| torch", torch.__version__, "| cuda build", torch.version.cuda)
EOF
say "setup done. Next: qsub scripts/aspire/gpu_smoke.pbs, then scripts/aspire/infer.pbs"
