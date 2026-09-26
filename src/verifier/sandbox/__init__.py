"""Sandboxed execution of untrusted code behind one interface.

    from verifier.sandbox import run
    result = run(code, timeout_s=5, memory_mb=256)

The backend comes from the `[sandbox]` table of the run config (default
`configs/default.toml`, or the path in $VERIFIER_CONFIG); $VERIFIER_SANDBOX_BACKEND
overrides just the backend name.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from verifier.sandbox.base import RunResult, Sandbox
from verifier.sandbox.docker_backend import DockerSandbox
from verifier.sandbox.subprocess_backend import SubprocessSandbox

__all__ = ["RunResult", "Sandbox", "DockerSandbox", "SubprocessSandbox",
           "load_config", "make_sandbox", "run"]

BACKENDS = {"docker": DockerSandbox, "subprocess": SubprocessSandbox}
DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "default.toml"


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.environ.get("VERIFIER_CONFIG") or DEFAULT_CONFIG)
    with open(path, "rb") as f:
        return tomllib.load(f)


def make_sandbox(sandbox_cfg: dict) -> Sandbox:
    """Build a backend from a `[sandbox]` table: `backend = "..."` plus an
    optional sub-table of constructor options named after the backend."""
    backend = os.environ.get("VERIFIER_SANDBOX_BACKEND") or sandbox_cfg.get("backend")
    if backend not in BACKENDS:
        raise ValueError(f"unknown sandbox backend {backend!r}; "
                         f"choose one of {sorted(BACKENDS)}")
    return BACKENDS[backend](**sandbox_cfg.get(backend, {}))


_default: Sandbox | None = None


def run(code: str, timeout_s: float, memory_mb: int) -> RunResult:
    global _default
    if _default is None:
        _default = make_sandbox(load_config()["sandbox"])
    return _default.run(code, timeout_s, memory_mb)
