"""Execution-grounded strategies (c) self-tests and (d) differential testing.

Both are *per problem*: the verifier model sees only the problem statement
(never the candidate, never the hidden tests) and writes, once per
(problem, seed):

  (c) "self-tests"  assert statements that a correct solution must pass;
  (d) "reference"   a deliberately simple brute-force `reference(...)` with the
                    same signature, plus `generate_inputs()` returning small
                    argument tuples, against which each candidate is
                    differentially tested.

The same model output is then applied to every candidate of that problem.
Writing tests from the specification alone (as in CodeT) keeps them from
being anchored on any one candidate, and needs 10x fewer model calls than
per-candidate prompting.

Model calls happen in `verifier.harness.verify` (safe on GPU hosts); the code
the model wrote, and the candidates, run only in `verifier.harness.exec_verdicts`
inside the sandbox (WSL2). Verdicts therefore come from exec.jsonl, not from
parsing the response: `parse_verdict` returns None at run time.

Pre-registered decision rules (2026-11-18):
  (c) accept iff every extracted assert passes (each assert runs separately,
      2 s each); no extractable assert -> no verdict.
  (d) accept iff the candidate agrees with `reference` on every input where
      `reference` itself returns within 2 s without raising; floats compare
      with rel/abs tolerance 1e-6; no usable input -> no verdict.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass

PER_PROBLEM = "__problem__"          # candidate_id of per-problem model calls
MARK = "@@VERIFIER_EXEC@@"           # prefix of the runner's result line
MAX_TESTS = 30
MAX_INPUTS = 50
PER_CALL_S = 2.0

SELF_TESTS_TEMPLATE = """\
Write unit tests for the following Python function. You will NOT see any \
implementation; write tests purely from the specification below.

```python
{problem}
```

Requirements:
- Output one ```python code block containing only top-level `assert` \
statements, one per line, each calling `{entry_point}` directly, e.g. \
`assert {entry_point}(...) == ...`.
- Write 8 to 15 tests. Cover the docstring examples, edge cases (empty or \
minimal inputs, boundaries, duplicates, negative numbers where allowed) and a \
few typical cases.
- Only use inputs the specification allows, and only assert results you are \
certain of.
- Do not define `{entry_point}` or any other function; no explanations outside \
the code block.
"""

REFERENCE_TEMPLATE = """\
You are building an oracle to check implementations of the following Python \
function by differential testing:

```python
{problem}
```

Write one ```python code block that defines exactly two functions:
1. `reference({params})`: a deliberately simple, obviously correct \
implementation (brute force is fine and preferred over clever code; it only \
needs to be fast on small inputs).
2. `generate_inputs()`: returns a list of 20 to 40 tuples, each tuple being \
the positional arguments for one call. Include the docstring examples, edge \
cases (empty or minimal inputs, boundaries, duplicates, negative numbers \
where allowed) and small random-looking cases. Only include inputs the \
specification allows. Keep every input small.

