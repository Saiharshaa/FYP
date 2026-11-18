#!/usr/bin/env bash
# One-time setup on the ASPIRE 2A LOGIN node (it has internet; compute nodes
# may not). Downloads only, no computation:
#   cd ~/FYP && bash scripts/aspire/setup_env.sh
# Sizes: conda env with vllm + torch ~8-10 GB in $HOME; ~15-16 GB per model in scratch.
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

failed=()
for key in $FYP_MODEL_KEYS; do
  id=$(model_id "$key"); dir=$SCRATCH_DIR/models/${id//\//__}
  say "download [$key] $id -> $dir"
  mkdir -p "$dir"
  if ! huggingface-cli download "$id" --local-dir "$dir" --exclude 'original/*'; then
    failed+=("$key")
    echo "  !! $id failed. If gated (Llama): accept the licence at https://huggingface.co/$id,"
    echo "     then 'huggingface-cli login' here with a read token, and re-run this script."
  fi
done

python - <<'EOF'
import vllm, torch, evalplus
print("vllm", vllm.__version__, "| torch", torch.__version__, "| cuda build", torch.version.cuda)
EOF
if [ ${#failed[@]} -gt 0 ]; then say "setup incomplete: models not downloaded: ${failed[*]}"; exit 1; fi
say "setup done. Next: qsub scripts/aspire/gpu_smoke.pbs, then bash scripts/aspire/submit.sh generate"
