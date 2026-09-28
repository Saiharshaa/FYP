"""Offline stand-in for a generator model, for pipeline tests and dry runs.

Answers a build_prompt() prompt with a chat-style response (prose + markdown
code block). The variant depends only on seed % 5, so a run is reproducible:
  0, 1, 2   the canonical solution          -> correct
  3         `return None`                    -> wrong_output
  4         a syntax error                   -> error
"""

from __future__ import annotations

import re

from verifier.harness.client import MockClient

_FENCE = re.compile(r"```\n(.*?)\n```", re.S)


class MockCoder(MockClient):
    def __init__(self, problems: dict[str, dict], model: str = "mock-coder"):
        self._by_prompt = {p["prompt"].strip(): p for p in problems.values()}
        super().__init__(responder=self._respond, model=model)

    def _respond(self, prompt: str, seed: int) -> str:
        m = _FENCE.search(prompt)
        problem = self._by_prompt.get(m.group(1).strip()) if m else None
        if problem is None:
            return "I could not find a problem in the prompt."
        header = problem["prompt"].rstrip() + "\n"
        variant = seed % 5
        if variant <= 2:
            code = header + problem["canonical_solution"]
        elif variant == 3:
            code = header + "    return None\n"
        else:
            code = header + "    return (\n"
        return ("Here is a self-contained solution:\n\n```python\n" + code.rstrip()
                + "\n```\n\nThis handles the cases in the docstring.")

    def generate(self, prompt, temperature, seed, max_tokens):
        # Real responses are long; ignore max_tokens here so code is never cut.
        return super().generate(prompt, temperature, seed, max_tokens=10**9)
