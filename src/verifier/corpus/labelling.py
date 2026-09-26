"""Ground-truth labelling of candidate solutions via EvalPlus (HumanEval+).

Thin wrapper over the same functions ``evalplus.evaluate.evaluate`` uses
internally (evalplus 0.3.1): ``get_human_eval_plus``, ``get_groundtruth`` and
``check_correctness``. Calling them directly avoids the CLI's file-based I/O and
its on-disk result cache, while keeping identical pass/fail semantics.

Two properties of EvalPlus matter for interpreting labels:

* ``expected`` outputs are produced by executing each problem's canonical
  solution (``get_groundtruth`` -> ``trusted_exec``). A label therefore means
  "agrees with the canonical solution on the base/plus inputs", and canonical
  solutions pass by construction.
* Per-test time limits are ``max(1.0s, 4 x canonical runtime)``, with the
  canonical runtime measured on the current machine. Timeout labels are thus
  host-dependent; record where labels were produced.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass

from evalplus.data import get_human_eval_plus, get_human_eval_plus_hash
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION
from evalplus.eval import PASS
from evalplus.evaluate import check_correctness, get_groundtruth


@dataclass(frozen=True)
class Label:
    task_id: str
    base_status: str  # "pass" | "fail" | "timeout"
    plus_status: str
    n_base_passed: int  # tests passed before stopping (all, if fast_check=False)
    n_plus_passed: int

    @property
    def correct(self) -> bool:
        """Ground truth: correct iff it passes both base and plus suites."""
        return self.base_status == PASS and self.plus_status == PASS


def require_posix() -> None:
    # evalplus's reliability_guard imports `resource` and uses SIGALRM. On
    # Windows it raises inside the worker before the result is recorded, so
    # every candidate is silently reported as "timeout". Refuse instead.
    if os.name != "posix":
        raise RuntimeError(
            "EvalPlus execution needs a POSIX host (resource, SIGALRM); "
            "run under Linux/WSL2, not native Windows."
        )


def load_problems() -> dict[str, dict]:
    return get_human_eval_plus()


def dataset_info() -> dict[str, str]:
    return {"dataset": "HumanEvalPlus", "version": HUMANEVAL_PLUS_VERSION,
            "md5": get_human_eval_plus_hash()}


def load_expected(problems: dict[str, dict]) -> dict[str, dict]:
    # Cached by EvalPlus under its user cache dir, keyed by dataset hash.
    return get_groundtruth(problems, get_human_eval_plus_hash(), [])


def label_solution(problem: dict, solution: str, expected: dict,
                   fast_check: bool = True) -> Label:
    """Label one complete solution (prompt + body) against base and plus tests."""
    require_posix()
    r = check_correctness("humaneval", 0, problem, solution, expected,
                          base_only=False, fast_check=fast_check)
    (b_stat, b_det), (p_stat, p_det) = r["base"], r["plus"]
    return Label(problem["task_id"], b_stat, p_stat,
                 int(sum(b_det)), int(sum(p_det)))


def label_many(items: list[tuple[str, str]], problems: dict[str, dict],
               expected: dict[str, dict], workers: int | None = None,
               fast_check: bool = True) -> list[Label]:
    """Label (task_id, solution) pairs in parallel; output order matches input."""
    require_posix()
    workers = workers or max(1, (os.cpu_count() or 2) // 2)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(label_solution, problems[t], s, expected[t], fast_check)
                for t, s in items]
        return [f.result() for f in futs]


def canonical_solution(problem: dict) -> str:
    # Same composition evaluate() uses for "completion"-style samples.
    return problem["prompt"] + problem["canonical_solution"]


def to_dict(label: Label) -> dict:
    return {**asdict(label), "correct": label.correct}
