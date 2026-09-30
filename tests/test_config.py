from pathlib import Path

import pytest

from verifier.config import deep_merge, load_config

REPO = Path(__file__).resolve().parents[1]


def test_deep_merge_tables_merge_scalars_and_arrays_replace():
    base = {"a": {"x": 1, "y": [1, 2]}, "b": 1}
    over = {"a": {"y": [3]}, "c": 2}
    assert deep_merge(base, over) == {"a": {"x": 1, "y": [3]}, "b": 1, "c": 2}
    assert base == {"a": {"x": 1, "y": [1, 2]}, "b": 1}  # inputs untouched


def test_extends_resolves_relative_to_file(tmp_path):
    (tmp_path / "base.toml").write_text('[s]\nk = 1\nm = 2\n')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "child.toml").write_text('extends = "../base.toml"\n[s]\nm = 3\n')
    assert load_config(tmp_path / "sub" / "child.toml") == {"s": {"k": 1, "m": 3}}


def test_extends_cycle_is_rejected(tmp_path):
    (tmp_path / "a.toml").write_text('extends = "b.toml"\n')
    (tmp_path / "b.toml").write_text('extends = "a.toml"\n')
    with pytest.raises(ValueError, match="cycle"):
        load_config(tmp_path / "a.toml")


def test_pilot_config_inherits_defaults():
    cfg = load_config(REPO / "configs" / "pilot_local.toml")
    default = load_config(REPO / "configs" / "default.toml")
    assert "extends" not in cfg
    assert cfg["pilot"] == {"n_problems": 40, "sample_seed": 2026}
    assert cfg["model"]["openai"]["extra_body"] == {"cache_prompt": False}
    for section in ("corpus", "labelling", "generation", "sandbox"):
        assert cfg[section] == default[section]
