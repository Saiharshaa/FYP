"""Verifier reliability as a classification problem.

Conventions (used throughout the report):
  accept    verdict == CORRECT (the critic would pass the code downstream)
  TP        accept, code correct          FP  accept, code incorrect (false accept)
  TN        reject, code incorrect        FN  reject, code correct   (false reject)
  FAR = FP / (FP + TN)   share of incorrect code that is accepted
  FRR = FN / (FN + TP)   share of correct code that is rejected
  No verdict (abstention) counts as reject by default: a critic that does not
  say yes does not pass code. `abstain="exclude"` drops those items instead.
MCC is 0 when any margin is empty (e.g. always-accept), as in scikit-learn.
CIs: percentile bootstrap resampling *problems* (clusters), since candidates
of one problem are correlated.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Item:
    problem_id: str
    candidate_id: str
    correct: bool
    verdict: bool | None  # True accept, False reject, None no verdict


def confusion(items: Iterable[Item], abstain: str = "reject") -> dict[str, int]:
    if abstain not in ("reject", "exclude"):
        raise ValueError("abstain must be 'reject' or 'exclude'")
    c = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "abstain": 0}
    for it in items:
        if it.verdict is None:
            c["abstain"] += 1
            if abstain == "exclude":
                continue
        accept = it.verdict is True
        c[("tp" if it.correct else "fp") if accept else ("fn" if it.correct else "tn")] += 1
    return c


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def rates(c: dict[str, int]) -> dict[str, float | None]:
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    n = tp + fp + tn + fn
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "n": n,
        "accuracy": _div(tp + tn, n),
        "precision": _div(tp, tp + fp),
        "recall": _div(tp, tp + fn),
        "far": _div(fp, fp + tn),
        "frr": _div(fn, fn + tp),
        "accept_rate": _div(tp + fp, n),
        "mcc": (tp * tn - fp * fn) / denom if denom else 0.0,
    }


def score(items: list[Item], abstain: str = "reject") -> dict:
    c = confusion(items, abstain)
    return {**c, **rates(c), "abstain_rate": _div(c["abstain"], len(items))}


def cluster_bootstrap(items: list[Item], metric: Callable[[list[Item]], float | None],
                      n_boot: int = 2000, seed: int = 0,
                      alpha: float = 0.05) -> tuple[float, float] | None:
    by_problem: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_problem[it.problem_id].append(it)
    groups = [by_problem[k] for k in sorted(by_problem)]
    if not groups:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        sample = [it for _ in groups for it in rng.choice(groups)]
        v = metric(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    lo = vals[int(math.floor(alpha / 2 * (len(vals) - 1)))]
    hi = vals[int(math.ceil((1 - alpha / 2) * (len(vals) - 1)))]
    return lo, hi


CI_METRICS = ("accuracy", "far", "frr", "mcc")


def score_with_ci(items: list[Item], n_boot: int = 2000, seed: int = 0) -> dict:
    out = score(items)
    out["ci95"] = {m: cluster_bootstrap(items, lambda s, m=m: rates(confusion(s))[m],
                                        n_boot, seed)
                   for m in CI_METRICS}
    return out


def majority_vote(verdicts: list[bool | None]) -> bool:
    """Accept only on a strict majority of accepts; ties/abstentions reject."""
    return sum(v is True for v in verdicts) * 2 > len(verdicts)


def seed_spread(per_seed: dict[int, dict]) -> dict[str, dict[str, float]]:
    out = {}
    for m in ("accuracy", "far", "frr", "mcc"):
        vals = [s[m] for s in per_seed.values() if s[m] is not None]
        if vals:
            out[m] = {"mean": statistics.mean(vals),
                      "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0}
    return out
