"""Judgement-only strategies (a) direct and (b) reason-then-judge."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_HEADER = """\
You are reviewing a candidate solution to a programming problem. The solution \
is correct only if it returns the right result for every valid input described \
by the problem, not just the examples in the docstring.

Problem:
```python
{problem}
```

Candidate solution:
```python
{solution}
```
"""

DIRECT_TEMPLATE = _HEADER + """
Do not explain. Reply with exactly one line:
VERDICT: CORRECT
or
VERDICT: INCORRECT
"""

REASON_TEMPLATE = _HEADER + """
Think step by step: restate what the function must do, consider edge cases, \
and check whether the code handles each of them. Then finish with exactly one \
final line:
VERDICT: CORRECT
or
VERDICT: INCORRECT
"""

# Control for answer-order bias: identical to DIRECT except that the two
# allowed answers are listed in the opposite order. Added 2026-10-07 after
# DIRECT answered "VERDICT: CORRECT" for 400/400 pilot candidates.
DIRECT_SWAPPED_TEMPLATE = _HEADER + """
Do not explain. Reply with exactly one line:
VERDICT: INCORRECT
or
VERDICT: CORRECT
"""

_VERDICT = re.compile(r"VERDICT\W{0,4}(INCORRECT|CORRECT)\b", re.I)
_LEADING = re.compile(r"^\W*(INCORRECT|CORRECT)\b", re.I)
_BOXED = re.compile(r"\\boxed\{\s*(?:\\text(?:bf)?\{\s*)?(INCORRECT|CORRECT)\b", re.I)


def parse_verdict(text: str) -> bool | None:
    """Parser v1 (pre-registered, used at run time and stored in the log).
    The last `VERDICT: X` wins; failing that, a reply that *starts* with the
    bare word CORRECT/INCORRECT. Anything else is no verdict (None)."""
    matches = _VERDICT.findall(text or "")
    word = matches[-1] if matches else None
    if word is None:
        m = _LEADING.match(text or "")
        word = m.group(1) if m else None
    return None if word is None else word.upper() == "CORRECT"


def parse_verdict_v2(text: str) -> bool | None:
    """Parser v2 (2026-10-07, applied post hoc to logged responses): v1, plus
    a LaTeX `\\boxed{CORRECT}` / `\\boxed{\\text{INCORRECT}}` answer when no
    `VERDICT:` line is present. Added because the 1.5B model often ends its
    reasoning with a boxed verdict instead of the requested line."""
    matches = _VERDICT.findall(text or "")
    if matches:
        return matches[-1].upper() == "CORRECT"
    boxed = _BOXED.findall(text or "")
    if boxed:
        return boxed[-1].upper() == "CORRECT"
    return parse_verdict(text)


PARSERS = {"v1": parse_verdict, "v2": parse_verdict_v2}


@dataclass(frozen=True)
class JudgeStrategy:
    name: str
    template: str
    max_tokens: int

    def build_prompt(self, problem: dict, solution: str) -> str:
        return self.template.format(problem=problem["prompt"].strip(),
                                    solution=solution.strip())

    def parse_verdict(self, text: str) -> bool | None:
        return parse_verdict(text)

    @property
    def template_sha256(self) -> str:
        return hashlib.sha256(self.template.encode()).hexdigest()


DIRECT = JudgeStrategy("direct", DIRECT_TEMPLATE, max_tokens=16)
REASON = JudgeStrategy("reason", REASON_TEMPLATE, max_tokens=768)
DIRECT_SWAPPED = JudgeStrategy("direct-swapped", DIRECT_SWAPPED_TEMPLATE, max_tokens=16)
