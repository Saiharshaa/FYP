"""Sanity check of the ground-truth labeller.

1. Every HumanEval+ canonical solution must pass base and plus tests.
2. Deliberately wrong solutions must fail. Each covers a different failure
   category from the project plan (wrong algorithm, implementation bug, timeout).

Because EvalPlus derives expected outputs from the canonical solutions, (1)
validates the execution pipeline (determinism, time limits, sandbox guard), not
the correctness of the canonical solutions themselves.

Run:  python -m verifier.corpus.ground_truth_check [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time

from verifier.corpus.labelling import (
    canonical_solution,
    dataset_info,
    label_many,
    load_expected,
    load_problems,
    require_posix,
    to_dict,
)

# task_id -> (failure category, function body appended to the prompt)
WRONG_SOLUTIONS: dict[str, tuple[str, str]] = {
    "HumanEval/0": ("wrong_algorithm", "    return False\n"),
    "HumanEval/23": ("implementation_bug", "    return len(string) - 1\n"),
    "HumanEval/13": ("timeout", "    while True:\n        pass\n"),
}


def run(workers: int | None = None) -> dict:
    require_posix()
    t0 = time.time()
    problems = load_problems()
    expected = load_expected(problems)

    canon = label_many([(t, canonical_solution(p)) for t, p in problems.items()],
                       problems, expected, workers)
    wrong_items = [(t, problems[t]["prompt"] + body)
                   for t, (_, body) in WRONG_SOLUTIONS.items()]
    wrong = label_many(wrong_items, problems, expected, workers)

    canon_failures = [to_dict(l) for l in canon if not l.correct]
    return {
        **dataset_info(),
        "host": {"python": sys.version.split()[0], "platform": platform.platform()},
        "n_problems": len(problems),
        "canonical": {
            "base_pass": sum(l.base_status == "pass" for l in canon),
            "plus_pass": sum(l.plus_status == "pass" for l in canon),
            "failures": canon_failures,
        },
        "wrong": [{**to_dict(l), "category": WRONG_SOLUTIONS[l.task_id][0]}
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

    ok = (report["canonical"]["base_pass"] == report["n_problems"]
          and report["canonical"]["plus_pass"] == report["n_problems"]
          and not any(w["correct"] for w in report["wrong"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
