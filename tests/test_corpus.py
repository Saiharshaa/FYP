import os

import pytest

from verifier.config import load_config
from verifier.corpus import labelling
from verifier.corpus.categorise import categorise, machine_info
from verifier.corpus.ground_truth_check import WRONG_SOLUTIONS

posix_only = pytest.mark.skipif(os.name != "posix",
                                reason="EvalPlus execution needs POSIX")
PINNED_EVALPLUS = "6eb1e199c2e370518e7bf3e8eee6322c2b23c89c"
CFG = load_config()


@pytest.fixture(scope="module")
def problems():
    return labelling.load_problems(CFG["corpus"]["exclude"])


@pytest.fixture(scope="module")
def expected(problems):
    return labelling.load_expected(problems)


@pytest.fixture(scope="module")
def sandbox():
    from verifier.sandbox import make_sandbox
    return make_sandbox(CFG["sandbox"])


def label(problems, expected, sandbox, task_id, body):
    p = problems[task_id]
    sol = p["prompt"] + body
    lab = labelling.label_solution(p, sol, expected[task_id])
    return categorise(lab, p, sol, expected[task_id], sandbox,
                      CFG["labelling"]["timeout_multiplier"], CFG["labelling"]["memory_mb"])


def test_dataset_is_pinned_version():
    assert len(labelling.load_problems()) == 164
    assert labelling.dataset_info()["version"] == "v0.1.10"


def test_evalplus_is_pinned_commit():
    assert labelling.evalplus_info()["commit"] == PINNED_EVALPLUS


def test_exclusion_from_config(problems):
    assert CFG["corpus"]["exclude"] == ["HumanEval/32"]
    assert "HumanEval/32" not in problems and len(problems) == 163
    with pytest.raises(ValueError, match="not in dataset"):
        labelling.load_problems(["HumanEval/999"])


def test_timeout_multiplier_is_configured():
    assert CFG["labelling"]["timeout_multiplier"] == 5


@pytest.mark.skipif(os.name == "posix", reason="guard only fires off-POSIX")
def test_refuses_to_label_on_windows():
    with pytest.raises(RuntimeError, match="POSIX"):
        labelling.label_solution({"task_id": "x"}, "", {})


@pytest.mark.linux
@posix_only
@pytest.mark.parametrize("task_id", sorted(WRONG_SOLUTIONS))
def test_wrong_solution_fails_and_is_categorised(problems, expected, sandbox, task_id):
    category, body = WRONG_SOLUTIONS[task_id]
    lab = label(problems, expected, sandbox, task_id, body)
    assert not lab.correct
    assert lab.base_status == "fail"  # raw evalplus status, incl. the infinite loop
    assert lab.failure_category == category, lab.rerun


@pytest.mark.linux
@posix_only
def test_rerun_uses_multiplied_limit(problems, expected, sandbox):
    lab = label(problems, expected, sandbox, "HumanEval/13", "    while True:\n        pass\n")
    r = lab.rerun
    assert r["limit_s"] == pytest.approx(r["evalplus_limit_s"] * 5)
    assert r["status"] == "timeout" and r["seconds"] >= r["limit_s"] * 0.99


@pytest.mark.linux
@posix_only
def test_slow_but_correct_is_not_a_timeout(problems, expected, sandbox):
    # Exceeds evalplus's 1 s per-test limit, finishes well inside 5x, right answer.
    body = "    import time\n    time.sleep(1.5)\n    return len(string)\n"
    lab = label(problems, expected, sandbox, "HumanEval/23", body)
    assert not lab.correct and lab.base_status == "fail"
    assert lab.failure_category == "slow", lab.rerun


@pytest.mark.linux
@posix_only
@pytest.mark.parametrize("body", [
    "    raise ValueError('boom')\n",
    "    return undefined_name\n",
    "    return len(string\n",  # syntax error: fails at load
], ids=["raises", "name-error", "syntax-error"])
def test_errors_are_categorised(problems, expected, sandbox, body):
    lab = label(problems, expected, sandbox, "HumanEval/23", body)
    assert not lab.correct and lab.failure_category == "error", lab.rerun


@pytest.mark.linux
@posix_only
def test_correct_solution_has_no_category(problems, expected, sandbox):
    p = problems["HumanEval/0"]
    lab = labelling.label_solution(p, labelling.canonical_solution(p), expected["HumanEval/0"])
    lab = categorise(lab, p, labelling.canonical_solution(p), expected["HumanEval/0"],
                     sandbox, 5, 4096)
    assert lab.correct and lab.failure_category is None and lab.rerun is None


@pytest.mark.linux
@posix_only
def test_machine_is_recorded(sandbox):
    info = machine_info(sandbox)
    assert info["hostname"] and info["cpu_count"] and info["sandbox"] == sandbox.name


@pytest.mark.linux
@pytest.mark.slow
@posix_only
def test_all_canonical_solutions_pass(problems, expected):
    labels = labelling.label_many(
        [(t, labelling.canonical_solution(p)) for t, p in problems.items()],
        problems, expected)
    failures = [labelling.to_dict(l) for l in labels if not l.correct]
    assert failures == [], failures
