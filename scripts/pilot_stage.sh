#!/usr/bin/env bash
# Run one pilot stage in the foreground with the local model server up:
#   scripts/pilot_stage.sh python -m verifier.corpus.build generate --run-id pilot-q15b --sample
# Keep this attached to a wsl.exe session for the whole stage: WSL2 stops the
# VM (and the server container) once no Windows-side client is attached.
# Every stage resumes from its log, so an interrupted stage is simply re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
. scripts/pilot_env.sh
bash scripts/serve_local_llm.sh ensure
exec "$@"
