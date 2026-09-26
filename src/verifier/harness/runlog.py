"""Append-only JSONL log of model calls, with checkpoint/resume.

One line per model call in results/<run_id>/log.jsonl. A call's identity is
(problem_id, candidate_id, strategy, seed); `execute` skips identities already
logged, so a run killed by the TC1 six-hour wall limit is resumed by simply
re-submitting the same run_id.

Durability: each record is written with a single write(), then flushed and
fsync'd before the next call starts. If the process dies mid-write, the only
possible damage is a partial final line; opening the log truncates it, so that
call is redone rather than lost or duplicated.

Assumes a single writer per run_id (one SLURM job at a time). Parallel workers
should use separate run_ids, or shard by problem_id.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

from verifier.harness.client import ModelClient

Key = tuple[str, str, str, int]  # (problem_id, candidate_id, strategy, seed)
_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class Task:
    problem_id: str
    candidate_id: str
    strategy: str
    seed: int
    prompt: str

    @property
    def key(self) -> Key:
        return (self.problem_id, self.candidate_id, self.strategy, self.seed)


@dataclass(frozen=True)
class LogRecord:
    run_id: str
    problem_id: str
    candidate_id: str
    strategy: str
    seed: int
    prompt: str
    response: str
    verdict: bool | None
    input_tokens: int
    output_tokens: int
    latency_s: float
    timestamp: str  # UTC, ISO 8601
    # Beyond the core schema: needed for the cross-model ablation and for
    # spotting responses truncated by max_tokens.
    model: str
    temperature: float
    max_tokens: int
    finish_reason: str | None

    @property
    def key(self) -> Key:
        return (self.problem_id, self.candidate_id, self.strategy, self.seed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RunLog:
    def __init__(self, run_id: str, root: str | os.PathLike = "results"):
        if not _RUN_ID.match(run_id):
            raise ValueError(f"run_id must match {_RUN_ID.pattern}: {run_id!r}")
        self.run_id = run_id
        self.path = Path(root) / run_id / "log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.repaired_bytes = self._repair()

    def _repair(self) -> int:
        """Drop a partial trailing line left by a crash mid-write."""
        if not self.path.exists():
            return 0
        data = self.path.read_bytes()
        if not data or data.endswith(b"\n"):
            return 0
        keep = data.rfind(b"\n") + 1
        with open(self.path, "r+b") as f:
            f.truncate(keep)
        return len(data) - keep

    def records(self) -> Iterator[LogRecord]:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield LogRecord(**json.loads(line))

    def completed(self) -> set[Key]:
        return {r.key for r in self.records()}

    def append(self, record: LogRecord) -> None:
        if record.run_id != self.run_id:
            raise ValueError("record belongs to a different run")
        line = json.dumps(asdict(record), ensure_ascii=False) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


def pending(tasks: Iterable[Task], done: set[Key]) -> list[Task]:
    """Resume: the tasks whose key is not yet logged, in original order."""
    return [t for t in tasks if t.key not in done]


def execute(log: RunLog, tasks: Iterable[Task], client: ModelClient, *,
            temperature: float, max_tokens: int,
            parse_verdict: Callable[[str], bool | None] | None = None) -> int:
    """Run every not-yet-logged task through the client; returns calls made."""
    todo = pending(tasks, log.completed())
    for t in todo:
        g = client.generate(t.prompt, temperature=temperature, seed=t.seed,
                            max_tokens=max_tokens)
        log.append(LogRecord(
            run_id=log.run_id, problem_id=t.problem_id, candidate_id=t.candidate_id,
            strategy=t.strategy, seed=t.seed, prompt=t.prompt, response=g.text,
            verdict=parse_verdict(g.text) if parse_verdict else None,
            input_tokens=g.input_tokens, output_tokens=g.output_tokens,
            latency_s=round(g.latency_s, 6), timestamp=_now(), model=g.model,
            temperature=temperature, max_tokens=max_tokens,
            finish_reason=g.finish_reason))
    return len(todo)


def audit(log: RunLog, tasks: Iterable[Task]) -> dict[str, list[Key]]:
    """Compare a log against the intended task list."""
    counts = Counter(r.key for r in log.records())
    wanted = {t.key for t in tasks}
    return {"duplicates": sorted(k for k, n in counts.items() if n > 1),
            "missing": sorted(wanted - counts.keys()),
            "unexpected": sorted(counts.keys() - wanted)}
