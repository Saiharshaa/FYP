"""Confusion-matrix report for one verification run.

    python -m verifier.analysis.report --run-id verify-pilot-q15b --out reports/pilot-q15b

Joins results/<run>/log.jsonl (verdicts) with the corpus labels named in
verify_meta.json. Per strategy:
  single call   every (candidate, seed) call pooled over *complete* seeds
  vote          (e) strict-majority vote over those seeds, one verdict per candidate
  per seed      each seed separately, plus mean/sd across seeds
Metric definitions: verifier.analysis.metrics. Writes report.json + report.md
next to the log (and to --out).
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from verifier.analysis.metrics import (
    Item, majority_vote, score, score_with_ci, seed_spread)
from verifier.harness.runlog import RunLog
from verifier.harness.verify import load_corpus


def _items(rows: list[dict], verdicts: dict[tuple, bool | None]) -> list[Item]:
    return [Item(r["problem_id"], r["candidate_id"], r["correct"],
                 verdicts[(r["problem_id"], r["candidate_id"])]) for r in rows]


def _far(items: list[Item]) -> dict:
    inc = [i for i in items if not i.correct]
    acc = sum(i.verdict is True for i in inc)
    return {"n": len(inc), "accepted": acc, "far": acc / len(inc) if inc else None}


def corpus_summary(rows: list[dict], meta: dict) -> dict:
    by_t = defaultdict(list)
    for r in rows:
        by_t[r["temperature"]].append(r["correct"])
    return {
        "n_candidates": len(rows),
        "n_problems": len({r["problem_id"] for r in rows}),
        "n_correct": sum(r["correct"] for r in rows),
        "base_rate": sum(r["correct"] for r in rows) / len(rows) if rows else None,
        "pass_rate_by_temperature": {str(t): sum(v) / len(v) for t, v in sorted(by_t.items())},
        "failure_categories": dict(Counter(r["failure_category"] for r in rows
                                           if not r["correct"])),
        "n_response_syntax_error": sum(not r.get("response_code_parses", True) for r in rows),
        "n_truncated": sum(r.get("truncated", False) for r in rows),
        "generator_models": meta.get("models", []),
    }


def strategy_report(rows: list[dict], recs: list, n_boot: int) -> dict:
    by_seed: dict[int, dict[tuple, object]] = defaultdict(dict)
    for r in recs:
        by_seed[r.seed][(r.problem_id, r.candidate_id)] = r
    keys = {(r["problem_id"], r["candidate_id"]) for r in rows}
    complete = sorted(s for s, d in by_seed.items() if keys <= d.keys())
    partial = {s: len(keys & d.keys()) for s, d in by_seed.items() if s not in complete}
    out: dict = {"seeds_complete": complete, "seeds_partial": partial}
    if not complete:
        return out

    per_seed = {s: _items(rows, {k: by_seed[s][k].verdict for k in keys}) for s in complete}
    pooled = [i for s in complete for i in per_seed[s]]
    out["single_call"] = score_with_ci(pooled, n_boot)
    out["abstain_excluded"] = score(pooled, abstain="exclude")
    out["per_seed"] = {s: score(v) for s, v in per_seed.items()}
    out["seed_spread"] = seed_spread(out["per_seed"])
    if len(complete) >= 2:
        votes = {k: majority_vote([by_seed[s][k].verdict for s in complete]) for k in keys}
        out["vote"] = {**score_with_ci(_items(rows, votes), n_boot), "n_seeds": len(complete)}

    row_of = {(r["problem_id"], r["candidate_id"]): r for r in rows}
    groups: dict[str, dict] = {"category": defaultdict(list), "parses": defaultdict(list),
                               "temperature": defaultdict(list)}
    for it in pooled:
        r = row_of[(it.problem_id, it.candidate_id)]
        if not it.correct:
            groups["category"][r["failure_category"]].append(it)
            groups["parses"][str(r.get("response_code_parses", True))].append(it)
        groups["temperature"][str(r["temperature"])].append(it)
    out["far_by_failure_category"] = {k: _far(v) for k, v in sorted(groups["category"].items())}
    out["far_by_response_code_parses"] = {k: _far(v) for k, v in sorted(groups["parses"].items())}
    out["by_temperature"] = {k: score(v) for k, v in sorted(groups["temperature"].items())}

    calls = [by_seed[s][k] for s in complete for k in keys]
    out["cost"] = {
        "calls": len(calls),
        "mean_input_tokens": statistics.mean(c.input_tokens for c in calls),
        "mean_output_tokens": statistics.mean(c.output_tokens for c in calls),
        "mean_latency_s": statistics.mean(c.latency_s for c in calls),
        "truncated_calls": sum(c.finish_reason == "length" for c in calls),
    }
    return out


def build_report(results: str | Path, run_id: str, n_boot: int = 2000) -> dict:
    vdir = Path(results) / run_id
    vmeta = json.loads((vdir / "verify_meta.json").read_text())
    rows, cmeta = load_corpus(results, vmeta["corpus_run"])
    recs = defaultdict(list)
    for r in RunLog(run_id, results).records():
        recs[r.strategy].append(r)
    return {
        "verify_run": run_id, "corpus_run": vmeta["corpus_run"],
        "verifier_model": vmeta["verifier_model"], "condition": vmeta.get("condition"),
        "verification_config": vmeta["strategies"],
        "corpus": corpus_summary(rows, cmeta),
        "labelling": {k: cmeta.get(k) for k in ("evalplus", "dataset_version",
                                                "dataset_md5", "machine",
                                                "timeout_multiplier", "labelling_workers")},
        "baselines": {
            "always_accept": score(_items(rows, defaultdict(lambda: True))),
            "always_reject": score(_items(rows, defaultdict(lambda: False))),
        },
        "strategies": {s: strategy_report(rows, v, n_boot) for s, v in sorted(recs.items())},
        "n_boot": n_boot,
    }


# ------------------------------------------------------------------ markdown

def _p(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def _fmt(metric: str, x: float) -> str:
    return f"{x:.3f}" if metric == "mcc" else _p(x)


def _ci(s: dict, m: str, pct: bool = True) -> str:
    v, ci = s.get(m), (s.get("ci95") or {}).get(m)
    val = _p(v) if pct else ("–" if v is None else f"{v:.3f}")
    if not ci:
        return val
    lo, hi = (_p(ci[0]), _p(ci[1])) if pct else (f"{ci[0]:.3f}", f"{ci[1]:.3f}")
    return f"{val} [{lo}, {hi}]"


def to_markdown(rep: dict) -> str:
    c = rep["corpus"]
    L = [f"# Verifier reliability: `{rep['verify_run']}`", "",
         f"Corpus `{rep['corpus_run']}`: {c['n_candidates']} candidates on {c['n_problems']} "
         f"problems, {c['n_correct']} correct (base rate {_p(c['base_rate'])}). Generator "
         f"{', '.join(c['generator_models'])}; verifier `{rep['verifier_model']}` "
         f"(**{rep['condition']}-verification**).", "",
         "Accept = verdict CORRECT. FAR = share of incorrect code accepted; FRR = share of "
         "correct code rejected; no verdict counts as reject. 95% CIs: bootstrap over "
         f"problems ({rep['n_boot']} resamples).", "",
         "| Strategy | n | Accuracy | FAR (false accept) | FRR (false reject) | MCC | No verdict | Out tok | Latency |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, s in rep["strategies"].items():
        if "single_call" not in s:
            L.append(f"| {name} | incomplete: {s['seeds_partial']} | | | | | | | |")
            continue
        sc, cost = s["single_call"], s["cost"]
        L.append(f"| {name} (single call, seeds {s['seeds_complete']}) | {sc['n']} | "
                 f"{_ci(sc, 'accuracy')} | {_ci(sc, 'far')} | {_ci(sc, 'frr')} | "
                 f"{_ci(sc, 'mcc', False)} | {_p(sc['abstain_rate'])} | "
                 f"{cost['mean_output_tokens']:.0f} | {cost['mean_latency_s']:.1f}s |")
        if "vote" in s:
            v = s["vote"]
            L.append(f"| {name} majority vote ({v['n_seeds']} seeds) | {v['n']} | "
                     f"{_ci(v, 'accuracy')} | {_ci(v, 'far')} | {_ci(v, 'frr')} | "
                     f"{_ci(v, 'mcc', False)} | – | ×{v['n_seeds']} | ×{v['n_seeds']} |")
    for name, b in rep["baselines"].items():
        L.append(f"| baseline: {name.replace('_', ' ')} | {b['n']} | {_p(b['accuracy'])} | "
                 f"{_p(b['far'])} | {_p(b['frr'])} | {b['mcc']:.3f} | – | – | – |")

    for name, s in rep["strategies"].items():
        if "single_call" not in s:
            continue
        L += ["", f"## {name}", "", "False-accept rate by failure category (incorrect code only):", "",
              "| Category | n calls | Accepted | FAR |", "|---|---|---|---|"]
        for k, f in s["far_by_failure_category"].items():
            L.append(f"| {k} | {f['n']} | {f['accepted']} | {_p(f['far'])} |")
        L += ["", "By sampling temperature of the candidate:", "",
              "| T | n | Accuracy | FAR | FRR | MCC |", "|---|---|---|---|---|---|"]
        for t, sc in s["by_temperature"].items():
            L.append(f"| {t} | {sc['n']} | {_p(sc['accuracy'])} | {_p(sc['far'])} | "
                     f"{_p(sc['frr'])} | {sc['mcc']:.3f} |")
        parses = s["far_by_response_code_parses"]
        if parses:
            L += ["", "FAR by whether the model's own code block parsed "
                  "(sanitize repairs syntax errors):", ""]
            L += [f"- parses={k}: {f['accepted']}/{f['n']} accepted ({_p(f['far'])})"
                  for k, f in parses.items()]
        L += ["", "Across seeds (mean ± sd): " + "; ".join(
            f"{m} {_fmt(m, v['mean'])} ± {_fmt(m, v['sd'])}"
            for m, v in s["seed_spread"].items())]
        ex = s["abstain_excluded"]
        L.append(f"With no-verdict calls excluded ({ex['abstain']} dropped): accuracy "
                 f"{_p(ex['accuracy'])}, FAR {_p(ex['far'])}, FRR {_p(ex['frr'])}, MCC {ex['mcc']:.3f}.")
        L.append(f"Cost: {s['cost']['calls']} calls, mean {s['cost']['mean_input_tokens']:.0f} in / "
                 f"{s['cost']['mean_output_tokens']:.0f} out tokens, "
                 f"{s['cost']['truncated_calls']} truncated at max_tokens.")

    L += ["", "## Corpus", "",
          f"- Pass rate by temperature: " + ", ".join(
              f"T={t}: {_p(v)}" for t, v in c["pass_rate_by_temperature"].items()),
          f"- Failure categories: {c['failure_categories']}",
          f"- Model code blocks with syntax errors (before sanitize): {c['n_response_syntax_error']}",
          f"- Generations truncated at max_tokens: {c['n_truncated']}"]
    lab = rep["labelling"]
    if lab.get("evalplus"):
        L.append(f"- Labels: evalplus {lab['evalplus'].get('commit', '')[:7]}, HumanEvalPlus "
                 f"{lab.get('dataset_version')}, timeout ×{lab.get('timeout_multiplier')}, "
                 f"{lab.get('labelling_workers')} worker(s), host "
                 f"{(lab.get('machine') or {}).get('hostname')}")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verifier.analysis.report")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", help="also copy report.json/report.md here (tracked)")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args(argv)

    rep = build_report(args.results, args.run_id, args.n_boot)
    d = Path(args.results) / args.run_id
    (d / "report.json").write_text(json.dumps(rep, indent=2, default=str))
    (d / "report.md").write_text(to_markdown(rep))
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        for f in ("report.json", "report.md"):
            shutil.copy(d / f, Path(args.out) / f)
    print((d / "report.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
