import json

import pytest

from verifier.corpus.labelling import load_problems
from verifier.harness import verify as V
from verifier.harness.client import MockClient
from verifier.harness.runlog import RunLog, audit
from verifier.strategies import (
    DIRECT, DIRECT_SWAPPED, REASON, STRATEGIES, parse_verdict, parse_verdict_v2)


@pytest.fixture(scope="module")
def problems():
    return load_problems()


@pytest.fixture
def rows(problems):
    p = problems["HumanEval/23"]
    return [
        {"problem_id": "HumanEval/23", "candidate_id": "T0.2-0",
         "solution": "def strlen(string: str) -> int:\n    return len(string)\n", "correct": True},
        {"problem_id": "HumanEval/23", "candidate_id": "T0.8-1",
         "solution": "def strlen(string: str) -> int:\n    return 0\n", "correct": False},
    ]


@pytest.mark.parametrize("text,expected", [
    ("VERDICT: CORRECT", True),
    ("VERDICT: INCORRECT", False),
    ("verdict: correct", True),
    ("**VERDICT:** INCORRECT", False),
    ("VERDICT - CORRECT", True),
    ("The code looks fine.\nVERDICT: INCORRECT\n...\nVERDICT: CORRECT", True),  # last wins
    ("CORRECT", True),
    ("  Incorrect. The loop is off by one.", False),
    ("It is not clear whether this is correct.", None),  # 'correct' not leading, no VERDICT
    ("", None),
    ("VERDICT: MAYBE", None),
])
def test_parse_verdict(text, expected):
    assert parse_verdict(text) is expected


@pytest.mark.parametrize("text,v1,v2", [
    ("...the final verdict is:\n\\[\n\\boxed{\\text{CORRECT}}\n\\]", None, True),
    ("\\boxed{INCORRECT}", None, False),
    ("\\boxed{\\textbf{incorrect}}", None, False),
    ("\\boxed{CORRECT} ... on reflection\nVERDICT: INCORRECT", False, False),  # VERDICT line wins
    ("\\boxed{42}", None, None),
    ("VERDICT: CORRECT", True, True),
    ("Correct.", True, True),
])
def test_parser_v2_adds_boxed_only(text, v1, v2):
    assert parse_verdict(text) is v1
    assert parse_verdict_v2(text) is v2


def test_strategies_registered():
    assert set(STRATEGIES) == {"direct", "direct-swapped", "reason"}
    assert DIRECT.max_tokens < REASON.max_tokens == 768
    assert len({DIRECT.template_sha256, DIRECT_SWAPPED.template_sha256,
                REASON.template_sha256}) == 3


def test_swapped_control_differs_only_in_answer_order(problems):
    p, sol = problems["HumanEval/0"], "def f():\n    pass\n"
    a, b = DIRECT.build_prompt(p, sol), DIRECT_SWAPPED.build_prompt(p, sol)
    assert a.replace("VERDICT: CORRECT", "@").replace("VERDICT: INCORRECT", "VERDICT: CORRECT") \
            .replace("@", "VERDICT: INCORRECT") == b
    assert b.index("VERDICT: INCORRECT") < b.index("VERDICT: CORRECT")
    assert DIRECT_SWAPPED.max_tokens == DIRECT.max_tokens


@pytest.mark.parametrize("strategy", [DIRECT, REASON], ids=lambda s: s.name)
def test_prompt_contains_problem_and_code_but_no_tests(problems, strategy):
    p = problems["HumanEval/0"]
    sol = "def has_close_elements(numbers, threshold):\n    return False\n"
    prompt = strategy.build_prompt(p, sol)
    assert p["prompt"].strip() in prompt and sol.strip() in prompt
    assert "def check" not in prompt                       # original HumanEval test code
    for inp in p["plus_input"][:20]:                        # EvalPlus hidden inputs
        assert repr(inp) not in prompt
    assert prompt.rstrip().endswith("VERDICT: INCORRECT")


def test_tasks_are_seed_major(problems, rows):
    tasks = V.verification_tasks(rows, problems, DIRECT, [0, 1])
    assert [(t.seed, t.candidate_id) for t in tasks] == [
        (0, "T0.2-0"), (0, "T0.8-1"), (1, "T0.2-0"), (1, "T0.8-1")]
    assert all(t.strategy == "direct" for t in tasks)


def responder(prompt, seed):
    # accepts the real strlen, rejects `return 0`, no verdict on seed 2
    if seed == 2:
        return "I am not sure."
    return "VERDICT: INCORRECT" if "return 0" in prompt else "VERDICT: CORRECT"


def test_verify_logs_verdicts_and_resumes(tmp_path, problems, rows):
    log = RunLog("v", tmp_path)
    client = MockClient(responder, model="judge")
    args = dict(rows=rows, problems=problems, strategy=DIRECT, seeds=[0, 1, 2],
                temperature=0.7, corpus_run="c", corpus_meta={"models": ["gen"]})
    assert V.verify(log, client, **args) == 6
    assert V.verify(log, client, **args) == 0
    recs = {(r.candidate_id, r.seed): r for r in log.records()}
    assert recs[("T0.2-0", 0)].verdict is True
    assert recs[("T0.8-1", 1)].verdict is False
    assert recs[("T0.2-0", 2)].verdict is None
    assert all(r.max_tokens == DIRECT.max_tokens and r.temperature == 0.7
               for r in recs.values())
    tasks = V.verification_tasks(rows, problems, DIRECT, [0, 1, 2])
    assert audit(log, tasks) == {"duplicates": [], "missing": [], "unexpected": []}

    meta = json.loads((tmp_path / "v" / "verify_meta.json").read_text())
    assert meta["condition"] == "cross" and meta["verifier_model"] == "judge"
    assert meta["strategies"]["direct"]["seeds"] == [0, 1, 2]


def test_self_condition_and_guards(tmp_path, problems, rows):
    log = RunLog("v", tmp_path)
    args = dict(rows=rows, problems=problems, strategy=DIRECT, seeds=[0],
                temperature=0.7, corpus_meta={"models": ["same"]})
    V.verify(log, MockClient(responder, model="same"), corpus_run="c", **args)
    assert json.loads((tmp_path / "v" / "verify_meta.json").read_text())["condition"] == "self"
    with pytest.raises(ValueError, match="belongs to corpus"):
        V.verify(log, MockClient(responder, model="same"), corpus_run="other", **args)
    with pytest.raises(ValueError, match="uses verifier"):
        V.verify(log, MockClient(responder, model="different"), corpus_run="c", **args)
    with pytest.raises(ValueError, match="already run at T="):
        V.verify(log, MockClient(responder, model="same"), corpus_run="c",
                 **{**args, "temperature": 0.2})


def test_missing_corpus_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError, match="build label"):
        V.load_corpus(tmp_path, "nope")


def test_cli_with_mock_backend(tmp_path, rows):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "corpus.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    argv = ["--corpus", "c", "--run-id", "v", "--strategy", "reason", "--seeds", "0",
            "--backend", "mock", "--results", str(tmp_path)]
    assert V.main(argv) == 0
    recs = list(RunLog("v", tmp_path).records())
    assert len(recs) == 2 and all(r.strategy == "reason" for r in recs)
