"""Run configuration: configs/default.toml, or the file named by $VERIFIER_CONFIG."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default.toml"


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.environ.get("VERIFIER_CONFIG") or DEFAULT_CONFIG)
    with open(path, "rb") as f:
        return tomllib.load(f)
