import json
import math

import pytest

from verifier.analysis import report as R
from verifier.analysis.metrics import (
    Item, cluster_bootstrap, confusion, majority_vote, rates, score, seed_spread)
from verifier.corpus.labelling import load_problems
from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog
from verifier.harness.verify import verify
from verifier.strategies import DIRECT


def items_from(spec):
    # spec: list of (correct, verdict); one problem per item unless given
    return [Item(f"P{i % 4}", f"c{i}", c, v) for i, (c, v) in enumerate(spec)]


HAND = [(True, True)] * 3 + [(True, False)] + [(False, True)] * 2 + [(False, False)] * 4


def test_hand_computed_confusion_and_rates():
    c = confusion(items_from(HAND))
    assert c == {"tp": 3, "fp": 2, "tn": 4, "fn": 1, "abstain": 0}
    r = rates(c)
    assert r["accuracy"] == pytest.approx(0.7)
    assert r["precision"] == pytest.approx(3 / 5)
    assert r["recall"] == pytest.approx(3 / 4)
    assert r["far"] == pytest.approx(2 / 6)
    assert r["frr"] == pytest.approx(1 / 4)
    assert r["mcc"] == pytest.approx(10 / math.sqrt(600))


def test_degenerate_verifiers_have_zero_mcc():
    acc = rates(confusion(items_from([(c, True) for c, _ in HAND])))
    rej = rates(confusion(items_from([(c, False) for c, _ in HAND])))
    assert acc["far"] == 1 and acc["frr"] == 0 and acc["mcc"] == 0
    assert rej["far"] == 0 and rej["frr"] == 1 and rej["mcc"] == 0


def test_abstention_is_reject_by_default_or_excluded():
    its = items_from([(True, None), (False, None), (True, True), (False, False)])
    assert confusion(its) == {"tp": 1, "fp": 0, "tn": 2, "fn": 1, "abstain": 2}
    assert confusion(its, "exclude") == {"tp": 1, "fp": 0, "tn": 1, "fn": 0, "abstain": 2}
    assert score(its)["abstain_rate"] == 0.5
    with pytest.raises(ValueError):
        confusion(its, "ignore")


@pytest.mark.parametrize("votes,expected", [
    ([True, True, False], True), ([True, None, False], False), ([True, True], True),
    ([True, False], False), ([None, None, None], False), ([False, False, True], False)])
def test_majority_vote(votes, expected):
    assert majority_vote(votes) is expected


def test_cluster_bootstrap_is_deterministic_and_brackets_estimate():
    its = items_from(HAND * 5)
    m = lambda s: rates(confusion(s))["accuracy"]
    a = cluster_bootstrap(its, m, n_boot=500, seed=1)
    assert a == cluster_bootstrap(its, m, n_boot=500, seed=1)
    assert a[0] <= m(its) <= a[1]
    one_problem = [Item("P", f"c{i}", c, v) for i, (c, v) in enumerate(HAND)]
    lo, hi = cluster_bootstrap(one_problem, m, n_boot=50)
    assert lo == hi == pytest.approx(0.7)  # one cluster: no resampling variance


def test_seed_spread():
    sp = seed_spread({0: {"accuracy": 0.5, "far": 0.2, "frr": None, "mcc": 0.1},
                      1: {"accuracy": 0.7, "far": 0.4, "frr": None, "mcc": 0.3}})
    assert sp["accuracy"]["mean"] == pytest.approx(0.6)
    assert sp["far"]["sd"] == pytest.approx(math.sqrt(0.02))
    assert "frr" not in sp


# ------------------------------------------------------------- end to end

@pytest.fixture(scope="module")
def problems():
    return load_problems()


def make_corpus(tmp_path):
    rows = []
    for p in ("HumanEval/0", "HumanEval/23", "HumanEval/53"):
        for i, (correct, cat) in enumerate([(True, None), (True, None),
                                            (False, "wrong_output"), (False, "error")]):
            rows.append({"problem_id": p, "candidate_id": f"T{0.2 if i < 2 else 0.8}-{i}",
                         "temperature": 0.2 if i < 2 else 0.8, "correct": correct,
                         "failure_category": cat, "response_code_parses": cat != "error",
                         "solution": f"# {p} candidate {i} {'good' if correct else 'bad'}\n"})
    d = tmp_path / "corp"
    d.mkdir()
    (d / "corpus.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (d / "corpus_meta.json").write_text(json.dumps({"models": ["gen"]}))
    return rows


def judge(prompt, seed):
    # accepts all "good" code; accepts "bad" code only on seed 1 (a noisy critic)
    if "good" in prompt or seed == 1:
        return "VERDICT: CORRECT"
    return "VERDICT: INCORRECT"


def test_report_end_to_end(tmp_path, problems):
    rows = make_corpus(tmp_path)
    log = RunLog("ver", tmp_path)
    verify(log, MockClient(judge, model="judge"), rows, problems, DIRECT, [0, 1, 2], 0.7,
           corpus_run="corp", corpus_meta={"models": ["gen"]})
    rep = R.build_report(tmp_path, "ver", n_boot=200)
    s = rep["strategies"]["direct"]

    sc = s["single_call"]
    assert sc["tp"] + sc["fp"] + sc["tn"] + sc["fn"] == sc["n"] == len(rows) * 3
    assert sc["frr"] == 0 and sc["far"] == pytest.approx(1 / 3)  # bad code accepted on 1/3 seeds
    assert s["vote"]["far"] == 0 and s["vote"]["n"] == len(rows)  # majority removes the noise
    assert s["per_seed"][1]["far"] == 1 and s["per_seed"][0]["far"] == 0

    cats = s["far_by_failure_category"]
    assert sum(c["n"] for c in cats.values()) == 3 * sum(not r["correct"] for r in rows)
    assert rep["baselines"]["always_accept"]["far"] == 1
    assert rep["baselines"]["always_accept"]["mcc"] == 0
    assert rep["condition"] == "cross" and rep["corpus"]["base_rate"] == 0.5

    md = R.to_markdown(rep)
    assert "| Strategy |" in md and "majority vote (3 seeds)" in md and "wrong_output" in md


def test_partial_seed_is_excluded_from_pooled(tmp_path, problems):
    rows = make_corpus(tmp_path)
    log = RunLog("ver", tmp_path)
    client = MockClient(judge, model="judge")
    verify(log, client, rows, problems, DIRECT, [0], 0.7, corpus_run="corp")
    verify(log, client, rows[:5], problems, DIRECT, [1], 0.7, corpus_run="corp")  # partial
    s = R.build_report(tmp_path, "ver", n_boot=50)["strategies"]["direct"]
    assert s["seeds_complete"] == [0] and s["seeds_partial"] == {1: 5}
    assert s["single_call"]["n"] == len(rows) and "vote" not in s


def test_report_cli_writes_files(tmp_path, problems):
    rows = make_corpus(tmp_path)
    verify(RunLog("ver", tmp_path), MockClient(judge, model="judge"), rows, problems,
           DIRECT, [0], 0.7, corpus_run="corp")
    out = tmp_path / "reports"
    assert R.main(["--run-id", "ver", "--results", str(tmp_path), "--out", str(out),
                   "--n-boot", "50"]) == 0
    assert (out / "report.md").exists() and json.loads((out / "report.json").read_text())
