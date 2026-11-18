#!/usr/bin/env bash
# WSL, between phase A and phase B: fetch each generated corpus from ASPIRE,
# label it locally (executes candidate code, so never on ASPIRE), then push
# the labelled corpus back for verification.
#   bash scripts/aspire/label_corpora.sh            # all of: q7b l8b
#   bash scripts/aspire/label_corpora.sh q7b        # just one
set -euo pipefail
cd "$(dirname "$0")/../.."
. .venv/bin/activate
unset VERIFIER_CONFIG                     # labelling uses configs/default.toml
keys=${*:-q7b l8b}
for g in $keys; do
  run=gen-$g
  echo "== $run: pull"
  bash scripts/aspire/sync.sh pull-run "$run"
  echo "== $run: label (serial; see [labelling] in configs/default.toml)"
  python -m verifier.corpus.build label --run-id "$run"
  echo "== $run: push labelled corpus"
  bash scripts/aspire/sync.sh push-run "$run"
done
