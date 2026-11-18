import pytest

from verifier.analysis.metrics import Item
from verifier.analysis.selection import per_problem, selection


def items(pid, correct, verdicts):
    return [Item(pid, f"c{i}", c, v) for i, (c, v) in enumerate(zip(correct, verdicts))]


def test_per_problem_expected_values():
    # 4 candidates, 1 correct; verifier accepts the correct one and one wrong one
    pp = per_problem(items("P", [True, False, False, False], [True, True, False, None]))
    assert pp["P"] == (0.25, 0.5, 1.0)
    # nothing accepted -> falls back to random
    pp = per_problem(items("Q", [True, False], [False, None]))
    assert pp["Q"] == (0.5, 0.5, 1.0)


def test_perfect_verifier_captures_all_headroom_and_always_accept_none():
    corr = [True, False, False, True, False]
    perfect = items("A", corr, corr) + items("B", [False, True], [False, True])
    s = selection(perfect, n_boot=200)
    assert s["verifier"] == s["oracle"] == 1.0
    assert s["headroom_captured"] == pytest.approx(1.0)
    always = items("A", corr, [True] * 5) + items("B", [False, True], [True, True])
    assert selection(always, n_boot=200)["headroom_captured"] == pytest.approx(0.0)


def test_inverted_verifier_is_worse_than_random():
    corr = [True, False, False, False]
    inv = items("A", corr, [not c for c in corr])
    s = selection(inv, n_boot=200)
    assert s["verifier"] == 0.0 and s["headroom_captured"] < 0


def test_problems_without_headroom_do_not_divide_by_zero():
    all_right = items("A", [True, True], [False, True])
    all_wrong = items("B", [False, False], [True, False])
    s = selection(all_right + all_wrong, n_boot=50)
    assert s["random"] == s["verifier"] == 0.5 and s["oracle"] == 0.5
    assert s["headroom_captured"] is None and s["n_problems_with_headroom"] == 0


def test_bootstrap_ci_brackets_point_estimate():
    data = []
    for p in range(20):
        corr = [p % 3 == 0, True, False, False]
        verd = [c if p % 2 else True for c in corr]
        data += items(f"P{p}", corr, verd)
    s = selection(data, n_boot=500)
    lo, hi = s["ci95_headroom"]
    assert lo <= s["headroom_captured"] <= hi
