"""Таксономия и метки глоссария (§5.1, §5.2). Без ввода-вывода."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from finance_analysis.domain.dimensions import (
    coarse_kind,
    coarse_unit,
    default_aggregation,
    resolve_axes,
    weight_fits,
)
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
_CODE = re.compile(r"^\d{3,4}$")
_TOKEN = re.compile(r"[^\W\d_]+|\d+|%")


@dataclass(frozen=True)
class _Peeled:
    body: str
    unit: str | None
    period: str | None
    abbrevs: tuple[str, ...]
    codes: tuple[str, ...] = ()
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
    if _CODE.match(inner):
        return "code", inner, rest
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
    codes: list[str] = []
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
        elif kind == "code":
            codes.append(fragment)
        elif kind == "drop":
            stem = True
        body = rest
    return _Peeled(
        body,
        " ".join(reversed(units)) or None,
        " ".join(reversed(periods)) or None,
        tuple(reversed(abbrevs)),
        tuple(reversed(codes)),
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
    for code in peeled.codes:
        key = _fold(code)
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


def label_phrase(item: object) -> str | None:
    """Текст метки. Строка остаётся собой. Объект `{text, ambiguous}` отдаёт фразу."""

    if isinstance(item, str) and item:
        return item
    if isinstance(item, dict):
        text = item.get("text")
        if isinstance(text, str) and text:
            return text
    return None


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


# Первая версия. equivalent_to и replaced_by зарезервированы и в конфиг не принимаются.
ACTIVE_RELATION_TYPES = frozenset({"composed_of", "broader_than", "related_to"})
RESERVED_RELATION_TYPES = frozenset({"equivalent_to", "replaced_by"})


@dataclass(frozen=True)
class ConceptRelation:
    """Ребро от понятия-источника к понятию-цели. Обратное ребро не подразумевается."""

    type: str
    target: str


@dataclass(frozen=True)
class Concept:
    id: str
    semantic_role: str
    dimension: str
    temporal_nature: str
    expected_sign: str | None
    expects_formula: bool
    prefer: str | None
    relations: tuple[ConceptRelation, ...]
    validation_range: tuple[str, str] | None
    not_all_zero: bool
    plausible: tuple[object, ...]
    pref: Mapping[str, str]
    negative: tuple[str, ...]
    definition: Mapping[str, str]
    expand: Mapping[str, str]
    broader: str | None
    aggregation: str | None = None
    pricing_basis: str | None = None
    billing_period: str | None = None
    object_aggregation: str | None = None
    weight: str | None = None

    def relation_targets(self, kind: str) -> tuple[str, ...]:
        return tuple(item.target for item in self.relations if item.type == kind)

    @property
    def composed_of(self) -> tuple[str, ...]:
        return self.relation_targets("composed_of")

    @property
    def broader_than(self) -> tuple[str, ...]:
        return self.relation_targets("broader_than")

    @property
    def related_to(self) -> tuple[str, ...]:
        return self.relation_targets("related_to")

    @property
    def kind(self) -> str:
        """Устаревшая ось. `assumption` читается как parameter, безразмерная мера — как ratio."""

        return coarse_kind(self.semantic_role, self.dimension)

    @property
    def unit(self) -> str:
        """Устаревшая грубая единица. Новая размерность не притворяется money, ratio или count."""

        return coarse_unit(self.dimension)

    @property
    def form(self) -> str:
        """Математическая форма: безразмерная размерность — ratio, остальное — amount."""

        return "ratio" if self.dimension == "ratio" else "amount"

    @property
    def effective_aggregation(self) -> str:
        """Свёртка по времени. Среднее только если оно написано. По объектам этот метод не ходит."""

        return self.aggregation or default_aggregation(self.temporal_nature)

    def sign_conflict(self, row_sign: str | None) -> bool:
        """Приток и отток сверяются со знаком. Запас не носит знак, но поток на запасе — конфликт."""

        if not row_sign:
            return False
        if self.expected_sign:
            return row_sign != self.expected_sign
        return self.temporal_nature == "stock" and row_sign in {"inflow", "outflow"}


@dataclass(frozen=True)
class GlossaryPackage:
    taxonomy: str
    concepts: Mapping[str, Concept]
    flows: Mapping[str, tuple[str, ...]]
    markers: Mapping[str, tuple[str, ...]]
    _by_norm: Mapping[str, LabelHit]
    # Одна нормализованная метка на два понятия только с пометкой ambiguous у обеих.
    # Уверенного победителя у такой метки нет: кандидаты читает ambiguous_hits.
    _ambiguous: Mapping[str, tuple[LabelHit, ...]] = field(default_factory=dict)
    # Несколько исходных текстов одного ключа. Хвост в скобках ключ не меняет.
    _surfaces: Mapping[str, tuple[LabelHit, ...]] = field(default_factory=dict)

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.concepts)

    def resolve(self, text: str) -> LabelHit | None:
        found = self.resolve_match(text)
        return found[0] if found else None

    def resolve_match(self, text: str) -> tuple[LabelHit, str] | None:
        """Одно понятие и сила: exact — тело подписи, abbrev — только скобка.

        Два ключа на разные понятия не привязываются. Тело, совпавшее вместе со
        своей аббревиатурой, остаётся exact. Голова подписи до пояснения в скобках
        тоже exact, если она совпала с меткой глоссария. Метка, помеченная
        ambiguous у нескольких понятий, сюда не попадает.
        """

        peeled = _peel(text)
        body = _fold(peeled.body)
        if body and body in self._ambiguous:
            return None
        found: list[tuple[LabelHit, str]] = []
        if body:
            hit = self._select(body, text)
            if hit is not None:
                found.append((hit, "exact"))
        for abbrev in peeled.abbrevs:
            key = _fold(abbrev)
            if not key or key == body:
                continue
            hit = self._select(key, text)
            if hit is None or any(item.concept == hit.concept for item, _strength in found):
                continue
            found.append((hit, "abbrev"))
        for code in peeled.codes:
            key = _fold(code)
            if not key or key == body:
                continue
            hit = self._select(key, text)
            if hit is None or any(item.concept == hit.concept for item, _strength in found):
                continue
            found.append((hit, "exact"))
        if len({hit.concept for hit, _strength in found}) != 1:
            return None
        return found[0]

    def _select(self, key: str, text: str) -> LabelHit | None:
        """Поверхность ключа, чей текст совпал со строкой. Иначе первая."""

        pool = self._surfaces.get(key)
        if not pool:
            return self._by_norm.get(key)
        wanted = label_surface(text)
        for hit in pool:
            if label_surface(hit.text) == wanted:
                return hit
        return pool[0]

    def ambiguous_hits(self, text: str) -> tuple[LabelHit, ...]:
        """Кандидаты метки, которую делят несколько понятий. Уверенного совпадения нет.

        Тело, уже занятое одним понятием, этот список не открывает: аббревиатура
        в скобке не спорит с точной меткой.
        """

        peeled = _peel(text)
        body = _fold(peeled.body)
        if body and body in self._by_norm:
            return ()
        keys: list[str] = []
        if body:
            keys.append(body)
        for abbrev in peeled.abbrevs:
            key = _fold(abbrev)
            if key and key not in keys:
                keys.append(key)
        for code in peeled.codes:
            key = _fold(code)
            if key and key not in keys:
                keys.append(key)
        found: list[LabelHit] = []
        seen: set[str] = set()
        wanted = label_surface(text)
        for key in keys:
            by_concept: dict[str, list[LabelHit]] = {}
            for hit in self._ambiguous.get(key, ()):
                by_concept.setdefault(hit.concept, []).append(hit)
            for concept, hits in by_concept.items():
                if concept in seen:
                    continue
                seen.add(concept)
                found.append(next((item for item in hits if label_surface(item.text) == wanted), hits[0]))
        return tuple(found)

    def display_label(self, concept: str, lang: str) -> str | None:
        return self.concepts[concept].pref.get(lang)


def with_profile(package: GlossaryPackage, document: dict, profile_id: str | None) -> GlossaryPackage:
    """Метки профиля бьют глобальные только у этой книги. Чужой ключ не перезаписывается."""

    if not profile_id:
        return package
    overlay = dict(package._by_norm)
    surfaces = dict(package._surfaces)
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
                        if norm in package._ambiguous:
                            continue
                        previous = overlay.get(norm)
                        if previous is not None and previous.concept != str(concept):
                            continue
                        overlay[norm] = LabelHit(str(concept), kind, text)
                        surfaces.pop(norm, None)
    return GlossaryPackage(
        taxonomy=package.taxonomy,
        concepts=package.concepts,
        flows=package.flows,
        markers=package.markers,
        _by_norm=MappingProxyType(overlay),
        _ambiguous=package._ambiguous,
        _surfaces=MappingProxyType(surfaces),
    )


def build_package(document: dict, glossaries: Mapping[str, dict], dictionaries: dict) -> GlossaryPackage:
    raw = document.get("concepts")
    if not isinstance(raw, dict) or not raw:
        raise GlossaryInvalid(["concepts"])
    taxonomy = document.get("taxonomy")
    if not isinstance(taxonomy, str) or not taxonomy:
        raise GlossaryInvalid(["taxonomy"])
    concepts: dict[str, Concept] = {}
    slots: dict[str, list[tuple[LabelHit, bool]]] = {}
    known = {check_concept_id(str(key)) for key in raw}
    for key, body in raw.items():
        name = check_concept_id(str(key))
        glossary = glossaries.get(name)
        if not isinstance(glossary, dict):
            raise GlossaryInvalid([name])
        concepts[name] = _concept(name, body if isinstance(body, dict) else {}, glossary, slots, known)
    owned, ambiguous, surfaces = _publish(slots)
    bad_weight = [
        concept.id
        for concept in concepts.values()
        if concept.object_aggregation == "weighted_average"
        and (
            concept.weight not in concepts
            or concept.weight == concept.id
            or not weight_fits(concept.dimension, concepts[concept.weight].dimension)
        )
    ]
    if bad_weight:
        raise GlossaryInvalid(bad_weight)
    _check_relations(concepts)
    return GlossaryPackage(
        taxonomy=taxonomy,
        concepts=MappingProxyType(concepts),
        flows=MappingProxyType(_groups(dictionaries.get("flows"), "flows")),
        markers=MappingProxyType(_groups(dictionaries.get("markers"), "markers")),
        _by_norm=MappingProxyType(owned),
        _ambiguous=MappingProxyType(ambiguous),
        _surfaces=MappingProxyType(surfaces),
    )


def _concept(
    name: str,
    body: dict,
    glossary: dict,
    slots: dict[str, list[tuple[LabelHit, bool]]],
    known: set[str],
) -> Concept:
    declared = glossary.get("concept")
    if declared != name:
        raise GlossaryInvalid([str(declared), name])
    try:
        axes = resolve_axes(body)
    except (TypeError, ValueError):
        raise GlossaryInvalid([name]) from None
    pref = _pref(glossary.get("pref"), name)
    if "ru" not in pref or "en" not in pref:
        raise GlossaryInvalid([name])
    _take(slots, name, "pref", {lang: [(text, False)] for lang, text in pref.items()})
    alt = _bucket(glossary.get("alt"), name)
    for lang, texts in alt.items():
        if lang not in pref:
            raise GlossaryInvalid([text for text, _flag in texts])
    _take(slots, name, "alt", alt)
    _take(slots, name, "hidden", _bucket(glossary.get("hidden"), name))
    validation = body.get("validation") or {}
    if not isinstance(validation, dict):
        raise GlossaryInvalid([name])
    return Concept(
        id=name,
        semantic_role=str(axes["semantic_role"]),
        dimension=str(axes["dimension"]),
        temporal_nature=str(axes["temporal_nature"]),
        expected_sign=axes["expected_sign"] if isinstance(axes["expected_sign"], str) else None,
        aggregation=axes["aggregation"] if isinstance(axes["aggregation"], str) else None,
        pricing_basis=axes["pricing_basis"] if isinstance(axes["pricing_basis"], str) else None,
        billing_period=axes["billing_period"] if isinstance(axes["billing_period"], str) else None,
        object_aggregation=axes["object_aggregation"] if isinstance(axes["object_aggregation"], str) else None,
        weight=axes["weight"] if isinstance(axes["weight"], str) else None,
        expects_formula=bool(body.get("expects_formula", False)),
        prefer=_optional_str(body.get("prefer"), name),
        relations=_relations(body, name, known),
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


def _bucket(raw, name: str) -> dict[str, list[tuple[str, bool]]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name])
    out: dict[str, list[tuple[str, bool]]] = {}
    for lang, value in raw.items():
        if not isinstance(lang, str):
            raise GlossaryInvalid([name])
        out[lang] = _labels(value, name)
    return out


def _labels(raw, name: str) -> list[tuple[str, bool]]:
    """Строка — обычная метка. Объект `{text, ambiguous: true}` делится между понятиями."""

    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise GlossaryInvalid([name])
    out: list[tuple[str, bool]] = []
    for item in raw:
        if isinstance(item, str) and item:
            out.append((item, False))
            continue
        if not isinstance(item, dict) or set(item) != {"text", "ambiguous"}:
            raise GlossaryInvalid([name])
        text = item.get("text")
        if not isinstance(text, str) or not text or item.get("ambiguous") is not True:
            raise GlossaryInvalid([name, str(text)])
        out.append((text, True))
    return out


def _take(
    slots: dict[str, list[tuple[LabelHit, bool]]],
    name: str,
    kind: str,
    groups: Mapping[str, list[tuple[str, bool]]],
) -> None:
    seen: set[tuple[str, str]] = set()
    for lang, texts in groups.items():
        for text, ambiguous in texts:
            if (lang, text) in seen:
                raise GlossaryInvalid([text])
            seen.add((lang, text))
            keys = label_keys(text)
            if not keys:
                raise GlossaryInvalid([text])
            hit = LabelHit(name, kind, text)
            surface = label_surface(text)
            for norm in keys:
                group = slots.setdefault(norm, [])
                exact = next(
                    (
                        item
                        for item in group
                        if item[0].concept == name and item[0].kind == kind and label_surface(item[0].text) == surface
                    ),
                    None,
                )
                if exact is not None:
                    if not ambiguous and exact[1]:
                        group[group.index(exact)] = (exact[0], False)
                    continue
                others = [item for item in group if item[0].concept != name or item[0].kind != kind]
                if others and (not ambiguous or any(not flag for _hit, flag in others)):
                    raise GlossaryInvalid([others[0][0].text, text])
                group.append((hit, ambiguous))


def _publish(
    slots: dict[str, list[tuple[LabelHit, bool]]],
) -> tuple[dict[str, LabelHit], dict[str, tuple[LabelHit, ...]], dict[str, tuple[LabelHit, ...]]]:
    single: dict[str, LabelHit] = {}
    ambiguous: dict[str, tuple[LabelHit, ...]] = {}
    surfaces: dict[str, tuple[LabelHit, ...]] = {}
    for norm, group in slots.items():
        concepts = []
        for hit, _flag in group:
            if hit.concept not in concepts:
                concepts.append(hit.concept)
        kept = _unique_hits(group)
        if len(concepts) == 1:
            single[norm] = kept[0]
            if len(kept) > 1:
                surfaces[norm] = tuple(kept)
            continue
        if any(not flag for _hit, flag in group):
            raise GlossaryInvalid([hit.text for hit, _flag in group])
        ambiguous[norm] = tuple(kept)
    return single, ambiguous, surfaces


def _unique_hits(group: list[tuple[LabelHit, bool]]) -> list[LabelHit]:
    kept: list[LabelHit] = []
    seen: set[tuple[str, str, str]] = set()
    for hit, _flag in group:
        marker = (hit.concept, hit.kind, label_surface(hit.text))
        if marker in seen:
            continue
        seen.add(marker)
        kept.append(hit)
    return kept


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


def _relations(body: dict, name: str, known: set[str]) -> tuple[ConceptRelation, ...]:
    """Новая карта `relations` или прежние ключи уже выпущенного документа.

    `composition` читается как `composed_of`. Из `related` остаются только понятия пакета:
    прежний список cfads называл ещё идентификаторы метрик. Рядом с `relations` старые ключи отвергаются.
    """

    legacy = [key for key in ("composition", "related") if key in body]
    if legacy and "relations" in body:
        raise GlossaryInvalid([name, "legacy:relations"])
    raw = body.get("relations")
    if legacy:
        raw = {}
        if "composition" in body:
            raw["composed_of"] = body["composition"]
        related = body.get("related")
        if isinstance(related, list):
            kept = [item for item in related if isinstance(item, str) and item in known]
            if kept:
                raw["related_to"] = kept
        elif "related" in body:
            raise GlossaryInvalid([name, "related"])
        if not raw:
            return ()
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise GlossaryInvalid([name, "relations"])
    found: list[ConceptRelation] = []
    seen: set[tuple[str, str]] = set()
    for kind, targets in raw.items():
        label = str(kind)
        if label in RESERVED_RELATION_TYPES:
            raise GlossaryInvalid([name, f"reserved:{label}"])
        if label not in ACTIVE_RELATION_TYPES:
            raise GlossaryInvalid([name, f"unknown:{label}"])
        if not isinstance(targets, list) or not targets:
            raise GlossaryInvalid([name, label])
        for item in targets:
            if not isinstance(item, str):
                raise GlossaryInvalid([name, label])
            target = check_concept_id(item)
            if target == name:
                raise GlossaryInvalid([name, f"cycle:{label}", target])
            if (label, target) in seen:
                raise GlossaryInvalid([name, f"duplicate:{label}", target])
            seen.add((label, target))
            found.append(ConceptRelation(label, target))
    return tuple(found)


def _check_relations(concepts: Mapping[str, Concept]) -> None:
    """Цель есть в пакете. composed_of проверяется отдельно.

    Иерархия — один граф в направлении broader_than: цель связи — ребёнок,
    опубликованный broader — ребро от родителя к ребёнку. Обход цикла один.
    """

    bad: list[str] = []
    composed: dict[str, tuple[str, ...]] = {}
    children: dict[str, set[str]] = {}
    parents: dict[str, set[str]] = {}

    def link(parent: str, child: str) -> None:
        children.setdefault(parent, set()).add(child)

    for concept in concepts.values():
        for relation in concept.relations:
            if relation.target not in concepts:
                bad.append(f"missing:{relation.target}")
        if concept.composed_of:
            composed[concept.id] = concept.composed_of
        for target in concept.broader_than:
            link(concept.id, target)
            parents.setdefault(target, set()).add(concept.id)
        parent = concept.broader
        if parent is None:
            continue
        if parent == concept.id or parent not in concepts:
            bad.append(concept.id)
            continue
        link(parent, concept.id)
        declared = parents.get(concept.id)
        if declared is not None and declared != {parent}:
            bad.append(concept.id)
    member = _cycle_member(composed)
    if member:
        bad.append("cycle:composed_of")
        bad.append(member)
    hierarchy = {node: tuple(sorted(kids)) for node, kids in children.items()}
    member = _cycle_member(hierarchy)
    if member:
        bad.append("cycle:broader")
        bad.append(member)
    if bad:
        raise GlossaryInvalid(_unique(bad))


def _cycle_member(edges: Mapping[str, tuple[str, ...]]) -> str | None:
    color: dict[str, int] = {}

    def walk(node: str) -> str | None:
        color[node] = 1
        for nxt in edges.get(node, ()):
            state = color.get(nxt, 0)
            if state == 1:
                return nxt
            if state == 0:
                found = walk(nxt)
                if found:
                    return found
        color[node] = 2
        return None

    for node in edges:
        if color.get(node, 0) == 0:
            found = walk(node)
            if found:
                return found
    return None


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


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


def parse_dictionary_groups(raw, name: str) -> dict[str, tuple[str, ...]]:
    """Строгая проверка flows/markers: только непустые строки, без тихого отбрасывания."""

    if not isinstance(raw, Mapping):
        raise GlossaryInvalid([name])
    out: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, (list, tuple)):
            raise GlossaryInvalid([name])
        if not all(isinstance(item, str) and item for item in value):
            raise GlossaryInvalid([name, key])
        out[key] = tuple(value)
    return out


def _groups(raw, name: str) -> dict[str, tuple[str, ...]]:
    # shortcut: словарь потоков — стартовые слова, пополнять когда строка книги остаётся без знака
    return parse_dictionary_groups(raw, name)
