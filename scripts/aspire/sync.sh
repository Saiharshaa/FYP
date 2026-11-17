#!/usr/bin/env bash
# Move code and run data between WSL (~/FYP) and ASPIRE 2A (~/FYP there).
# Uses the ssh host alias in ~/.ssh/config (default: aspire-via-jump).
#   bash scripts/aspire/sync.sh code              # push code (no .venv/.git/results)
#   bash scripts/aspire/sync.sh push-run <run>    # push results/<run>/ (e.g. a labelled corpus to verify)
#   bash scripts/aspire/sync.sh pull-run <run>    # pull results/<run>/log.jsonl (model outputs) back
# pull-run fetches only log.jsonl, so it never overwrites a corpus labelled in WSL.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST=${ASPIRE_HOST:-aspire-via-jump}
cmd=${1:?usage: sync.sh code|push-run <run>|pull-run <run>}
case "$cmd" in
  code)
    rsync -az --info=stats1 --exclude .venv --exclude .git --exclude results \
      --exclude logs --exclude '__pycache__' --exclude reports ./ "$HOST:FYP/" ;;
  push-run)
    run=${2:?run id}
    rsync -az --info=stats1 "results/$run/" "$HOST:FYP/results/$run/" ;;
  pull-run)
    run=${2:?run id}
    mkdir -p "results/$run"
    rsync -az --info=stats1 --backup --suffix=".bak-$(date +%Y%m%d%H%M)" \
      "$HOST:FYP/results/$run/log.jsonl" "results/$run/log.jsonl" ;;
  *) echo "unknown command: $cmd"; exit 2 ;;
esac
