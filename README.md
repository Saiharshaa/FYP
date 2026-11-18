# FYP — Verification Reliability in Multi-Agent Code Generation

NTU CCDS Final Year Project CCDS26-0044 (SC4079), AY2026/27.
Supervisor: A/P Chee Wei Tan.

**Research question.** Can an agent determine whether generated code is correct
without access to ground truth, and does the reliability of that judgement
determine the effectiveness of collaborative algorithm design?

The project treats the verifier (critic) as the object of study: each
verification strategy's binary verdict on a candidate solution is scored against
a ground-truth label obtained by executing the candidate against the
strengthened HumanEval+ test suites from [EvalPlus](https://github.com/evalplus/evalplus).

Full plan: [`docs/project_plan.md`](docs/project_plan.md).

## Layout

```
src/verifier/
  corpus/      ground-truth labelling via EvalPlus (HumanEval+); candidate
               generation + labelling pipeline (build.py)
  sandbox/     resource-limited execution of untrusted code (Docker / rlimit subprocess)
  harness/     model client, run logging, checkpoint/resume, verify runner
  strategies/  verification strategies: (a) direct, (b) reason-then-judge
  analysis/    confusion-matrix metrics and report (FAR/FRR/MCC, bootstrap CIs)
configs/       run configuration (default.toml; pilot_local.toml extends it)
scripts/       local model server, pilot runner and status
results/       run outputs (results/<run_id>/log.jsonl) — gitignored
reports/       committed summary reports
notebook/      LAB_NOTEBOOK.md, dated research log
tests/         pytest suite
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                    # exact pinned versions
pip install -e ".[dev]" --no-deps                  # this package, editable
pytest
```

EvalPlus's evaluator and the rlimit sandbox backend need Linux (`SIGALRM`,
`resource`). On Windows use WSL2; tests that need Linux or Docker skip
themselves elsewhere and run in CI.

## Pipeline

Two kinds of stage, so inference and code execution can run on different hosts
(plan: inference on a GPU cluster, NSCC ASPIRE 2A or CCDS TC1; all
candidate-code execution in WSL2):

| Stage | Command | Runs code? |
|---|---|---|
| generate candidates | `python -m verifier.corpus.build generate --run-id R [--sample N]` | no |
| label candidates | `python -m verifier.corpus.build label --run-id R` | yes (WSL2) |
| verify | `python -m verifier.harness.verify --corpus R --run-id V --strategy direct\|reason --seeds 0 1 2` | no |
| report | `python -m verifier.analysis.report --run-id V --out reports/...` | no |

Every model-calling stage appends to `results/<run_id>/log.jsonl` and resumes
from it after an interruption.

### Local pilot (laptop CPU, WSL2)

Qwen2.5-Coder-1.5B-Instruct (q4_k_m) served by llama.cpp in Docker, 40 problems
× 10 candidates, strategies (a) and (b) with 3 seeds each:

```bash
bash scripts/run_pilot.sh        # whole pilot, resumable; keep WSL attached
bash scripts/pilot_status.sh     # progress, from any other window
```

WSL2 stops its VM (and the model server) when no Windows-side `wsl` client is
attached, so long runs need an attached session or a keep-alive.

### GPU inference (NSCC ASPIRE 2A, PBS Pro)

Each PBS job serves one model with vLLM on one A100-40GB (32 requests in
flight, `configs/aspire_a100.toml`) and runs its model-calling stages.
Labelling never runs there. Full sweep, a 2×2 self/cross design with
Qwen2.5-Coder-7B (`q7b`) and Llama-3.1-8B (`l8b`) as generators and as
verifiers:

```bash
# WSL: push code
bash scripts/aspire/sync.sh code
# ASPIRE login node, once: conda env + vllm, HumanEval+ cache, both models
# (Llama is gated: accept its licence on Hugging Face, `huggingface-cli login`)
bash scripts/aspire/setup_env.sh
qsub scripts/aspire/gpu_smoke.pbs
# Phase A (ASPIRE): one generation job per model -> results/gen-<g>/
bash scripts/aspire/submit.sh generate
# WSL: pull, label (runs candidate code), push back
bash scripts/aspire/label_corpora.sh
# Phase B (ASPIRE): 4 jobs, corpus x verifier; direct, direct-swapped, reason x 3 seeds
bash scripts/aspire/submit.sh verify
# WSL: pull verify logs, then report locally
bash scripts/aspire/sync.sh pull-run verify-gen-q7b-by-l8b   # etc.
```

Every stage resumes from its log, so after a walltime kill, run the same
submit line again. `DRY_RUN=1` prints the qsub commands instead of submitting.

Access is via the NTU HPCC jumphost; see `notebook/LAB_NOTEBOOK.md`
(2026-11-17).

## Status

Phase 1 (corpus) and the first Phase 2 strategies are being piloted locally
(`reports/pilot-q15b/` once complete). Execution-based strategies (c)/(d) and
the OpenClaw integration are not implemented yet.
