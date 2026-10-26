"""Каталог понятий: таксономия §5.1 и глоссарий §5.2."""

from __future__ import annotations

from pathlib import Path

import yaml

from finance_analysis.domain.glossary import (
    GlossaryInvalid,
    GlossaryPackage,
    build_package,
)
from finance_analysis.domain.ids import concept_id as check_concept_id


def catalog_file() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "configs" / "concepts" / "core.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("configs/concepts/core.yaml")


def load_git_document(path: Path | None = None) -> dict:
    core = path or catalog_file()
    document = yaml.safe_load(core.read_text(encoding="utf-8")) or {}
    raw = document.get("concepts") if isinstance(document, dict) else None
    if not isinstance(raw, dict):
        raise GlossaryInvalid(["concepts"])
    names = [check_concept_id(str(key)) for key in raw]
    glossary_dir = core.parent.parent / "glossary"
    glossaries: dict[str, dict] = {}
    for name in names:
        file = glossary_dir / f"{name}.yaml"
        if not file.is_file():
            raise GlossaryInvalid([name])
        glossaries[name] = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    dictionaries = glossary_dir / "dictionaries.yaml"
    if not dictionaries.is_file():
        raise GlossaryInvalid(["dictionaries"])
    return {
        "taxonomy": document.get("taxonomy"),
        "concepts": raw,
        "glossaries": glossaries,
        "dictionaries": yaml.safe_load(dictionaries.read_text(encoding="utf-8")) or {},
    }


def load_catalog(path: Path | None = None) -> GlossaryPackage:
    document = load_git_document(path)
    return build_package(
        {"taxonomy": document["taxonomy"], "concepts": document["concepts"]},
        document["glossaries"],
        document["dictionaries"],
    )
