"""Run configuration: configs/default.toml, or the file named by $VERIFIER_CONFIG.

A config may start with `extends = "other.toml"` (resolved relative to itself);
it is then deep-merged over that base: tables merge key by key, any other
value (including arrays) replaces the base value.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default.toml"


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | os.PathLike | None = None, _seen: tuple = ()) -> dict:
    path = Path(path or os.environ.get("VERIFIER_CONFIG") or DEFAULT_CONFIG).resolve()
    if path in _seen:
        raise ValueError(f"config extends cycle: {' -> '.join(map(str, (*_seen, path)))}")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    parent = cfg.pop("extends", None)
    if parent is None:
        return cfg
    return deep_merge(load_config(path.parent / parent, (*_seen, path)), cfg)
