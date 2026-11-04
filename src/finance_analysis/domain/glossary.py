"""Таксономия и метки глоссария (§5.1, §5.2). Без ввода-вывода."""

from __future__ import annotations

import re
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


# Хвостовые куски сравнения (§5.2). Список замкнутый: новая форма — новое правило и тест.
_PERIODS = (
    re.compile(r"(?i)[\s,]+(за\s+кв\.?)$"),
    re.compile(r"(?i)[\s,]+(за\s+квартал)$"),
    re.compile(r"(?i)[\s,]+(за\s+год)$"),
    re.compile(r"(?i)[\s,]+(за\s+период)$"),
    re.compile(r"(?i)[\s,]+(last\s+12\s+months)$"),
    re.compile(r"(?i)[\s,]+(ltm)$"),
)
_UNITS = (
    re.compile(r"(?i)[\s,]+((?:тыс|млн|млрд)\.?\s*руб\.?)$"),
    re.compile(r"(?i),\s*(руб\.?)$"),
    re.compile(r"(?i)[\s,]+(%)$"),
    re.compile(r"(?i)\s*(\$\s*'?\s*0{3})$"),
    re.compile(r"(?i)[\s,]+((?:usd|eur|gbp|rub)\s*'?\s*(?:k|000))$"),
    re.compile(r"(?i)[\s,]+(k[£€$])$"),
    re.compile(r"(?i)\s*([£€]\s*'?\s*0{3})$"),
)
_PAREN = re.compile(r"\s*\(([^()]*)\)\s*$")
_INSTRUCTION = re.compile(r"(?i)[,;]?\s*(?:укажите|введите)\b.*$")
_PERIOD_INNER = re.compile(r"(?i)^(?:last\s+12\s+months|ltm|за\s+кв\.?|за\s+квартал|за\s+год|за\s+период)$")
_UNIT_INNER = re.compile(
    r"(?i)^(?:(?:тыс|млн|млрд)\.?\s*руб\.?|руб\.?|%|\$\s*'?\s*0{3}|(?:usd|eur|gbp|rub)\s*'?\s*(?:k|000)|k[£€$]|[£€$]\s*'?\s*0{3})$"
)
_ABBREV = re.compile(r"^[A-ZА-ЯЁ][A-ZА-ЯЁ0-9.]{1,14}$")
_TOKEN = re.compile(r"[^\W\d_]+|\d+|%")


@dataclass(frozen=True)
class _Peeled:
    body: str
    unit: str | None
    period: str | None
    abbrevs: tuple[str, ...]
    stem: bool = False


@dataclass(frozen=True)
class LabelFeatures:
    """Единица и период, снятые с хвоста подписи. Пусто, если хвоста не было."""

    unit: str | None = None
    period: str | None = None


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", fragment).strip(" ,")


def _suffix(body: str, patterns: tuple[re.Pattern[str], ...], kind: str) -> tuple[str, str, str] | None:
    for pattern in patterns:
        match = pattern.search(body)
        if match is None:
            continue
        fragment = _clean(match.group(1))
        rest = body[: match.start()].rstrip(" ,")
        if fragment and len(rest) < len(body):
            return kind, fragment, rest
    return None


def _paren(body: str) -> tuple[str, str, str] | None:
    match = _PAREN.search(body)
    if match is None:
        return None
    inner = _clean(match.group(1))
    rest = body[: match.start()].rstrip(" ,")
    if not inner or len(rest) >= len(body):
        return None
    if _PERIOD_INNER.match(inner):
        return "period", inner, rest
    if _UNIT_INNER.match(inner):
        return "unit", inner, rest
    if _ABBREV.match(inner):
        return "abbrev", inner, rest
    return "drop", inner, rest


def _strip_instruction(text: str) -> str:
    """Снимает хвост «укажите …» или «введите …». Подпись целиком не стирает."""

    match = _INSTRUCTION.search(text)
    if match is None or match.start() == 0:
        return text
    return text[: match.start()].strip(" ,;")


def _peel(text: str) -> _Peeled:
    body = unicodedata.normalize("NFC", _strip_instruction(text)).strip()
    units: list[str] = []
    periods: list[str] = []
    abbrevs: list[str] = []
    stem = False
    while body:
        cut = _suffix(body, _PERIODS, "period") or _suffix(body, _UNITS, "unit") or _paren(body)
        if cut is None:
            break
        kind, fragment, rest = cut
        if kind == "period":
            periods.append(fragment)
        elif kind == "unit":
            units.append(fragment)
        elif kind == "abbrev":
            abbrevs.append(fragment)
        elif kind == "drop":
            stem = True
        body = rest
    return _Peeled(
        body,
        " ".join(reversed(units)) or None,
        " ".join(reversed(periods)) or None,
        tuple(reversed(abbrevs)),
        stem,
    )


