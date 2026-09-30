"""Sanity check of the ground-truth labeller.

1. Every HumanEval+ canonical solution (minus [corpus] exclude) must pass base
   and plus tests.
2. Deliberately wrong solutions must fail. Each covers a different failure
   category, and each failure is categorised by re-running in the sandbox.

Because EvalPlus derives expected outputs from the canonical solutions, (1)
validates the execution pipeline (determinism, time limits, sandbox guard), not
the correctness of the canonical solutions themselves.

Run:  python -m verifier.corpus.ground_truth_check [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from verifier.config import load_config
from verifier.corpus.categorise import categorise, machine_info
from verifier.corpus.labelling import (
    canonical_solution,
    dataset_info,
    evalplus_info,
    label_many,
    load_expected,
    load_problems,
    require_posix,
    to_dict,
)
from verifier.sandbox import make_sandbox

# task_id -> (expected failure_category, function body appended to the prompt)
WRONG_SOLUTIONS: dict[str, tuple[str, str]] = {
    "HumanEval/0": ("wrong_output", "    return False\n"),               # wrong algorithm
    "HumanEval/23": ("wrong_output", "    return len(string) - 1\n"),     # off-by-one
    "HumanEval/13": ("timeout", "    while True:\n        pass\n"),        # never returns
}


def run(workers: int | None = None, config: dict | None = None) -> dict:
    require_posix()
    cfg = config or load_config()
    lab = cfg["labelling"]
    workers = workers or lab.get("workers") or 1
    sandbox = make_sandbox(cfg["sandbox"])
    t0 = time.time()
    problems = load_problems(cfg["corpus"].get("exclude", []))
    expected = load_expected(problems)

    def labelled(items):
        labels = label_many(items, problems, expected, workers)
        return [categorise(l, problems[l.task_id], s, expected[l.task_id], sandbox,
                           lab["timeout_multiplier"], lab["memory_mb"])
                for l, (_, s) in zip(labels, items)]

    canon = labelled([(t, canonical_solution(p)) for t, p in problems.items()])
    wrong = labelled([(t, problems[t]["prompt"] + body)
                      for t, (_, body) in WRONG_SOLUTIONS.items()])

    return {
        **dataset_info(),
        "evalplus": evalplus_info(),
        "machine": machine_info(sandbox),
        "timeout_multiplier": lab["timeout_multiplier"],
        "labelling_workers": workers,
        "excluded": list(cfg["corpus"].get("exclude", [])),
        "n_problems": len(problems),
        "canonical": {
            "base_pass": sum(l.base_status == "pass" for l in canon),
            "plus_pass": sum(l.plus_status == "pass" for l in canon),
            "failures": [to_dict(l) for l in canon if not l.correct],
        },
        "wrong": [{**to_dict(l), "expected_category": WRONG_SOLUTIONS[l.task_id][0]}
                  for l in wrong],
        "duration_s": round(time.time() - t0, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write JSON report here")
    ap.add_argument("--workers", type=int)
    args = ap.parse_args()

    report = run(args.workers)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)

    n = report["n_problems"]
    ok = (report["canonical"]["base_pass"] == n and report["canonical"]["plus_pass"] == n
          and all(not w["correct"] and w["failure_category"] == w["expected_category"]
                  for w in report["wrong"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
