import json
import os

import pytest

from verifier.config import load_config
from verifier.corpus import build
from verifier.corpus.labelling import load_problems
from verifier.corpus.mock_coder import MockCoder
from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog

CFG = load_config()


@pytest.fixture(scope="module")
def problems():
    return load_problems(CFG["corpus"]["exclude"])


@pytest.fixture(scope="module")
def few(problems):
    return {t: problems[t] for t in ("HumanEval/0", "HumanEval/23", "HumanEval/53")}


def test_default_sampling_plan():
    g = CFG["generation"]
    assert g["temperatures"] == [0.2, 0.8] and g["samples_per_temperature"] == 5


def test_labelling_is_serial_by_default():
    assert CFG["labelling"]["workers"] == 1


def test_prompt_uses_evalplus_instruction(problems):
    p = build.build_prompt(problems["HumanEval/0"])
    assert p.startswith(build.INSTRUCTION)
    assert problems["HumanEval/0"]["prompt"].strip() in p


def test_generation_tasks_are_unique(problems):
    tasks = build.generation_tasks(problems, 0.8, 5)
    assert len(tasks) == len(problems) * 5
    assert len({t.key for t in tasks}) == len(tasks)
    assert {t.candidate_id for t in tasks} == {f"T0.8-{i}" for i in range(5)}


def test_generate_logs_all_candidates_and_resumes(tmp_path, few):
    # Runs on any OS: generation never executes candidate code.
    log = RunLog("gen", tmp_path)
    assert build.generate(log, MockCoder(few), few, CFG["generation"]) == 30
    assert build.generate(log, MockCoder(few), few, CFG["generation"]) == 0
    recs = list(log.records())
    assert len(recs) == 30 and {r.temperature for r in recs} == {0.2, 0.8}
    assert all(r.strategy == "generate" and r.model == "mock-coder" for r in recs)


def test_generate_refuses_second_model_in_same_run(tmp_path, few):
    log = RunLog("gen", tmp_path)
    build.generate(log, MockCoder(few), few, CFG["generation"])
    with pytest.raises(ValueError, match="new run_id"):
        build.generate(log, MockClient(model="other"), few, CFG["generation"])


def test_select_problems_is_reproducible(problems):
    a = build.select_problems(problems, 40, 2026)
    assert len(a) == 40 and list(a) == [t for t in problems if t in a]  # dataset order
    assert list(a) == list(build.select_problems(problems, 40, 2026))
    assert list(a) != list(build.select_problems(problems, 40, 2027))


def test_problem_set_is_pinned_per_run(tmp_path):
    log = RunLog("pin", tmp_path)
    build.pin_problem_set(log, ["HumanEval/0", "HumanEval/1"])
    build.pin_problem_set(log, ["HumanEval/0", "HumanEval/1"])  # same set: fine
    with pytest.raises(ValueError, match="different problem set"):
        build.pin_problem_set(log, ["HumanEval/0"])


def test_cli_generate_sample_with_pilot_config(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIER_CONFIG", str(build.Path(__file__).resolve().parents[1]
                                              / "configs" / "pilot_local.toml"))
    args = ["generate", "--run-id", "p", "--backend", "mock", "--sample", "3",
            "--results", str(tmp_path)]
    assert build.main(args) == 0
    ids = json.loads((tmp_path / "p" / "problems.json").read_text())
    assert len(ids) == 3
    assert len(list(RunLog("p", tmp_path).records())) == 30
    assert build.main(args) == 0  # resume: same sample, no new calls
    with pytest.raises(ValueError, match="different problem set"):
        build.main(["generate", "--run-id", "p", "--backend", "mock", "--sample", "4",
                    "--results", str(tmp_path)])


def test_extract_solution_from_chat_response(few):
    p = few["HumanEval/23"]
    resp = MockCoder(few)._respond(build.build_prompt(p), seed=0)
    sol = build.extract_solution(resp, p["entry_point"])
    assert sol.startswith("def strlen") and "Here is" not in sol and "```" not in sol


@pytest.mark.linux
@pytest.mark.skipif(os.name != "posix", reason="labelling needs POSIX")
def test_label_end_to_end(tmp_path, few):
    log = RunLog("e2e", tmp_path)
    build.generate(log, MockCoder(few), few, CFG["generation"])
    meta = build.label(log, CFG)

    rows = [json.loads(l) for l in (tmp_path / "e2e" / "corpus.jsonl").read_text().splitlines()]
    assert len(rows) == meta["n_candidates"] == 30
    # MockCoder: seeds 0-2 canonical, 3 wrong, 4 syntax error; 2 temps x 3 problems
    assert meta["n_correct"] == 18
    by_seed = {s: {r["correct"] for r in rows if r["seed"] == s} for s in range(5)}
    assert by_seed == {0: {True}, 1: {True}, 2: {True}, 3: {False}, 4: {False}}
    assert all(r["failure_category"] is None for r in rows if r["correct"])
    assert {r["failure_category"] for r in rows if r["seed"] == 3} == {"wrong_output"}

    # Syntax errors: evalplus's sanitize repairs `return (` away, leaving a
    # docstring-only function (-> wrong_output), except HumanEval/0 where the
    # whole function is dropped (-> load error). The raw response is flagged.
    syn = [r for r in rows if r["seed"] == 4]
    assert all(not r["response_code_parses"] and r["sanitize_modified"] for r in syn)
    assert {(r["problem_id"], r["failure_category"]) for r in syn} == {
        ("HumanEval/0", "error"), ("HumanEval/23", "wrong_output"),
        ("HumanEval/53", "wrong_output")}
    assert meta["failure_categories"] == {"wrong_output": 10, "error": 2}
    assert meta["n_response_syntax_error"] == 6
    ok = [r for r in rows if r["seed"] < 3]
    assert all(r["response_code_parses"] for r in ok)
    assert meta["evalplus"]["commit"].startswith("6eb1e19")
    assert meta["labelling_workers"] == 1  # serial default from config
    assert meta["machine"]["hostname"] and meta["dataset_version"] == "v0.1.10"


@pytest.mark.linux
@pytest.mark.skipif(os.name != "posix", reason="labelling needs POSIX")
def test_label_skips_excluded_problems(tmp_path, problems):
    full = load_problems()
    sub = {t: full[t] for t in ("HumanEval/0", "HumanEval/32")}
    log = RunLog("excl", tmp_path)
    build.generate(log, MockCoder(sub), sub, {**CFG["generation"], "temperatures": [0.2]})
    meta = build.label(log, CFG)
    assert meta["skipped_excluded"] == {"HumanEval/32": 5}
    assert meta["n_candidates"] == 5
