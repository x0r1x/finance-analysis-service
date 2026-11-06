"""Каталог понятий: таксономия §5.1 и глоссарий §5.2."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from finance_analysis.domain.dimensions import DimensionCatalog, parse_catalog
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


def dimensions_file() -> Path:
    return catalog_file().parent.parent / "dimensions.yaml"


@lru_cache(maxsize=1)
def load_dimensions(path: str | None = None) -> DimensionCatalog:
    file = Path(path) if path else dimensions_file()
    try:
        return parse_catalog(yaml.safe_load(file.read_text(encoding="utf-8")) or {})
    except (TypeError, ValueError) as exc:
        raise GlossaryInvalid([str(exc)]) from None


def load_catalog(path: Path | None = None) -> GlossaryPackage:
    document = load_git_document(path)
    package = build_package(
        {"taxonomy": document["taxonomy"], "concepts": document["concepts"]},
        document["glossaries"],
        document["dictionaries"],
    )
    catalog = load_dimensions()
    unknown = []
    for name, concept in package.concepts.items():
        if concept.dimension not in catalog.exponents:
            unknown.append(name)
            continue
        declared = catalog.pricing_basis.get(concept.dimension)
        if declared and concept.pricing_basis != declared:
            unknown.append(name)
    if unknown:
        raise GlossaryInvalid(unknown)
    return package


def load_identities(path: Path | None = None) -> dict[str, list[str]]:
    """Тождества для lf.identity из configs/identities/*.yaml (§5.11.1)."""

    folder = path or catalog_file().parent.parent / "identities"
    found: dict[str, list[str]] = {}
    if not folder.is_dir():
        return found
    for file in sorted(folder.glob("*.yaml")):
        document = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        for left, parts in (document.get("identities") or {}).items():
            found[check_concept_id(str(left))] = [check_concept_id(str(part)) for part in parts]
    return found
