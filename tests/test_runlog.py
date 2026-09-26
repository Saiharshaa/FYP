import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog, Task, audit, execute

sys.path.insert(0, str(Path(__file__).parent))
import _mock_run  # noqa: E402

SCHEMA = {"run_id", "problem_id", "candidate_id", "strategy", "seed", "prompt",
          "response", "verdict", "input_tokens", "output_tokens", "latency_s",
          "timestamp"}


def lines(log: RunLog) -> list[str]:
    return log.path.read_text(encoding="utf-8").splitlines() if log.path.exists() else []


def test_record_has_required_fields(tmp_path):
    log = RunLog("r1", tmp_path)
    execute(log, _mock_run.tasks()[:1], MockClient(), temperature=0.0, max_tokens=16,
            parse_verdict=lambda s: None)
    rec = json.loads(lines(log)[0])
    assert SCHEMA <= rec.keys()
    assert rec["run_id"] == "r1" and rec["verdict"] is None
    assert rec["timestamp"].endswith("Z")
    assert log.path == tmp_path / "r1" / "log.jsonl"


def test_resume_skips_logged_keys(tmp_path):
    tasks = _mock_run.tasks()
    log, client = RunLog("r2", tmp_path), MockClient()
    assert execute(log, tasks[:15], client, temperature=0, max_tokens=16) == 15
    assert execute(log, tasks, client, temperature=0, max_tokens=16) == len(tasks) - 15
    assert execute(log, tasks, client, temperature=0, max_tokens=16) == 0
    assert audit(log, tasks) == {"duplicates": [], "missing": [], "unexpected": []}


def test_kill_halfway_then_resume_has_no_duplicates_or_gaps(tmp_path):
    tasks = _mock_run.tasks()
    log_path = tmp_path / "killed" / "log.jsonl"
    proc = subprocess.Popen([sys.executable, str(Path(_mock_run.__file__)),
                             str(tmp_path), "killed"])
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if log_path.exists() and log_path.read_bytes().count(b"\n") >= len(tasks) // 2:
                break
            time.sleep(0.01)
        proc.kill()  # SIGKILL / TerminateProcess: no cleanup handlers run
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    before = log_path.read_bytes().count(b"\n")
    assert 0 < before < len(tasks), f"kill landed outside the run ({before} lines)"

    log = RunLog("killed", tmp_path)
    client = MockClient(_mock_run.slow)
    made = execute(log, tasks, client, temperature=0.0, max_tokens=64)

    assert made == len(tasks) - before  # only unfinished work was redone
    assert audit(log, tasks) == {"duplicates": [], "missing": [], "unexpected": []}
    assert len(lines(log)) == len(tasks)


def test_partial_trailing_line_is_repaired(tmp_path):
    tasks = _mock_run.tasks()[:3]
    log = RunLog("torn", tmp_path)
    execute(log, tasks[:2], MockClient(), temperature=0, max_tokens=16)
    with open(log.path, "a", encoding="utf-8") as f:
        f.write('{"run_id": "torn", "problem_id": "Human')  # died mid-write

    log = RunLog("torn", tmp_path)
    assert log.repaired_bytes > 0
    assert execute(log, tasks, MockClient(), temperature=0, max_tokens=16) == 1
    assert audit(log, tasks) == {"duplicates": [], "missing": [], "unexpected": []}


def test_audit_reports_duplicates(tmp_path):
    tasks = _mock_run.tasks()[:2]
    log = RunLog("dup", tmp_path)
    execute(log, tasks, MockClient(), temperature=0, max_tokens=16)
    first = lines(log)[0]
    with open(log.path, "a", encoding="utf-8") as f:
        f.write(first + "\n")
    assert audit(log, tasks)["duplicates"] == [tasks[0].key]


def test_rejects_unsafe_run_id(tmp_path):
    with pytest.raises(ValueError):
        RunLog("../escape", tmp_path)
