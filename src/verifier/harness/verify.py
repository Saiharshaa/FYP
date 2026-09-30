"""Run a verification strategy over a labelled corpus.

    python -m verifier.harness.verify --corpus pilot-q15b --run-id verify-pilot-q15b \
        --strategy direct --seeds 0 1 2

Model calls only (no code execution), so it is TC1-safe like `build generate`.
Each call is one line in results/<run_id>/log.jsonl with strategy, seed and the
parsed verdict (None = no verdict); resume skips logged
(problem_id, candidate_id, strategy, seed). Tasks are seed-major, so a partial
run still holds complete early seeds.

The verifier sees the problem statement and the *sanitized* candidate code
(corpus `solution`, the exact code that was labelled), never tests or labels.
One verify run = one corpus and one verifier model (verify_meta.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from verifier.config import load_config
from verifier.harness.client import ModelClient, MockClient, make_client
from verifier.harness.runlog import RunLog, Task, execute
from verifier.strategies import STRATEGIES, Strategy


def load_corpus(results: str | Path, corpus_run: str) -> tuple[list[dict], dict]:
    d = Path(results) / corpus_run
    path = d / "corpus.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no labelled corpus at {path}; run "
                                f"`build label --run-id {corpus_run}` first")
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    meta_path = d / "corpus_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return rows, meta


def verification_tasks(rows: list[dict], problems: dict[str, dict],
                       strategy: Strategy, seeds: list[int]) -> list[Task]:
    return [Task(problem_id=r["problem_id"], candidate_id=r["candidate_id"],
                 strategy=strategy.name, seed=s,
                 prompt=strategy.build_prompt(problems[r["problem_id"]], r["solution"]))
            for s in seeds for r in rows]


def _record_meta(log: RunLog, corpus_run: str, corpus_meta: dict, client: ModelClient,
                 strategy: Strategy, seeds: list[int], temperature: float) -> dict:
    path = log.path.with_name("verify_meta.json")
    meta = json.loads(path.read_text()) if path.exists() else {
        "run_id": log.run_id, "corpus_run": corpus_run,
        "generator_models": corpus_meta.get("models", []),
        "verifier_model": client.model, "strategies": {}}
    if meta["corpus_run"] != corpus_run:
        raise ValueError(f"verify run {log.run_id!r} belongs to corpus "
                         f"{meta['corpus_run']!r}; use a new run_id")
    if meta["verifier_model"] != client.model:
        raise ValueError(f"verify run {log.run_id!r} uses verifier "
                         f"{meta['verifier_model']!r}; use a new run_id for {client.model!r}")
    prev = meta["strategies"].get(strategy.name)
    if prev and prev["temperature"] != temperature:
        raise ValueError(f"{strategy.name!r} already run at T={prev['temperature']}")
    meta["condition"] = ("self" if meta["generator_models"] == [client.model]
                         else "cross")
    meta["strategies"][strategy.name] = {
        "seeds": sorted(set(seeds) | set(prev["seeds"] if prev else [])),
        "temperature": temperature, "max_tokens": strategy.max_tokens,
        "template_sha256": getattr(strategy, "template_sha256", None),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(meta, indent=2))
    return meta


def verify(log: RunLog, client: ModelClient, rows: list[dict], problems: dict[str, dict],
           strategy: Strategy, seeds: list[int], temperature: float,
           corpus_run: str = "", corpus_meta: dict | None = None) -> int:
    """Run `strategy` on every corpus row for each seed; returns calls made."""
    _record_meta(log, corpus_run, corpus_meta or {}, client, strategy, seeds, temperature)
    tasks = verification_tasks(rows, problems, strategy, seeds)
    return execute(log, tasks, client, temperature=temperature,
                   max_tokens=strategy.max_tokens, parse_verdict=strategy.parse_verdict)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verifier.harness.verify")
    ap.add_argument("--corpus", required=True, help="corpus run_id (labelled)")
    ap.add_argument("--run-id", required=True, help="verification run_id")
    ap.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    ap.add_argument("--seeds", type=int, nargs="+", help="default: [verification] seeds")
    ap.add_argument("--backend", choices=["openai", "mock"], default="openai")
    ap.add_argument("--results", default="results")
    args = ap.parse_args(argv)

    from verifier.corpus.labelling import load_problems  # dataset only

    cfg = load_config()
    vcfg = cfg["verification"]
    rows, corpus_meta = load_corpus(args.results, args.corpus)
    problems = load_problems()
    client = (MockClient() if args.backend == "mock"
              else make_client("openai", **cfg.get("model", {}).get("openai", {})))
    log = RunLog(args.run_id, args.results)
    made = verify(log, client, rows, problems, STRATEGIES[args.strategy],
                  args.seeds or vcfg["seeds"], vcfg["temperature"],
                  corpus_run=args.corpus, corpus_meta=corpus_meta)
    print(f"{made} model calls; log at {log.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
