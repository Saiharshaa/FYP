"""Verification strategies: judge a candidate from the problem statement and
code alone (never the hidden tests), returning a binary verdict.

Runtime-agnostic on purpose: the plan implements strategies as OpenClaw skills
behind a thin adapter, and that adapter should reuse these prompts and parsers.
Implemented: (a) "direct", its answer-order control "direct-swapped",
(b) "reason", and the execution-grounded (c) "self-tests" and (d) "reference"
(verifier.strategies.execution; verdicts come from running code, see
verifier.harness.exec_verdicts). (e) majority vote is computed from repeated
seeds in verifier.analysis.
"""

from verifier.strategies.base import Strategy
from verifier.strategies.execution import PER_PROBLEM, REFERENCE, SELF_TESTS
from verifier.strategies.judge import (
    DIRECT, DIRECT_SWAPPED, PARSERS, REASON, parse_verdict, parse_verdict_v2)

STRATEGIES: dict[str, Strategy] = {
    s.name: s for s in (DIRECT, DIRECT_SWAPPED, REASON, SELF_TESTS, REFERENCE)}
EXEC_STRATEGIES = {n for n, s in STRATEGIES.items() if getattr(s, "executes", False)}

__all__ = ["Strategy", "STRATEGIES", "EXEC_STRATEGIES", "PER_PROBLEM", "DIRECT",
           "DIRECT_SWAPPED", "REASON", "SELF_TESTS", "REFERENCE", "PARSERS",
           "parse_verdict", "parse_verdict_v2"]
