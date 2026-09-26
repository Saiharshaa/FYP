"""Subprocess target for test_runlog: a slow mock run that the test kills."""

import sys
import time

from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog, Task, execute


def tasks() -> list[Task]:
    return [Task(f"HumanEval/{p}", f"c{c}", s, seed, f"verify HumanEval/{p} c{c}")
            for p in range(5) for c in range(2) for s in ("direct", "cot")
            for seed in (0, 1)]  # 40 tasks


def slow(prompt: str, seed: int) -> str:
    time.sleep(0.05)
    return f"VERDICT: correct ({seed})"


if __name__ == "__main__":
    root, run_id = sys.argv[1], sys.argv[2]
    execute(RunLog(run_id, root), tasks(), MockClient(slow),
            temperature=0.0, max_tokens=64)
