from __future__ import annotations

from typing import Protocol, TypedDict


class RunResult(TypedDict):
    stdout: str
    stderr: str
    exit_code: int  # killed by signal N -> 128 + N (shell convention) on both backends
    timed_out: bool
    duration_s: float  # host wall clock, including interpreter/container start-up


class Sandbox(Protocol):
    name: str

    def run(self, code: str, timeout_s: float, memory_mb: int) -> RunResult: ...


def read_capped(path: str, limit: int) -> str:
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    text = data[:limit].decode("utf-8", errors="replace")
    return text + "\n[output truncated]" if len(data) > limit else text


def normalise_exit(returncode: int) -> int:
    # subprocess reports death-by-signal as -N; docker/shells report 128+N.
    return 128 - returncode if returncode < 0 else returncode
