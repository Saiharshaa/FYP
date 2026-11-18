#!/usr/bin/env bash
# Submit the full sweep on ASPIRE 2A (run on the login node, from ~/FYP).
# Design (decision 2026-11-18): 2x2 self/cross verification.
#   generators = verifiers = $FYP_MODEL_KEYS (default: q7b l8b, see env.sh)
#
#   Phase A  bash scripts/aspire/submit.sh generate   -> results/gen-<g>/log.jsonl
#   (WSL)    bash scripts/aspire/label_corpora.sh     -> pull, label, push corpora
#   Phase B  bash scripts/aspire/submit.sh verify     -> results/verify-gen-<g>-by-<v>/
#
# One job per model in phase A and per (corpus, verifier) pair in phase B, so
# each model loads once. Resubmitting is safe: every stage resumes from its log.
# DRY_RUN=1 prints the qsub commands instead of submitting.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/aspire/env.sh
# Verification passes per pair: (a) direct, answer-order control, (b) reason;
# 3 seeds each; (e) = vote over reason seeds, computed by the report.
VERIFY_PASSES=${VERIFY_PASSES:-"direct:0 1 2;direct-swapped:0 1 2;reason:0 1 2"}

run() { if [ "${DRY_RUN:-0}" = 1 ]; then echo "qsub $*"; else qsub "$@"; fi; }

case "${1:-}" in
  generate)
    for g in $FYP_MODEL_KEYS; do
      run -N "gen-$g" -v "MODEL_KEY=$g,STAGE=verifier.corpus.build generate --run-id gen-$g --backend openai" \
        scripts/aspire/infer.pbs
    done ;;
  verify)
    for g in $FYP_MODEL_KEYS; do
      [ -f "results/gen-$g/corpus.jsonl" ] || {
        echo "results/gen-$g/corpus.jsonl missing: label it in WSL and push it first"; exit 1; }
    done
    for g in $FYP_MODEL_KEYS; do
      for v in $FYP_MODEL_KEYS; do
        stages=()
        IFS=';' read -ra passes <<< "$VERIFY_PASSES"
        for p in "${passes[@]}"; do
          stages+=("verifier.harness.verify --corpus gen-$g --run-id verify-gen-$g-by-$v --strategy ${p%%:*} --seeds ${p#*:}")
        done
        joined=$(IFS='|'; echo "${stages[*]}")
        run -N "ver-$g-$v" -v "MODEL_KEY=$v,STAGE=$joined" scripts/aspire/infer.pbs
      done
    done ;;
  *) echo "usage: submit.sh generate|verify"; exit 2 ;;
esac