Use only the Python standard library. No explanations outside the code block.
"""

_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S | re.I)


def last_code_block(text: str) -> str | None:
    blocks = _BLOCK.findall(text or "")
    if blocks:
        return blocks[-1]
    m = re.search(r"```(?:python|py)?\s*\n(.*)$", text or "", re.S | re.I)  # unterminated
    return m.group(1) if m else None


_UNITTEST = {   # self.<method>(args) -> assert template (post hoc, extractor v2)
    "assertEqual": "{0} == {1}", "assertEquals": "{0} == {1}",
    "assertListEqual": "{0} == {1}", "assertTupleEqual": "{0} == {1}",
    "assertDictEqual": "{0} == {1}", "assertSetEqual": "{0} == {1}",
    "assertNotEqual": "{0} != {1}", "assertTrue": "{0}", "assertFalse": "not ({0})",
    "assertIsNone": "{0} is None", "assertIsNotNone": "{0} is not None",
    "assertIn": "{0} in {1}", "assertNotIn": "{0} not in {1}",
    "assertAlmostEqual": "round(abs(({0}) - ({1})), 7) == 0",
}
_DOCTEST = re.compile(r"^\s*>>>\s?(.+)\n\s*(?!>>>)(\S.*)$", re.M)


def _unittest_asserts(code: str) -> list[str]:
    """`self.assertX(a, b, ...)` calls anywhere in the code -> assert statements."""
    try:
        nodes = ast.walk(ast.parse(code))
    except SyntaxError:      # truncated block: convert the lines that parse alone
        nodes = []
        for line in code.splitlines():
            try:
                nodes += list(ast.walk(ast.parse(line.strip())))
            except SyntaxError:
                pass
    out = []
    for n in nodes:
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
                and n.func.attr in _UNITTEST and n.args):
            args = [ast.unparse(a) for a in n.args]
            tmpl = _UNITTEST[n.func.attr]
            if "{1}" in tmpl and len(args) < 2:
                continue
            out.append("assert " + tmpl.format(*args))
    return out


def _doctest_asserts(code: str) -> list[str]:
    """`>>> expr` followed by an expected-output line -> `assert expr == expected`."""
    out = []
    for expr, want in _DOCTEST.findall(code):
        stmt = f"assert ({expr.strip()}) == ({want.strip()})"
        try:
            ast.parse(stmt)
            out.append(stmt)
        except SyntaxError:
            pass
    return out


def extract_asserts(text: str, limit: int = MAX_TESTS, version: str = "v1") -> list[str]:
    """Tests from the last code block.

    v1 (pre-registered): top-level assert statements, plus asserts in the body
    of `def test_*()`; any other code (including a re-definition of the
    function under test) is ignored.
    v2 (post hoc, 2026-11-18, reported alongside v1): v1, and if v1 finds
    nothing, unittest `self.assertX(...)` calls and doctest `>>> expr` /
    expected-output pairs converted to asserts. Added because the 1.5B pilot
    model often answered in those formats instead of plain asserts.
    """
    v1 = _extract_v1(text, limit)
    if version == "v1" or v1:
        return v1
    code = last_code_block(text) or ""
    return (_unittest_asserts(code) or _doctest_asserts(code))[:limit]


EXTRACTORS = ("v1", "v2")


def _extract_v1(text: str, limit: int) -> list[str]:
    code = last_code_block(text)
    if code is None:
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # keep the assert lines that parse on their own
        out = []
        for line in code.splitlines():
            s = line.strip()
            if s.startswith("assert "):
                try:
                    ast.parse(s)
                    out.append(s)
                except SyntaxError:
                    pass
        return out[:limit]
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assert):
            out.append(ast.unparse(node))
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            out += [ast.unparse(n) for n in node.body if isinstance(n, ast.Assert)]
    return out[:limit]


def extract_reference(text: str) -> str | None:
    """The last code block, if it defines both `reference` and `generate_inputs`."""
    code = last_code_block(text)
    if code is None:
        return None
    try:
        names = {n.name for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
    except SyntaxError:
        return None
    return code if {"reference", "generate_inputs"} <= names else None


def _params(problem: dict) -> str:
    """Parameter list of the entry point, from the problem's signature."""
    try:
        tree = ast.parse(problem["prompt"])
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == problem["entry_point"]:
                return ", ".join(a.arg for a in n.args.args)
    except SyntaxError:
        pass
    return "..."


@dataclass(frozen=True)
class ExecStrategy:
    name: str
    template: str
    max_tokens: int
    per_problem: bool = True
    executes: bool = True

    def build_prompt(self, problem: dict, solution: str = "") -> str:
        # `solution` is deliberately unused: tests come from the spec alone.
        return self.template.format(problem=problem["prompt"].strip(),
                                    entry_point=problem["entry_point"],
                                    params=_params(problem))

    def parse_verdict(self, text: str) -> bool | None:
        return None   # verdicts come from execution (exec.jsonl)

    @property
    def template_sha256(self) -> str:
        return hashlib.sha256(self.template.encode()).hexdigest()


SELF_TESTS = ExecStrategy("self-tests", SELF_TESTS_TEMPLATE, max_tokens=1024)
REFERENCE = ExecStrategy("reference", REFERENCE_TEMPLATE, max_tokens=1536)


# ------------------------------------------------------- in-sandbox runners
# Both runners receive their inputs as JSON literals, so neither the model's
# code nor the candidate can break out of the string; they print one result
# line prefixed with MARK.

