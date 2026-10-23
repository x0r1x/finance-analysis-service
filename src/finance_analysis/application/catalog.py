"""Каталог понятий из configs/concepts/core.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml


def catalog_file() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "configs" / "concepts" / "core.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("configs/concepts/core.yaml")


def load_catalog(path: Path | None = None) -> frozenset[str]:
    document = yaml.safe_load((path or catalog_file()).read_text(encoding="utf-8")) or {}
    found: list[str] = []
    for item in document.get("concepts") or []:
        if isinstance(item, str) and item:
            found.append(item)
        elif isinstance(item, dict) and item.get("id"):
            found.append(str(item["id"]))
    return frozenset(found)
