from __future__ import annotations

from typing import Protocol


class Strategy(Protocol):
    name: str
    max_tokens: int

    def build_prompt(self, problem: dict, solution: str) -> str:
        """Prompt from the problem statement (signature + docstring) and the
        candidate code only. Must never include tests, labels or categories."""
        ...

    def parse_verdict(self, text: str) -> bool | None:
        """True = accept (judged correct), False = reject, None = no verdict."""
        ...
