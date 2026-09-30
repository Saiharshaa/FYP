#!/usr/bin/env bash
# Whole pilot, in order; every stage resumes from its log, so just re-run
# after any interruption. Run it in a WSL terminal that stays open (WSL2 stops
# the VM, and the model server, when no Windows-side client is attached):
#   cd ~/FYP && bash scripts/run_pilot.sh
# Order puts seed 0 of both strategies first so a first report exists early.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
. scripts/pilot_env.sh
bash scripts/serve_local_llm.sh ensure

CORPUS=pilot-q15b
VERIFY=verify-pilot-q15b
say() { echo "[$(date '+%H:%M:%S')] $*"; }

say "generate";  python -m verifier.corpus.build generate --run-id "$CORPUS" --backend openai --sample
say "label";     python -m verifier.corpus.build label --run-id "$CORPUS"

# Guard from the plan: stop on an extreme class balance instead of silently
# verifying a corpus that is almost all correct or all incorrect.
python - "$CORPUS" <<'EOF'
import json, os, sys
m = json.load(open(f"results/{sys.argv[1]}/corpus_meta.json"))
rate = m["n_correct"] / m["n_candidates"]
print(f"corpus: {m['n_correct']}/{m['n_candidates']} correct ({rate:.1%}); "
      f"failures {m['failure_categories']}")
if not 0.10 <= rate <= 0.90 and os.environ.get("FORCE") != "1":
    sys.exit("class balance outside 10-90%: review before verifying (FORCE=1 to continue)")
EOF

report() { python -m verifier.analysis.report --run-id "$VERIFY" --out reports/pilot-q15b >/dev/null
           say "report written: reports/pilot-q15b/report.md"; }

say "verify direct seed 0"; python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" --strategy direct --seeds 0
say "verify reason seed 0"; python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" --strategy reason --seeds 0
report
say "verify direct seeds 0-2"; python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" --strategy direct --seeds 0 1 2
report
say "verify reason seeds 0-2"; python -m verifier.harness.verify --corpus "$CORPUS" --run-id "$VERIFY" --strategy reason --seeds 0 1 2
report
say "pilot complete"
