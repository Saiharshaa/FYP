#!/usr/bin/env bash
# Pilot of the execution-grounded strategies (c) self-tests and (d) reference
# on the pilot corpus, with the same local 1.5B verifier (self-verification).
# 40 problems x 3 seeds x 2 strategies = 240 model calls (per problem, not per
# candidate), then sandboxed execution against all 400 candidates.
# Resumable; run detached with a keep-alive, as for phase 2:
#   cd ~/FYP && bash scripts/run_pilot_exec.sh
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
. scripts/pilot_env.sh

CORPUS=pilot-q15b
VERIFY=verify-pilot-q15b
say() { echo "[$(date '+%H:%M:%S')] $*"; }
fresh_server() {   # llama-server grew to 4.3 GB over a 7 h run (2026-11-18)
  docker restart fyp-llm >/dev/null 2>&1 || true
  bash scripts/serve_local_llm.sh ensure
  for _ in $(seq 1 60); do curl -sf -m 5 http://127.0.0.1:8080/health >/dev/null && return; sleep 2; done
  say "model server not healthy"; exit 1
}
verify() { python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" "$@"; }
report() { python -m verifier.analysis.report --run-id "$VERIFY" --out reports/pilot-q15b >/dev/null
           say "report written: reports/pilot-q15b/report.md"; }

for s in self-tests reference; do
  for seed in 0 1 2; do
    fresh_server
    say "verify $s seed $seed"; verify --strategy "$s" --seeds "$seed"
  done
done
docker stop fyp-llm >/dev/null 2>&1 || true   # free memory for the sandbox
say "execute tests / reference against candidates"
python -m verifier.harness.exec_verdicts --run-id "$VERIFY"
report
say "exec pilot complete"
