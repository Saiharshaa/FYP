import os

import pytest

from verifier.corpus import labelling
from verifier.corpus.ground_truth_check import WRONG_SOLUTIONS

posix_only = pytest.mark.skipif(os.name != "posix",
                                reason="EvalPlus execution needs POSIX")


@pytest.fixture(scope="module")
def problems():
    return labelling.load_problems()


@pytest.fixture(scope="module")
def expected(problems):
    return labelling.load_expected(problems)


def test_dataset_is_pinned_version(problems):
    assert len(problems) == 164
    assert labelling.dataset_info()["version"] == "v0.1.10"


@pytest.mark.skipif(os.name == "posix", reason="guard only fires off-POSIX")
def test_refuses_to_label_on_windows(problems):
    with pytest.raises(RuntimeError, match="POSIX"):
        labelling.label_solution(problems["HumanEval/0"], "", {})


@pytest.mark.linux
@posix_only
@pytest.mark.parametrize("task_id", sorted(WRONG_SOLUTIONS))
def test_wrong_solution_fails(problems, expected, task_id):
    category, body = WRONG_SOLUTIONS[task_id]
    label = labelling.label_solution(
        problems[task_id], problems[task_id]["prompt"] + body, expected[task_id])
    assert not label.correct
    assert label.plus_status != "pass"
    if category == "timeout":
        assert label.base_status == "timeout"


@pytest.mark.linux
@posix_only
def test_single_canonical_passes(problems, expected):
    p = problems["HumanEval/0"]
    assert labelling.label_solution(
        p, labelling.canonical_solution(p), expected["HumanEval/0"]).correct


@pytest.mark.linux
@pytest.mark.slow
@posix_only
def test_all_canonical_solutions_pass(problems, expected):
    labels = labelling.label_many(
        [(t, labelling.canonical_solution(p)) for t, p in problems.items()],
        problems, expected)
    failures = [labelling.to_dict(l) for l in labels if not l.correct]
    assert failures == [], failures
