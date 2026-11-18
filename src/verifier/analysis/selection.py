"""RQ4 selection experiment: how much of the achievable gain does a verifier
capture when it is used to pick one candidate per problem?

For each problem with k candidates (c of them correct), three policies:
  random    pick uniformly                      -> expected pass c / k
  verifier  pick uniformly among the accepted    -> (correct accepted) / (accepted);
            candidates; if none is accepted,        no accept falls back to c / k
            pick uniformly among all
  oracle    pick a correct one if any exists     -> 1 if c > 0 else 0
Expected values are exact (no sampling). Over problems:
  headroom captured = (verifier - random) / (oracle - random)
0 = no better than random, 1 = as good as the oracle, < 0 = worse than random.
95% CI: bootstrap over problems (resampling problem-level values, so a
problem drawn twice is counted twice rather than merged).
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict


def per_problem(items) -> dict[str, tuple[float, float, float]]:
    """problem_id -> (random, verifier, oracle) expected pass rates.
    items: objects with problem_id, correct, verdict (True = accepted)."""
    by_p: dict[str, list] = defaultdict(list)
    for it in items:
        by_p[it.problem_id].append(it)
    out = {}
    for pid, its in by_p.items():
        k = len(its)
        c = sum(it.correct for it in its)
        rnd = c / k
        acc = [it for it in its if it.verdict is True]
        ver = sum(it.correct for it in acc) / len(acc) if acc else rnd
        out[pid] = (rnd, ver, 1.0 if c else 0.0)
    return out


def _summary(vals: list[tuple[float, float, float]]) -> dict:
    r, v, o = (statistics.mean(x[i] for x in vals) for i in range(3))
    return {"random": r, "verifier": v, "oracle": o,
            "headroom_captured": (v - r) / (o - r) if o > r else None}


def selection(items, n_boot: int = 2000, seed: int = 0) -> dict:
    pp = per_problem(items)
    vals = [pp[k] for k in sorted(pp)]
    if not vals:
        return {}
    out = _summary(vals)
    out["n_problems"] = len(vals)
    out["n_problems_no_accept"] = sum(1 for k in pp if not any(
        it.verdict is True for it in items if it.problem_id == k))
    out["n_problems_with_headroom"] = sum(1 for r, _, o in vals if o > r)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        s = _summary([rng.choice(vals) for _ in vals])
        if s["headroom_captured"] is not None:
            boots.append(s["headroom_captured"])
    if boots:
        boots.sort()
        out["ci95_headroom"] = (boots[int(math.floor(0.025 * (len(boots) - 1)))],
                                boots[int(math.ceil(0.975 * (len(boots) - 1)))])
    return out