def _plural(word: str) -> str:
    # Простое -s. Аббревиатура из заглавных и короткое слово без двух гласных не режутся (CFADS).
    folded = word.casefold()
    if len(word) < 5 or not folded.endswith("s") or folded.endswith("ss") or word.isupper():
        return word
    if sum(char in "aeiouy" for char in folded) < 2:
        return word
    return word[:-1]


def _fold(text: str) -> str:
    parts = []
    for token in _TOKEN.findall(unicodedata.normalize("NFC", text)):
        if token.isascii() and token.isalpha():
            token = _plural(token)
        parts.append(token)
    return " ".join(parts).casefold().replace("ё", "е")


def label_keys(text: str) -> tuple[str, ...]:
    """Ключи точного сравнения: тело метки и аббревиатуры из хвостовых скобок."""

    peeled = _peel(text)
    keys: list[str] = []
    body = _fold(peeled.body)
    if body:
        keys.append(body)
    for abbrev in peeled.abbrevs:
        key = _fold(abbrev)
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def normalize_label(text: str) -> str:
    """Поле сравнения. Исходная метка хранится как ввели."""

    keys = label_keys(text)
    return keys[0] if keys else ""


def label_surface(text: str) -> str:
    """Идентичность метки и поиск: NFC и casefold, без среза хвоста."""

    return unicodedata.normalize("NFC", text).strip().casefold()


def label_scan(text: str) -> str:
    """Сырой текст для negative: NFC, casefold, ё→е. Хвост не срезается."""

    return label_surface(text).replace("ё", "е")


def label_features(text: str) -> LabelFeatures:
    peeled = _peel(text)
    return LabelFeatures(peeled.unit, peeled.period)


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
        found = self.resolve_match(text)
        return found[0] if found else None

    def resolve_match(self, text: str) -> tuple[LabelHit, str] | None:
        """Одно понятие и сила: exact — тело подписи, stem — тело без хвоста в скобках, abbrev — только скобка.

        Два ключа на разные понятия не привязываются. Тело, совпавшее вместе со
        своей аббревиатурой, остаётся exact. Пояснение в скобках слабее точной метки.
        """

        peeled = _peel(text)
        body = _fold(peeled.body)
        found: list[tuple[LabelHit, str]] = []
        if body:
            hit = self._by_norm.get(body)
            if hit is not None:
                found.append((hit, "stem" if peeled.stem else "exact"))
        for abbrev in peeled.abbrevs:
            key = _fold(abbrev)
            if not key or key == body:
                continue
            hit = self._by_norm.get(key)
            if hit is None or any(item.concept == hit.concept for item, _strength in found):
                continue
            found.append((hit, "abbrev"))
        if len({hit.concept for hit, _strength in found}) != 1:
            return None
        return found[0]

    def display_label(self, concept: str, lang: str) -> str | None:
        return self.concepts[concept].pref.get(lang)


def with_profile(package: GlossaryPackage, document: dict, profile_id: str | None) -> GlossaryPackage:
    """Метки профиля бьют глобальные только у этой книги. Чужой ключ не перезаписывается."""

    if not profile_id:
        return package
    overlay = dict(package._by_norm)
    for concept, glossary in (document.get("glossaries") or {}).items():
        scoped = (glossary.get("scoped") or {}).get(profile_id) if isinstance(glossary, dict) else None
        if not isinstance(scoped, dict):
            continue
        for kind in ("alt", "hidden"):
            bucket = scoped.get(kind) or {}
            if not isinstance(bucket, dict):
                continue
            for texts in bucket.values():
                items = [texts] if isinstance(texts, str) else list(texts or [])
                for text in items:
                    if not isinstance(text, str) or not text:
                        continue
                    for norm in label_keys(text):
                        previous = overlay.get(norm)
                        if previous is not None and previous.concept != str(concept):
                            continue
                        overlay[norm] = LabelHit(str(concept), kind, text)
    return GlossaryPackage(
        taxonomy=package.taxonomy,
        concepts=package.concepts,
        flows=package.flows,
        markers=package.markers,
        _by_norm=MappingProxyType(overlay),
    )


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
            if (lang, text) in seen:
                raise GlossaryInvalid([text])
            seen.add((lang, text))
            keys = label_keys(text)
            if not keys:
                raise GlossaryInvalid([text])
            for norm in keys:
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
