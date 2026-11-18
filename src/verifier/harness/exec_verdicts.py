"""Execution stage for strategies (c) self-tests and (d) reference.

    python -m verifier.harness.exec_verdicts --run-id verify-gen-q7b-by-l8b [--workers N]

Runs in WSL2 only: it executes the verifier model's tests / reference code and
every candidate, inside the sandbox. For each per-problem model call logged by
`verify` (candidate_id == "__problem__") and each corpus candidate of that
problem, it writes one line to results/<run_id>/exec.jsonl:

    {problem_id, candidate_id, strategy, seed, verdict, details, duration_s}

Resumable: keys already in exec.jsonl are skipped. The report reads verdicts
for these strategies from exec.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from verifier.config import load_config
from verifier.harness.runlog import RunLog
from verifier.harness.verify import load_corpus
from verifier.strategies import EXEC_STRATEGIES, PER_PROBLEM
from verifier.strategies.execution import (
    MAX_INPUTS, PER_CALL_S, decide, extract_asserts, extract_reference,
    read_result, reference_program, self_tests_program)

EXEC_FILE = "exec.jsonl"


def exec_path(results: str | Path, run_id: str) -> Path:
    return Path(results) / run_id / EXEC_FILE


def load_exec(results: str | Path, run_id: str) -> dict[tuple, dict]:
    p = exec_path(results, run_id)
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue                      # partial trailing line
                out[(r["problem_id"], r["candidate_id"], r["strategy"], r["seed"],
                     r.get("extract", "v1"))] = r
    return out


def jobs(results: str | Path, run_id: str) -> list[dict]:
    """Every (problem call x candidate x extractor) still missing from exec.jsonl.

    Extractor v1 always runs. A v2 job exists only where v1 found no test and
    v2 finds some; everywhere else the v2 verdict *is* the v1 verdict (the
    report falls back to v1), so nothing is executed twice."""
    vmeta = json.loads((Path(results) / run_id / "verify_meta.json").read_text())
    rows, _ = load_corpus(results, vmeta["corpus_run"])
    by_problem: dict[str, list[dict]] = {}
    for r in rows:
        by_problem.setdefault(r["problem_id"], []).append(r)
    done = load_exec(results, run_id)
    todo = []
    for rec in RunLog(run_id, results).records():
        if rec.strategy not in EXEC_STRATEGIES or rec.candidate_id != PER_PROBLEM:
            continue
        versions = ["v1"]
        if (rec.strategy == "self-tests" and not extract_asserts(rec.response, version="v1")
                and extract_asserts(rec.response, version="v2")):
            versions.append("v2")
        for row in by_problem.get(rec.problem_id, []):
            for ver in versions:
                key = (rec.problem_id, row["candidate_id"], rec.strategy, rec.seed, ver)
                if key not in done:
                    todo.append({"key": key, "response": rec.response,
                                 "solution": row["solution"]})
    return todo


def run_one(job: dict, problems: dict, sandbox, memory_mb: int) -> dict:
    pid, cid, strategy, seed, ver = job["key"]
    base = {"problem_id": pid, "candidate_id": cid, "strategy": strategy, "seed": seed,
            "extract": ver}
    if strategy == "self-tests":
        tests = extract_asserts(job["response"], version=ver)
        if not tests:
            return {**base, "verdict": None, "details": {"n_tests": 0}, "duration_s": 0.0}
        code = self_tests_program(job["solution"], tests)
        timeout = 15 + PER_CALL_S * len(tests)
    elif strategy == "reference":
        ref = extract_reference(job["response"])
        if ref is None:
            return {**base, "verdict": None, "details": {"error": "no_reference"},
                    "duration_s": 0.0}
        code = reference_program(job["solution"], ref, problems[pid]["entry_point"])
        timeout = 25 + 2 * PER_CALL_S * MAX_INPUTS
    else:
        raise ValueError(strategy)
    res = sandbox.run(code, timeout_s=timeout, memory_mb=memory_mb)
    verdict, details = decide(strategy, read_result(res["stdout"]), res["timed_out"])
    return {**base, "verdict": verdict, "details": details,
            "duration_s": round(res["duration_s"], 3)}


def run(results: str | Path, run_id: str, cfg: dict, workers: int = 1) -> int:
    from verifier.corpus.labelling import load_problems, require_posix
    from verifier.sandbox import make_sandbox

    require_posix()
    todo = jobs(results, run_id)
    if not todo:
        return 0
    problems = load_problems()
    sandbox = make_sandbox(cfg["sandbox"])
    mem = cfg["labelling"]["memory_mb"]
    path = exec_path(results, run_id)
    if path.exists():                     # drop a partial last line from a crash
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            path.write_bytes(data[: data.rfind(b"\n") + 1])
    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        for out in ex.map(lambda j: run_one(j, problems, sandbox, mem), todo):
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return len(todo)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verifier.harness.exec_verdicts")
    ap.add_argument("--run-id", required=True, help="verify run id")
    ap.add_argument("--results", default="results")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel sandboxes (default 1: per-call 2 s limits are load-sensitive)")
    args = ap.parse_args(argv)
    n = run(args.results, args.run_id, load_config(), args.workers)
    print(f"{n} executions; results at {exec_path(args.results, args.run_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
