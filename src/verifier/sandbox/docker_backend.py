"""Docker sandbox for local use.

The container gets no network (--network none), hard memory with no swap,
a CPU quota, a PID cap, a read-only root with a small /tmp, no capabilities,
and runs as `nobody`. Code is piped to `python -I -` on stdin, so no host paths
are mounted.

Timing: coreutils `timeout` inside the container enforces `timeout_s` from
interpreter launch (exit 124), so container start-up does not eat into the
budget. A host-side deadline of timeout_s + startup_grace_s is a safety net
that `docker kill`s the container. `duration_s` is host wall clock and so
includes start-up (typically 0.3–1 s).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid

from verifier.sandbox.base import RunResult, read_capped

TIMEOUT_EXIT = 124  # coreutils `timeout` when the command was stopped


class DockerSandbox:
    name = "docker"

    def __init__(self, image: str = "python:3.13-slim", cpus: float = 1.0,
                 pids_limit: int = 64, tmpfs_mb: int = 64, docker: str = "docker",
                 startup_grace_s: float = 10.0, max_output_bytes: int = 1_000_000):
        self.image = image
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.tmpfs_mb = tmpfs_mb
        self.docker = docker
        self.startup_grace_s = startup_grace_s
        self.max_output_bytes = max_output_bytes

    def available(self) -> bool:
        try:
            return subprocess.run([self.docker, "info"], capture_output=True,
                                  timeout=20).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def command(self, name: str, timeout_s: float, memory_mb: int) -> list[str]:
        return [
            self.docker, "run", "--rm", "-i", "--name", name,
            "--network", "none",
            f"--memory={memory_mb}m", f"--memory-swap={memory_mb}m",
            f"--cpus={self.cpus}", f"--pids-limit={self.pids_limit}",
            "--read-only", "--tmpfs", f"/tmp:rw,size={self.tmpfs_mb}m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534", "--workdir", "/tmp",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            self.image,
            "timeout", "--kill-after=1", f"{timeout_s}", "python", "-I", "-",
        ]

    def run(self, code: str, timeout_s: float, memory_mb: int) -> RunResult:
        name = f"sbx-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory(prefix="sbx-") as d:
            out_path, err_path = os.path.join(d, "stdout"), os.path.join(d, "stderr")
            with open(out_path, "wb") as out, open(err_path, "wb") as err:
                t0 = time.monotonic()
                p = subprocess.Popen(self.command(name, timeout_s, memory_mb),
                                     stdin=subprocess.PIPE, stdout=out, stderr=err)
                try:
                    p.stdin.write(code.encode())
                    p.stdin.close()
                except BrokenPipeError:
                    pass
                host_killed = False
                try:
                    rc = p.wait(timeout=timeout_s + self.startup_grace_s)
                except subprocess.TimeoutExpired:
                    host_killed = True
                    subprocess.run([self.docker, "kill", name], capture_output=True)
                    rc = p.wait()
                duration = time.monotonic() - t0

            return RunResult(
                stdout=read_capped(out_path, self.max_output_bytes),
                stderr=read_capped(err_path, self.max_output_bytes),
                exit_code=rc,
                timed_out=host_killed or rc == TIMEOUT_EXIT,
                duration_s=round(duration, 4),
            )
