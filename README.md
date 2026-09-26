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
  corpus/    ground-truth labelling via EvalPlus (HumanEval+)
  sandbox/   resource-limited execution of untrusted code (Docker / rlimit subprocess)
  harness/   model client, run logging, checkpoint/resume
configs/     run configuration
results/     run outputs (results/<run_id>/log.jsonl) — gitignored
notebook/    LAB_NOTEBOOK.md, dated research log
tests/       pytest suite
```

## Status

Phase 0 (setup). Verification strategies and the OpenClaw integration are not
implemented yet.
