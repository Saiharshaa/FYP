#!/usr/bin/env bash
# Pilot phase 2 (decided 2026-10-07, after `direct` answered CORRECT 400/400):
#   - skip direct seeds 1-2 (same answer every time at T=0.7)
#   - run the answer-order control `direct-swapped` (seed 0)
#   - then reason seeds 1-2 for the majority vote (e)
# Waits for run_pilot.sh to finish reason seed 0, stops it before it starts
# direct seeds 1-2, then continues. Never re-labels the corpus. Resumable:
#   cd ~/FYP && bash scripts/run_pilot_phase2.sh
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
. scripts/pilot_env.sh

CORPUS=pilot-q15b
VERIFY=verify-pilot-q15b
N=$(python -c "import json; print(sum(1 for _ in open('results/$CORPUS/corpus.jsonl')))")
say() { echo "[$(date '+%H:%M:%S')] $*"; }
calls() {  # calls <strategy> <seed>
  python - "$1" "$2" <<'EOF'
import json, sys
from pathlib import Path
p = Path("results/verify-pilot-q15b/log.jsonl")
n = 0
if p.exists():
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            n += r["strategy"] == sys.argv[1] and r["seed"] == int(sys.argv[2])
print(n)
EOF
}
report() { python -m verifier.analysis.report --run-id "$VERIFY" --out reports/pilot-q15b >/dev/null
           say "report written: reports/pilot-q15b/report.md"; }
verify() { python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" "$@"; }

say "phase 2: waiting for reason seed 0 ($(calls reason 0)/$N)"
while [ "$(calls reason 0)" -lt "$N" ] && pgrep -f '^bash scripts/run_pilot\.sh' >/dev/null; do
  sleep 60
done
pkill -f '^bash scripts/run_pilot\.sh' && say "stopped run_pilot.sh" || true
pkill -f "verifier.harness.verify --corpus $CORPUS" || true
pkill -f "verifier.analysis.report --run-id $VERIFY" || true
sleep 2
bash scripts/serve_local_llm.sh ensure

say "verify reason seed 0 (completes any remainder)"; verify --strategy reason --seeds 0
report
say "verify direct-swapped seed 0 (answer-order control)"; verify --strategy direct-swapped --seeds 0
report
say "verify reason seeds 0-2 (majority vote)"; verify --strategy reason --seeds 0 1 2
report
say "phase 2 complete"
