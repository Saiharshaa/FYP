#!/usr/bin/env bash
# Read-only progress of the pilot (safe to run in a second window any time):
#   bash scripts/pilot_status.sh
cd "$(dirname "$0")/.."
.venv/bin/python - <<'EOF'
import json
from collections import Counter
from pathlib import Path

R = Path("results")
def lines(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

gen = lines(R / "pilot-q15b" / "log.jsonl")
target = 10 * len(json.loads((R / "pilot-q15b" / "problems.json").read_text())) \
    if (R / "pilot-q15b" / "problems.json").exists() else 400
print(f"generate : {len(gen)}/{target}")

meta = R / "pilot-q15b" / "corpus_meta.json"
if meta.exists():
    m = json.loads(meta.read_text())
    print(f"label    : done, {m['n_correct']}/{m['n_candidates']} correct "
          f"({m['n_correct'] / m['n_candidates']:.1%}); failures {m['failure_categories']}")
else:
    print("label    : not yet")

ver = lines(R / "verify-pilot-q15b" / "log.jsonl")
counts = Counter((r["strategy"], r["seed"]) for r in ver)
for (s, seed), n in sorted(counts.items()):
    nv = sum(1 for r in ver if r["strategy"] == s and r["seed"] == seed and r["verdict"] is None)
    print(f"verify   : {s:<6} seed {seed}: {n}/{target}  (no verdict: {nv})")
if not counts:
    print("verify   : not yet")

rep = Path("reports/pilot-q15b/report.md")
print(f"report   : {'reports/pilot-q15b/report.md' if rep.exists() else 'not yet'}")
EOF
[ -f results/pilot-run.out ] && echo "last log : $(grep -E '^\[' results/pilot-run.out | tail -1)"
