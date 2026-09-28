"""Derive failure_category for failing candidates by re-running in our sandbox.

evalplus records a per-test time-limit breach as "fail", so its status cannot
distinguish timeouts from wrong answers. For a failing candidate we re-run its
first failing input in the sandbox with a fixed limit of

    evalplus per-test limit  x  [labelling] timeout_multiplier   (default 5)

where the evalplus limit is max(1.0 s, 4 x canonical runtime on this host).

failure_category (derived; the raw evalplus status stays the correctness label):
  None            candidate is correct
  "timeout"       the re-run exceeded the fixed limit
  "error"         raised, or failed to load (syntax/import/name errors,
                  MemoryError, RecursionError, sys.exit, ...)
  "wrong_output"  returned within the limit, output differs from expected
  "slow"          returned within the limit with the expected output: evalplus
                  failed it on its (tighter) time limit, but it is not a timeout
  "unknown"       no failing input could be identified (evalplus failed the
                  suite but recorded every test as passed)
The plan's manual categories (wrong algorithm / implementation bug / edge
case) subdivide "wrong_output" and "error" and are assigned by hand later.
"""

from __future__ import annotations

import base64
import json
import os
import pickle
import platform
import socket
import sys
from dataclasses import replace

from evalplus.config import DEFAULT_GT_TIME_LIMIT_FACTOR, DEFAULT_MIN_TIME_LIMIT

from verifier.corpus.labelling import Label
from verifier.sandbox import Sandbox

RESULT_MARKER = "__VERIFIER_RERUN__"

# Runs inside the sandbox. The limit is enforced around the call only (SIGALRM),
# so interpreter start-up does not count; the sandbox's own timeout is a backstop.
_CHILD = r'''
import base64, io, json, math, pickle, signal, sys, time
P = pickle.loads(base64.b64decode("{payload}"))
OUT = sys.stdout
def emit(**k):
    OUT.write("\n{marker}" + json.dumps(k) + "\n"); OUT.flush()
class _Limit(BaseException):
    pass
def _alarm(signum, frame):
    raise _Limit()
def isfloats(x):
    return isinstance(x, float) or (isinstance(x, (list, tuple)) and len(x) > 0
                                    and all(isinstance(i, float) for i in x))
def matches(out, exp):
    # Mirrors evalplus unsafe_execute's comparison (pure Python; no numpy).
    if P["entry_point"] == "find_zero":
        xs = P["input"][0]
        return abs(sum(c * math.pow(out, i) for i, c in enumerate(xs))) <= P["atol"]
    if out == exp:
        return True
    atol = P["atol"] or (1e-6 if isfloats(exp) else 0)
    if not atol or type(out) is not type(exp):
        return False
    a, b = (list(out), list(exp)) if isinstance(exp, (list, tuple)) else ([out], [exp])
    if len(a) != len(b):
        return False
    try:
        return all(abs(x - y) <= atol + 1e-7 * abs(y) for x, y in zip(a, b))
    except TypeError:
        return False
sys.stdout = sys.stderr = io.StringIO()   # swallow candidate output, like evalplus
try:
    g = {{}}
    exec(compile(P["code"], "<candidate>", "exec"), g)
    fn = g[P["entry_point"]]
except BaseException as e:
    emit(status="error", phase="load", error_type=type(e).__name__)
    raise SystemExit(0)
signal.signal(signal.SIGALRM, _alarm)
t0 = time.perf_counter()
signal.setitimer(signal.ITIMER_REAL, P["limit_s"])
try:
    out = fn(*P["input"])
    signal.setitimer(signal.ITIMER_REAL, 0)
except _Limit:
    emit(status="timeout", seconds=time.perf_counter() - t0)
    raise SystemExit(0)
except BaseException as e:
    signal.setitimer(signal.ITIMER_REAL, 0)
    emit(status="error", phase="call", error_type=type(e).__name__,
         seconds=time.perf_counter() - t0)
    raise SystemExit(0)
dt = time.perf_counter() - t0
try:
    ok = bool(matches(out, P["expected"]))
except BaseException:
    ok = False
emit(status="returned", seconds=dt, matches=ok)
'''


def evalplus_limit(expected: dict, suite: str, index: int) -> float:
    ref = expected[f"{suite}_time"][index]
    return max(DEFAULT_MIN_TIME_LIMIT, DEFAULT_GT_TIME_LIMIT_FACTOR * ref)


def rerun_script(problem: dict, solution: str, expected: dict, suite: str,
                 index: int, limit_s: float) -> str:
    payload = {"code": solution, "entry_point": problem["entry_point"],
               "input": problem[f"{suite}_input"][index],
               "expected": expected[suite][index],
               "atol": problem["atol"], "limit_s": limit_s}
    b64 = base64.b64encode(pickle.dumps(payload)).decode()
    return _CHILD.format(payload=b64, marker=RESULT_MARKER)


def _parse(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])
    return None


def categorise(label: Label, problem: dict, solution: str, expected: dict,
               sandbox: Sandbox, timeout_multiplier: float,
               memory_mb: int, startup_grace_s: float = 10.0) -> Label:
    """Return `label` with failure_category and rerun details filled in."""
    if label.correct:
        return label
    suite, index = label.failing_suite, label.failing_index
    if index is None or index >= len(problem[f"{suite}_input"]):
        return replace(label, failure_category="unknown")

    base_limit = evalplus_limit(expected, suite, index)
    limit = base_limit * timeout_multiplier
    script = rerun_script(problem, solution, expected, suite, index, limit)
    r = sandbox.run(script, timeout_s=limit + startup_grace_s, memory_mb=memory_mb)
    res = _parse(r["stdout"])

    if res is None:
        # No verdict line: killed by the backstop timeout, or died hard
        # (os._exit, segfault, OOM kill) before reporting.
        category = "timeout" if r["timed_out"] else "error"
        res = {"status": "no_result", "exit_code": r["exit_code"]}
    elif res["status"] == "timeout":
        category = "timeout"
    elif res["status"] == "error":
        category = "error"
    else:
        category = "slow" if res["matches"] else "wrong_output"

    rerun = {"suite": suite, "index": index, "evalplus_limit_s": base_limit,
             "limit_s": limit, "multiplier": timeout_multiplier,
             "sandbox_duration_s": r["duration_s"], **res}
    return replace(label, failure_category=category, rerun=rerun)


def machine_info(sandbox: Sandbox) -> dict:
    """Where labels were produced; timeouts are host-dependent."""
    cpu = platform.processor() or ""
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next((l.split(":", 1)[1].strip() for l in f
                        if l.startswith("model name")), cpu)
    except OSError:
        pass
    info = {"hostname": socket.gethostname(), "platform": platform.platform(),
            "python": sys.version.split()[0], "cpu": cpu,
            "cpu_count": os.cpu_count(), "sandbox": sandbox.name}
    if hasattr(sandbox, "network_isolation"):
        info["network_isolation"] = sandbox.network_isolation
    if hasattr(sandbox, "image"):
        info["image"] = sandbox.image
    return info
