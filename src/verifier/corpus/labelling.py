"""Ground-truth labelling of candidate solutions via EvalPlus (HumanEval+).

Thin wrapper over the same functions ``evalplus.evaluate.evaluate`` uses
internally: ``get_human_eval_plus``, ``get_groundtruth`` and
``check_correctness``. evalplus is pinned to commit 6eb1e19 (v0.3.1 plus the
find_zero fix, #241). Calling these directly avoids the CLI's file-based I/O and
its on-disk result cache, while keeping identical pass/fail semantics.

Two properties of EvalPlus matter for interpreting labels:

* ``expected`` outputs are produced by executing each problem's canonical
  solution (``get_groundtruth`` -> ``trusted_exec``). A label therefore means
  "agrees with the canonical solution on the base/plus inputs".
* Per-test time limits are ``max(1.0s, 4 x canonical runtime)``, with the
  canonical runtime measured on the current machine. A test that exceeds its
  limit is reported as ``fail``, not ``timeout`` (``timeout`` only when the
  whole worker hangs). ``verifier.corpus.categorise`` derives the failure type.

The correctness label is the raw evalplus status and is never rewritten.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from importlib.metadata import distribution, version

from evalplus.data import get_human_eval_plus, get_human_eval_plus_hash
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION
from evalplus.eval import PASS
from evalplus.evaluate import check_correctness, get_groundtruth


@dataclass(frozen=True)
class Label:
    task_id: str
    base_status: str  # raw evalplus status: "pass" | "fail" | "timeout"
    plus_status: str
    n_base_passed: int  # tests passed before stopping (all, if fast_check=False)
    n_plus_passed: int
    failing_suite: str | None = None  # "base" | "plus": where the first failure is
    failing_index: int | None = None  # index into that suite's inputs
    # Derived by categorise(); never feeds back into `correct`.
    failure_category: str | None = None
    rerun: dict | None = None

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


def load_problems(exclude: list[str] | tuple[str, ...] = ()) -> dict[str, dict]:
    """HumanEval+ problems, minus any excluded task_ids (see [corpus] exclude)."""
    problems = get_human_eval_plus()
    unknown = set(exclude) - problems.keys()
    if unknown:
        raise ValueError(f"excluded task_ids not in dataset: {sorted(unknown)}")
    return {t: p for t, p in problems.items() if t not in set(exclude)}


def evalplus_info() -> dict[str, str | None]:
    info = json.loads(distribution("evalplus").read_text("direct_url.json") or "{}")
    return {"version": version("evalplus"),
            "commit": info.get("vcs_info", {}).get("commit_id")}


def dataset_info() -> dict[str, str]:
    # md5 of the cached jsonl. evalplus writes it in text mode, so a Windows
    # cache (CRLF) hashes differently from Linux; the Linux value is canonical.
    return {"dataset": "HumanEvalPlus", "version": HUMANEVAL_PLUS_VERSION,
            "md5": get_human_eval_plus_hash()}


def load_expected(problems: dict[str, dict]) -> dict[str, dict]:
    # Cached by evalplus under its user cache dir, keyed by the hash of the FULL
    # dataset, so always compute on the full set and then subset.
    full = get_groundtruth(get_human_eval_plus(), get_human_eval_plus_hash(), [])
    return {t: full[t] for t in problems}


def _first_failure(details: list[bool]) -> int:
    # fast_check stops at the first failing test, recording it as False; if the
    # worker hung or crashed before recording, the failure is the next index.
    return details.index(False) if False in details else len(details)


def label_solution(problem: dict, solution: str, expected: dict,
                   fast_check: bool = True) -> Label:
    """Label one complete solution (prompt + body) against base and plus tests."""
    require_posix()
    r = check_correctness("humaneval", 0, problem, solution, expected,
                          base_only=False, fast_check=fast_check)
    (b_stat, b_det), (p_stat, p_det) = r["base"], r["plus"]
    b_det, p_det = list(b_det), list(p_det)
    suite = index = None
    if b_stat != PASS:
        suite, index = "base", _first_failure(b_det)
    elif p_stat != PASS:
        suite, index = "plus", _first_failure(p_det)
    return Label(problem["task_id"], b_stat, p_stat, int(sum(b_det)), int(sum(p_det)),
                 suite, index)


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
