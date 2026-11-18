"""Strategies (c) self-tests and (d) reference: extraction, sandboxed
execution, decision rules and the report join."""

import json
import os

import pytest

from verifier.config import load_config
from verifier.corpus import build
from verifier.corpus.labelling import load_problems
from verifier.corpus.mock_coder import MockCoder
from verifier.harness import exec_verdicts
from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog
from verifier.harness.verify import load_corpus, verification_tasks, verify
from verifier.analysis.report import build_report, to_markdown
from verifier.strategies import EXEC_STRATEGIES, PER_PROBLEM, REFERENCE, SELF_TESTS
from verifier.strategies.execution import (
    decide, extract_asserts, extract_reference, read_result, reference_program,
    self_tests_program)

CFG = load_config()
posix = pytest.mark.skipif(os.name != "posix", reason="sandbox needs POSIX")

GOOD = "def add(x, y):\n    return x + y\n"
BAD = "def add(x, y):\n    return x - y\n"
LOOP = "def add(x, y):\n    while True:\n        pass\n"
TESTS_TEXT = """Sure:
```python
assert add(2, 3) == 5
assert add(0, 0) == 0
def add(x, y):          # must be ignored: would shadow the candidate
    return 5
def test_more():
    assert add(-1, 1) == 0
print("noise")
```"""
REF_TEXT = """```python
def reference(x, y):
    return sum([x, y])
def generate_inputs():
    return [(1, 2), (0, 0), (-3, 3), (10, -4), ("a", 1)]
```"""


# ------------------------------------------------------------ extraction

def test_extract_asserts_top_level_and_test_functions_only():
    got = extract_asserts(TESTS_TEXT)
    assert got == ["assert add(2, 3) == 5", "assert add(0, 0) == 0", "assert add(-1, 1) == 0"]


def test_extract_asserts_salvages_lines_from_broken_block():
    text = "```python\nassert add(1, 1) == 2\nassert add(1,\n```"
    assert extract_asserts(text) == ["assert add(1, 1) == 2"]
    assert extract_asserts("no code here") == []


UNITTEST_TEXT = """```python
import unittest

class TestAdd(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(add(2, 3), 5)
        self.assertTrue(add(1, 1) == 2)
        self.assertFalse(add(0, 0))
    def test_cut(self):
        self.assertEqual(add(1,
```"""
DOCTEST_TEXT = """```python
def add(x, y):
    \"\"\"
    >>> add(2, 3)
    5
    >>> add(-1, 1)
    0
    >>> add(1,
    \"\"\"
```"""


def test_extractor_v2_converts_unittest_and_doctest_formats():
    # Formats the 1.5B pilot model produced instead of plain asserts.
    assert extract_asserts(UNITTEST_TEXT) == []                # v1: nothing
    assert extract_asserts(UNITTEST_TEXT, version="v2") == [
        "assert add(2, 3) == 5", "assert add(1, 1) == 2", "assert not (add(0, 0))"]
    assert extract_asserts(DOCTEST_TEXT, version="v2") == [
        "assert (add(2, 3)) == (5)", "assert (add(-1, 1)) == (0)"]
    # v2 never overrides a v1 result
    assert extract_asserts(TESTS_TEXT, version="v2") == extract_asserts(TESTS_TEXT)


def test_extract_reference_needs_both_functions():
    assert extract_reference(REF_TEXT) is not None
    assert extract_reference("```python\ndef reference(x, y):\n    return x\n```") is None


def test_prompts_never_contain_the_candidate():
    p = {"prompt": 'def add(x: int, y: int):\n    """Add two numbers."""\n',
         "entry_point": "add"}
    for s in (SELF_TESTS, REFERENCE):
        prompt = s.build_prompt(p, "SECRET_CANDIDATE")
        assert "SECRET_CANDIDATE" not in prompt and "Add two numbers" in prompt
        assert s.parse_verdict("VERDICT: CORRECT") is None
    assert "reference(x, y)" in REFERENCE.build_prompt(p)


def test_exec_strategies_make_one_task_per_problem_and_seed():
    rows = [{"problem_id": p, "candidate_id": f"c{i}", "solution": "x"}
            for p in ("P/1", "P/2") for i in range(10)]
    problems = {p: {"prompt": "def f(a):\n    pass\n", "entry_point": "f"} for p in ("P/1", "P/2")}
    tasks = verification_tasks(rows, problems, SELF_TESTS, [0, 1, 2])
    assert len(tasks) == 6 and {t.candidate_id for t in tasks} == {PER_PROBLEM}
    assert EXEC_STRATEGIES == {"self-tests", "reference"}


# ------------------------------------------------------------ execution

@pytest.fixture(scope="module")
def sandbox():
    from verifier.sandbox import make_sandbox
    return make_sandbox(CFG["sandbox"])


