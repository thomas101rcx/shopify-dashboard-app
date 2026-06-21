"""Rules loader: read rules from YAML / JSON / Python file."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def _load_file(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")
    suffix = p.suffix.lower()
    if suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    elif suffix == ".py":
        import importlib.util

        spec = importlib.util.spec_from_file_location("rules_mod", p)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        data = getattr(mod, "RULES", getattr(mod, "rules", []))
    else:
        raise ValueError(f"Unsupported rules file format: {suffix}")
    if isinstance(data, dict):
        return data.get("rules", [])
    if isinstance(data, list):
        return data
    raise ValueError("Rules file must contain a list or a dict with a 'rules' key")


def load_rules(path: str | None) -> list[dict]:
    if path is None:
        return []
    return _load_file(path)
