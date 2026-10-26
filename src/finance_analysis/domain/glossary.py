"""Таксономия и метки глоссария (§5.1, §5.2). Без ввода-вывода."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from finance_analysis.domain.ids import concept_id as check_concept_id


class GlossaryInvalid(ValueError):
    """Битый пакет. labels — строки, из-за которых загрузка отказала."""

    def __init__(self, labels: list[str]) -> None:
        self.labels = list(labels)
        super().__init__("метки глоссария: " + ", ".join(self.labels))


def normalize_label(text: str) -> str:
    """Поле сравнения. Исходная метка хранится как ввели."""

    return unicodedata.normalize("NFC", text).casefold().replace("ё", "е")


@dataclass(frozen=True)
class LabelHit:
    concept: str
    kind: str
    text: str


@dataclass(frozen=True)
class Concept:
    id: str
    kind: str
    unit: str
    expected_sign: str | None
    expects_formula: bool
    prefer: str | None
    composition: tuple[str, ...]
    related: tuple[str, ...]
    validation_range: tuple[str, str] | None
    not_all_zero: bool
    plausible: tuple[object, ...]
    pref: Mapping[str, str]
    negative: tuple[str, ...]
    definition: Mapping[str, str]
    expand: Mapping[str, str]
    broader: str | None


@dataclass(frozen=True)
class GlossaryPackage:
    taxonomy: str
    concepts: Mapping[str, Concept]
    flows: Mapping[str, tuple[str, ...]]
    markers: Mapping[str, tuple[str, ...]]
    _by_norm: Mapping[str, LabelHit]

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.concepts)

    def resolve(self, text: str) -> LabelHit | None:
        return self._by_norm.get(normalize_label(text))

    def display_label(self, concept: str, lang: str) -> str | None:
        return self.concepts[concept].pref.get(lang)


def build_package(document: dict, glossaries: Mapping[str, dict], dictionaries: dict) -> GlossaryPackage:
    raw = document.get("concepts")
    if not isinstance(raw, dict) or not raw:
        raise GlossaryInvalid(["concepts"])
    taxonomy = document.get("taxonomy")
    if not isinstance(taxonomy, str) or not taxonomy:
        raise GlossaryInvalid(["taxonomy"])
    concepts: dict[str, Concept] = {}
    owned: dict[str, LabelHit] = {}
    for key, body in raw.items():
        name = check_concept_id(str(key))
        glossary = glossaries.get(name)
        if not isinstance(glossary, dict):
            raise GlossaryInvalid([name])
        concepts[name] = _concept(name, body if isinstance(body, dict) else {}, glossary, owned)
    return GlossaryPackage(
        taxonomy=taxonomy,
        concepts=MappingProxyType(concepts),
        flows=MappingProxyType(_groups(dictionaries.get("flows"), "flows")),
        markers=MappingProxyType(_groups(dictionaries.get("markers"), "markers")),
        _by_norm=MappingProxyType(owned),
    )


def _concept(name: str, body: dict, glossary: dict, owned: dict[str, LabelHit]) -> Concept:
    declared = glossary.get("concept")
    if declared != name:
        raise GlossaryInvalid([str(declared), name])
    kind = body.get("kind")
    unit = body.get("unit")
    if not isinstance(kind, str) or not isinstance(unit, str):
        raise GlossaryInvalid([name])
    pref = _pref(glossary.get("pref"), name)
    if "ru" not in pref or "en" not in pref:
        raise GlossaryInvalid([name])
    _take(owned, name, "pref", {lang: [text] for lang, text in pref.items()})
    alt = _bucket(glossary.get("alt"), name)
    for lang, texts in alt.items():
        if lang not in pref:
            raise GlossaryInvalid(texts)
    _take(owned, name, "alt", alt)
    _take(owned, name, "hidden", _bucket(glossary.get("hidden"), name))
    validation = body.get("validation") or {}
    if not isinstance(validation, dict):
        raise GlossaryInvalid([name])
    return Concept(
        id=name,
        kind=kind,
        unit=unit,
        expected_sign=_optional_str(body.get("expected_sign"), name),
        expects_formula=bool(body.get("expects_formula", False)),
        prefer=_optional_str(body.get("prefer"), name),
        composition=_names(body.get("composition"), name),
        related=_names(body.get("related"), name),
        validation_range=_range(validation.get("range"), name),
        not_all_zero=bool(validation.get("not_all_zero", False)),
        plausible=tuple(body.get("plausible") or ()),
        pref=MappingProxyType(pref),
        negative=tuple(_strings(glossary.get("negative"), name)),
        definition=MappingProxyType(_string_map(glossary.get("definition"), name)),
        expand=MappingProxyType(_string_map(glossary.get("expand"), name)),
        broader=_optional_str(glossary.get("broader"), name),
    )


def _pref(raw, name: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name])
    out: dict[str, str] = {}
    for lang, value in raw.items():
        if isinstance(value, list):
            raise GlossaryInvalid([str(item) for item in value])
        if not isinstance(lang, str) or not isinstance(value, str) or not value:
            raise GlossaryInvalid([name, str(value)])
        out[lang] = value
    return out


def _bucket(raw, name: str) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name])
    out: dict[str, list[str]] = {}
    for lang, value in raw.items():
        if not isinstance(lang, str):
            raise GlossaryInvalid([name])
        out[lang] = _strings(value, name)
    return out


def _take(owned: dict[str, LabelHit], name: str, kind: str, groups: Mapping[str, list[str]]) -> None:
    seen: set[tuple[str, str]] = set()
    for lang, texts in groups.items():
        for text in texts:
            norm = normalize_label(text)
            if not norm or (lang, norm) in seen:
                raise GlossaryInvalid([text])
            seen.add((lang, norm))
            previous = owned.get(norm)
            if previous is not None and (previous.concept != name or previous.kind != kind):
                raise GlossaryInvalid([previous.text, text])
            if previous is None:
                owned[norm] = LabelHit(name, kind, text)


def _strings(raw, name: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        raise GlossaryInvalid([name])
    return list(raw)


def _string_map(raw, name: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name])
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise GlossaryInvalid([name])
        out[key] = value
    return out


def _names(raw, name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise GlossaryInvalid([name])
    return tuple(check_concept_id(str(item)) for item in raw)


def _optional_str(raw, name: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise GlossaryInvalid([name])
    return raw


def _range(raw, name: str) -> tuple[str, str] | None:
    if raw is None:
        return None
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and all(isinstance(item, str) for item in raw)
    ):
        return (raw[0], raw[1])
    raise GlossaryInvalid([name])


def _groups(raw, name: str) -> dict[str, tuple[str, ...]]:
    # shortcut: словарь потоков — стартовые слова, пополнять когда строка книги остаётся без знака
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name])
    out: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list):
            raise GlossaryInvalid([name])
        if not all(isinstance(item, str) and item for item in value):
            raise GlossaryInvalid([name, key])
        out[key] = tuple(value)
    return out
