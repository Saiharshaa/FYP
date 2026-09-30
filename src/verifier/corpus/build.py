"""Build the labelled candidate corpus in two stages that run on different hosts.

  generate   model calls only; never executes candidate code, so it is safe to
             run on TC1 next to vLLM. Appends to results/<run_id>/log.jsonl and
             resumes after a kill (e.g. the six-hour SLURM wall limit).
  label      executes candidates (evalplus + sandbox re-run); WSL2 only.
             Writes results/<run_id>/corpus.jsonl and corpus_meta.json.

    python -m verifier.corpus.build generate --run-id gen-qwen7b --backend openai
    python -m verifier.corpus.build label    --run-id gen-qwen7b

One generator model per run_id: the resume key does not include the model,
so `generate` refuses to add a different model to an existing log.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from verifier.config import load_config
from verifier.harness.client import ModelClient, make_client
from verifier.harness.runlog import RunLog, Task, execute

STRATEGY = "generate"  # the `strategy` field for generation calls in the log

# EvalPlus's instruct prompt (evalplus.codegen, "base" split). EvalPlus also
# pre-fills the assistant turn with a response prefix; OpenAI-compatible chat
# APIs cannot pre-fill, so only the user message is sent.
INSTRUCTION = ("Please provide a self-contained Python script that solves the "
               "following problem in a markdown code block:")


def build_prompt(problem: dict) -> str:
    return f"{INSTRUCTION}\n```\n{problem['prompt'].strip()}\n```\n"


def candidate_id(temperature: float, sample: int) -> str:
    return f"T{temperature:g}-{sample}"


def generation_tasks(problems: dict[str, dict], temperature: float,
                     samples: int) -> list[Task]:
    return [Task(problem_id=t, candidate_id=candidate_id(temperature, i),
                 strategy=STRATEGY, seed=i, prompt=build_prompt(p))
            for t, p in problems.items() for i in range(samples)]


def generate(log: RunLog, client: ModelClient, problems: dict[str, dict],
             gen_cfg: dict) -> int:
    """Generate every missing candidate; returns the number of model calls made."""
    models = {r.model for r in log.records() if r.strategy == STRATEGY}
    if models - {client.model}:
        raise ValueError(f"run {log.run_id!r} already holds candidates from "
                         f"{sorted(models)}; use a new run_id for {client.model!r}")
    made = 0
    for temperature in gen_cfg["temperatures"]:
        tasks = generation_tasks(problems, temperature, gen_cfg["samples_per_temperature"])
        made += execute(log, tasks, client, temperature=temperature,
                        max_tokens=gen_cfg["max_tokens"])
    return made


# ----------------------------------------------------------------- labelling

def extract_solution(response: str, entry_point: str) -> str:
    from evalplus.sanitize import sanitize  # tree-sitter based, as the evalplus CLI

    return sanitize(response, entry_point)


_FENCED = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)


def response_diagnostics(response: str, solution: str) -> dict:
    """How the model's own code relates to the labelled solution.

    evalplus's sanitize is error-tolerant: a syntax error in the response is
    usually *repaired away* (e.g. a broken `return (` is dropped, leaving a
    docstring-only function that returns None -> wrong_output). The label and
    failure_category describe the sanitized code; these fields record what the
    model actually wrote, for the H3 analysis.
    """
    m = _FENCED.search(response)
    raw = m.group(1) if m else response
    try:
        ast.parse(raw)
        parses = True
    except (SyntaxError, ValueError):
        parses = False
    return {"response_has_code_block": m is not None,
            "response_code_parses": parses,
            "sanitize_modified": raw.strip() != solution.strip()}


def label(log: RunLog, cfg: dict, workers: int | None = None) -> dict:
    """Label every generated candidate in the log; returns corpus metadata."""
    from verifier.corpus.categorise import categorise, machine_info
    from verifier.corpus.labelling import (
        dataset_info, evalplus_info, label_many, load_expected, load_problems,
        require_posix, to_dict)
    from verifier.sandbox import make_sandbox

    require_posix()
    lab = cfg["labelling"]
    excluded = cfg["corpus"].get("exclude", [])
    problems = load_problems(excluded)
    expected = load_expected(problems)
    sandbox = make_sandbox(cfg["sandbox"])
    workers = workers or lab.get("workers") or 1  # serial default: see config

    records = [r for r in log.records() if r.strategy == STRATEGY]
    skipped = Counter(r.problem_id for r in records if r.problem_id not in problems)
    records = [r for r in records if r.problem_id in problems]
    solutions = [extract_solution(r.response, problems[r.problem_id]["entry_point"])
                 for r in records]

    labels = label_many([(r.problem_id, s) for r, s in zip(records, solutions)],
                        problems, expected, workers)
    with ThreadPoolExecutor(max_workers=workers) as ex:  # sandbox re-runs of failures
        labels = list(ex.map(
            lambda ls: categorise(ls[0], problems[ls[0].task_id], ls[1],
                                  expected[ls[0].task_id], sandbox,
                                  lab["timeout_multiplier"], lab["memory_mb"]),
            zip(labels, solutions)))

    rows = []
    for r, sol, l in zip(records, solutions, labels):
        d = to_dict(l)
        d.pop("task_id")
        rows.append({"problem_id": r.problem_id, "candidate_id": r.candidate_id,
                     "model": r.model, "temperature": r.temperature, "seed": r.seed,
                     "truncated": r.finish_reason == "length",
                     "solution": sol,
                     "solution_sha256": hashlib.sha256(sol.encode()).hexdigest(),
                     **response_diagnostics(r.response, sol),
                     **d})

    meta = {
        "run_id": log.run_id,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_candidates": len(rows),
        "n_correct": sum(r["correct"] for r in rows),
        "failure_categories": dict(Counter(r["failure_category"] for r in rows
                                           if not r["correct"])),
        "n_truncated": sum(r["truncated"] for r in rows),
        "n_response_syntax_error": sum(not r["response_code_parses"] for r in rows),
        "skipped_excluded": dict(skipped),
        "models": sorted({r["model"] for r in rows}),
        "generation": cfg["generation"],
        "timeout_multiplier": lab["timeout_multiplier"],
        "labelling_workers": workers,
        "excluded": excluded,
        "evalplus": evalplus_info(),
        **{"dataset_" + k: v for k, v in dataset_info().items()},
        "machine": machine_info(sandbox),
    }
    _atomic_write(log.path.with_name("corpus.jsonl"),
                  "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    _atomic_write(log.path.with_name("corpus_meta.json"), json.dumps(meta, indent=2))
    return meta


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ----------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verifier.corpus.build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="model calls only (safe on TC1)")
    g.add_argument("--run-id", required=True)
    g.add_argument("--backend", choices=["openai", "mock"], default="openai")
    g.add_argument("--limit", type=int, help="first N problems only (dry runs)")
    l = sub.add_parser("label", help="execute + label candidates (WSL2 only)")
    l.add_argument("--run-id", required=True)
    l.add_argument("--workers", type=int)
    for p in (g, l):
        p.add_argument("--results", default="results")
    args = ap.parse_args(argv)

    cfg = load_config()
    log = RunLog(args.run_id, args.results)
    if args.cmd == "generate":
        from verifier.corpus.labelling import load_problems  # dataset only; no execution

        problems = load_problems(cfg["corpus"].get("exclude", []))
        if args.limit:
            problems = dict(list(problems.items())[: args.limit])
        if args.backend == "mock":
            from verifier.corpus.mock_coder import MockCoder
            client = MockCoder(problems)
        else:
            client = make_client("openai")
        made = generate(log, client, problems, cfg["generation"])
        print(f"{made} model calls; log at {log.path}")
    else:
        meta = label(log, cfg, args.workers)
        print(json.dumps({k: meta[k] for k in ("n_candidates", "n_correct",
                                               "failure_categories", "n_truncated")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