_PRELUDE = """\
import json, math, signal, sys, copy, itertools, collections, functools, re, string
MARK = {mark!r}
def _alarm(s, f): raise TimeoutError()
signal.signal(signal.SIGALRM, _alarm)
def _limited(fn, secs):
    signal.setitimer(signal.ITIMER_REAL, secs)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
def _emit(d):
    sys.stdout.flush()
    print(MARK + json.dumps(d))
CAND = json.loads({cand!r})
cns = {{"__name__": "candidate"}}
try:
    _limited(lambda: exec(CAND, cns), 10)
except BaseException as e:
    _emit({{"candidate_load_error": type(e).__name__}}); sys.exit(0)
"""

SELF_TESTS_RUNNER = _PRELUDE + """\
TESTS = json.loads({tests!r})
res = []
for t in TESTS:
    try:
        _limited(lambda: exec(t, dict(cns)), {per})
        res.append([True, None])
    except AssertionError:
        res.append([False, "assert"])
    except TimeoutError:
        res.append([False, "timeout"])
    except BaseException as e:
        res.append([False, type(e).__name__])
_emit({{"results": res}})
"""

REFERENCE_RUNNER = _PRELUDE + """\
REF = json.loads({ref!r})
ENTRY = {entry!r}
rns = {{"__name__": "reference"}}
try:
    _limited(lambda: exec(REF, rns), 10)
    inputs = _limited(lambda: list(rns["generate_inputs"]()), 10)
except BaseException as e:
    _emit({{"reference_error": type(e).__name__}}); sys.exit(0)

def _close(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6) or (a != a and b != b)
        except TypeError:
            return False
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) == type(b) and len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    return a == b

used = agree = 0
first_diff = None
for args in inputs[:{max_inputs}]:
    if not isinstance(args, tuple):
        args = (args,)
    try:
        want = _limited(lambda: rns["reference"](*copy.deepcopy(args)), {per})
    except BaseException:
        continue                      # reference cannot handle it: skip input
    used += 1
    try:
        got = _limited(lambda: cns[ENTRY](*copy.deepcopy(args)), {per})
        ok = _close(got, want)
    except BaseException as e:
        ok, got = False, type(e).__name__
    agree += ok
    if not ok and first_diff is None:
        first_diff = repr(args)[:200]
_emit({{"used": used, "agree": agree, "n_inputs": len(inputs), "first_diff": first_diff}})
"""


def self_tests_program(candidate: str, tests: list[str]) -> str:
    return SELF_TESTS_RUNNER.format(mark=MARK, cand=json.dumps(candidate),
                                    tests=json.dumps(tests), per=PER_CALL_S)


def reference_program(candidate: str, reference: str, entry_point: str) -> str:
    return REFERENCE_RUNNER.format(mark=MARK, cand=json.dumps(candidate),
                                   ref=json.dumps(reference), entry=entry_point,
                                   per=PER_CALL_S, max_inputs=MAX_INPUTS)


def read_result(stdout: str) -> dict | None:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(MARK):
            try:
                return json.loads(line[len(MARK):])
            except json.JSONDecodeError:
                return None
    return None


def decide(strategy: str, result: dict | None, timed_out: bool) -> tuple[bool | None, dict]:
    """Verdict + details from a runner result (pre-registered rules above)."""
    if result is None:
        # The runner died without reporting (e.g. memory limit, or a hang the
        # per-call alarm could not interrupt): blame the candidate.
        return False, {"error": "timeout" if timed_out else "no_result"}
    if "candidate_load_error" in result:
        return False, {"error": "candidate_load:" + result["candidate_load_error"]}
    if strategy == "self-tests":
        res = result["results"]
        if not res:
            return None, {"n_tests": 0}
        passed = sum(ok for ok, _ in res)
        return passed == len(res), {"n_tests": len(res), "n_pass": passed,
                                    "fail_kinds": sorted({e for ok, e in res if not ok})}
    if strategy == "reference":
        if "reference_error" in result:
            return None, {"error": "reference:" + result["reference_error"]}
        if result["used"] == 0:
            return None, {"n_used": 0, "n_inputs": result["n_inputs"]}
        return result["agree"] == result["used"], {
            "n_inputs": result["n_inputs"], "n_used": result["used"],
            "n_agree": result["agree"], "first_diff": result["first_diff"]}
    raise ValueError(f"unknown execution strategy {strategy!r}")
