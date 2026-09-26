"""Subprocess sandbox using POSIX rlimits, for hosts without Docker (e.g. TC1).

Isolation provided:
  * memory     RLIMIT_AS (virtual address space; allocation fails -> MemoryError)
  * CPU        RLIMIT_CPU backstop at timeout+1s, plus a wall-clock timeout that
               SIGKILLs the whole process group (so forked children die too)
  * files      RLIMIT_FSIZE caps any file written, including captured stdout/stderr
  * network    "namespace": unprivileged network namespace via `unshare --net`
               (no interfaces but a down loopback) when the kernel permits it;
               "python-guard": socket functions patched to raise. The guard stops
               ordinary library code but is bypassable (ctypes, _socket, spawning
               curl) — adequate for non-adversarial model output, not a security
               boundary. `network_isolation` records which one is in force.
Not isolated: filesystem reads, process count (no RLIMIT_NPROC: it is per-user
and would break on shared cluster nodes).
"""

from __future__ import annotations

import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from verifier.sandbox.base import RunResult, normalise_exit, read_capped

_RUNNER = r'''
import runpy, sys
code_path, mode = sys.argv[1], sys.argv[2]
if mode == "guard":
    import socket
    def _deny(*a, **k):
        raise OSError(101, "Network is unreachable (sandbox)")
    for _n in ("connect", "connect_ex", "sendto", "sendmsg", "bind"):
        setattr(socket.socket, _n, _deny)
    socket.create_connection = _deny
    socket.getaddrinfo = _deny
    socket.gethostbyname = _deny
sys.argv = [code_path]
runpy.run_path(code_path, run_name="__main__")
'''


def _namespace_available() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        r = subprocess.run(["unshare", "--net", "--map-root-user", "true"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class SubprocessSandbox:
    name = "subprocess"

    def __init__(self, python: str = sys.executable, network: str = "auto",
                 max_output_bytes: int = 1_000_000, max_file_mb: int = 16):
        if network not in ("auto", "namespace", "python-guard"):
            raise ValueError(f"unknown network mode {network!r}")
        self.python = python
        self.network = network
        self.max_output_bytes = max_output_bytes
        self.max_file_bytes = max_file_mb * 1024 * 1024
        self._isolation: str | None = None

    @property
    def network_isolation(self) -> str:
        if self._isolation is None:
            has_ns = _namespace_available()
            if self.network == "namespace" and not has_ns:
                raise RuntimeError("network='namespace' but unprivileged "
                                   "user/network namespaces are unavailable")
            if self.network == "python-guard":
                self._isolation = "python-guard"
            else:
                self._isolation = "namespace" if has_ns else "python-guard"
        return self._isolation

    def _set_limits(self, timeout_s: float, memory_mb: int) -> None:
        import resource  # POSIX only; runs in the child between fork and exec

        mem = memory_mb * 1024 * 1024
        cpu = math.ceil(timeout_s) + 1
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (self.max_file_bytes,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def run(self, code: str, timeout_s: float, memory_mb: int) -> RunResult:
        if os.name != "posix":
            raise RuntimeError("SubprocessSandbox needs a POSIX host (resource.setrlimit)")
        isolation = self.network_isolation
        with tempfile.TemporaryDirectory(prefix="sbx-") as d:
            code_path, runner_path = os.path.join(d, "main.py"), os.path.join(d, "_runner.py")
            out_path, err_path = os.path.join(d, "stdout"), os.path.join(d, "stderr")
            with open(code_path, "w") as f:
                f.write(code)
            with open(runner_path, "w") as f:
                f.write(_RUNNER)

            cmd = [self.python, "-I", runner_path, code_path,
                   "guard" if isolation == "python-guard" else "none"]
            if isolation == "namespace":
                cmd = ["unshare", "--net", "--map-root-user", *cmd]
            env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": d,
                   "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}

            with open(out_path, "wb") as out, open(err_path, "wb") as err:
                t0 = time.monotonic()
                p = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    cwd=d, env=env, start_new_session=True,
                    preexec_fn=lambda: self._set_limits(timeout_s, memory_mb))
                timed_out = False
                try:
                    rc = p.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    self._kill_group(p.pid)
                    rc = p.wait()
                duration = time.monotonic() - t0
                self._kill_group(p.pid)  # reap any children left behind

            return RunResult(
                stdout=read_capped(out_path, self.max_output_bytes),
                stderr=read_capped(err_path, self.max_output_bytes),
                exit_code=normalise_exit(rc),
                timed_out=timed_out,
                duration_s=round(duration, 4),
            )

    @staticmethod
    def _kill_group(pgid: int) -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