def _run(sandbox, code, timeout=60):
    res = sandbox.run(code, timeout_s=timeout, memory_mb=1024)
    return read_result(res["stdout"]), res["timed_out"]


@pytest.mark.linux
@posix
def test_self_tests_accept_good_reject_bad_and_slow(sandbox):
    tests = extract_asserts(TESTS_TEXT)
    v, d = decide("self-tests", *_run(sandbox, self_tests_program(GOOD, tests)))
    assert v is True and d["n_pass"] == 3
    v, d = decide("self-tests", *_run(sandbox, self_tests_program(BAD, tests)))
    assert v is False and d["n_pass"] == 1          # add(0, 0) still passes
    v, d = decide("self-tests", *_run(sandbox, self_tests_program(LOOP, tests[:1])))
    assert v is False and d["fail_kinds"] == ["timeout"]
    v, d = decide("self-tests", *_run(sandbox, self_tests_program("def add(:\n", tests)))
    assert v is False and d["error"].startswith("candidate_load")


@pytest.mark.linux
@posix
def test_reference_differential_testing(sandbox):
    ref = extract_reference(REF_TEXT)
    v, d = decide("reference", *_run(sandbox, reference_program(GOOD, ref, "add")))
    assert v is True and d["n_used"] == 4 and d["n_inputs"] == 5   # ("a", 1) skipped
    v, d = decide("reference", *_run(sandbox, reference_program(BAD, ref, "add")))
    assert v is False and d["n_agree"] == 1                        # only (0, 0)
    broken = "def reference(x, y):\n    return x\ndef generate_inputs():\n    raise ValueError\n"
    v, d = decide("reference", *_run(sandbox, reference_program(GOOD, broken, "add")))
    assert v is None and d["error"] == "reference:ValueError"


def test_float_tolerance_and_missing_result():
    assert decide("self-tests", None, True) == (False, {"error": "timeout"})
    assert decide("reference", {"used": 0, "agree": 0, "n_inputs": 3,
                                "first_diff": None}, False)[0] is None


# ------------------------------------------------------------ end to end

ANSWERS = {
    "HumanEval/53": ("assert add(2, 3) == 5\nassert add(5, 7) == 12\nassert add(0, 0) == 0",
                     "def reference(x, y):\n    return x + y\n"
                     "def generate_inputs():\n    return [(1, 2), (0, 0), (5, 7), (-2, 9)]"),
    "HumanEval/23": ("assert strlen('') == 0\nassert strlen('abc') == 3",
                     "def reference(string):\n    n = 0\n    for _ in string:\n        n += 1\n"
                     "    return n\ndef generate_inputs():\n    return [('',), ('a',), ('abcd',)]"),
}


def _verifier_model(problems):
    by_prompt = {p["prompt"].strip(): pid for pid, p in problems.items()}

    def respond(prompt, seed):
        pid = next(i for s, i in by_prompt.items() if s in prompt)
        tests, ref = ANSWERS[pid]
        body = ref if "generate_inputs" in prompt else tests
        return f"```python\n{body}\n```"
    return MockClient(respond, model="mock-verifier")


@pytest.mark.linux
@posix
def test_exec_strategies_end_to_end(tmp_path):
    full = load_problems()
    few = {p: full[p] for p in ANSWERS}
    gen = RunLog("gen", tmp_path)
    build.generate(gen, MockCoder(few), few, {**CFG["generation"], "temperatures": [0.2]})
    build.label(gen, CFG)
    rows, meta = load_corpus(tmp_path, "gen")
    vlog = RunLog("ver", tmp_path)
    client = _verifier_model(few)
    for s in (SELF_TESTS, REFERENCE):
        made = verify(vlog, client, rows, few, s, [0, 1], 0.7, corpus_run="gen", corpus_meta=meta)
        assert made == 2 * len(few)                  # one call per problem and seed
    n = exec_verdicts.run(tmp_path, "ver", CFG)
    assert n == 2 * 2 * len(rows)                    # strategies x seeds x candidates
    assert exec_verdicts.run(tmp_path, "ver", CFG) == 0   # resume: nothing left

    rep = build_report(tmp_path, "ver", n_boot=50)
    for s in ("self-tests", "reference"):
        sc = rep["strategies"]["v1"][s]["single_call"]
        # MockCoder: seeds 0-2 canonical (accept), 3 wrong, 4 syntax error (reject)
        assert sc["accuracy"] == 1.0 and sc["far"] == 0.0 and sc["frr"] == 0.0
        assert rep["execution"][s]["no_verdict"] == 0
        assert "vote" in rep["strategies"]["v1"][s]
    assert rep["parser_check"]["v1_reparse_mismatches"] == 0
    md = to_markdown(rep)
    assert "self-tests [v1]" in md and "Execution strategy `reference`" in md
