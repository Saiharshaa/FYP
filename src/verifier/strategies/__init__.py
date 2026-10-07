"""Verification strategies: judge a candidate from the problem statement and
code alone (never the hidden tests), returning a binary verdict.

Runtime-agnostic on purpose: the plan implements strategies as OpenClaw skills
behind a thin adapter, and that adapter should reuse these prompts and parsers.
Implemented so far: (a) "direct", its answer-order control "direct-swapped",
and (b) "reason". (e) majority vote is computed from repeated seeds in
verifier.analysis. (c)/(d) execute model-written code and are not implemented
yet.
"""

from verifier.strategies.base import Strategy
from verifier.strategies.judge import (
    DIRECT, DIRECT_SWAPPED, PARSERS, REASON, parse_verdict, parse_verdict_v2)

STRATEGIES: dict[str, Strategy] = {s.name: s for s in (DIRECT, DIRECT_SWAPPED, REASON)}

__all__ = ["Strategy", "STRATEGIES", "DIRECT", "DIRECT_SWAPPED", "REASON",
           "PARSERS", "parse_verdict", "parse_verdict_v2"]
