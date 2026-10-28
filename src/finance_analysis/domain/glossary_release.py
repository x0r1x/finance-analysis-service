"""Релиз глоссария: канонический документ, ops и diff (§5.9)."""

from __future__ import annotations

import copy
import hashlib

from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.glossary import GlossaryInvalid, build_package


def version_for(seq: int, document: dict) -> str:
    digest = hashlib.sha256(canonical_json(document).encode()).hexdigest()[:12]
    return f"g-{seq:04d}:{digest}"


def package_of(document: dict):
    try:
        return build_package(
            {"taxonomy": document["taxonomy"], "concepts": document["concepts"]},
            document["glossaries"],
            document["dictionaries"],
        )
    except GlossaryInvalid as exc:
        raise InvalidArgument("пакет глоссария не сходится", extra={"labels": exc.labels}) from exc


def apply_ops(document: dict, ops: list[dict]) -> dict:
    updated = copy.deepcopy(document)
    for op in ops:
        if not isinstance(op, dict):
            raise InvalidArgument("op должен быть объектом")
        kind = op.get("op")
        concept = op.get("concept")
        glossary = updated["glossaries"].get(concept)
        if not isinstance(glossary, dict):
            raise InvalidArgument(f"нет понятия {concept}")
        if kind == "set_pref":
            lang, text = _lang_text(op)
            glossary.setdefault("pref", {})[lang] = text
        elif kind == "add_label":
            bucket = _bucket(glossary, op.get("kind"))
            lang, text = _lang_text(op)
            values = bucket.setdefault(lang, [])
            if isinstance(values, str):
                raise InvalidArgument("pref меняется через set_pref")
            if text not in values:
                values.append(text)
        elif kind == "remove_label":
            bucket = _bucket(glossary, op.get("kind"))
            lang, text = _lang_text(op)
            values = bucket.get(lang)
            if isinstance(values, list) and text in values:
                values.remove(text)
            elif values == text:
                bucket.pop(lang, None)
            else:
                raise InvalidArgument(f"метки нет: {text}")
        elif kind == "add_negative":
            text = op.get("text")
            if not isinstance(text, str) or not text:
                raise InvalidArgument("у отрицательной метки нужен text")
            values = glossary.get("negative") or []
            if isinstance(values, str):
                values = [values]
            if text not in values:
                values.append(text)
            glossary["negative"] = values
        else:
            raise InvalidArgument(f"неизвестный op {kind}")
    package_of(updated)
    return updated


def label_diff(before: dict, after: dict) -> list[dict]:
    old = _flat(before)
    new = _flat(after)
    changes = []
    for key in sorted(old):
        if key not in new:
            concept, kind, lang, text = key
            changes.append({"concept": concept, "kind": kind, "lang": lang, "text": text, "change": "remove"})
    for key in sorted(new):
        if key not in old:
            concept, kind, lang, text = key
            changes.append({"concept": concept, "kind": kind, "lang": lang, "text": text, "change": "add"})
    return changes


def _flat(document: dict) -> set[tuple[str, str, str, str]]:
    found: set[tuple[str, str, str, str]] = set()
    for concept, glossary in (document.get("glossaries") or {}).items():
        for kind in ("pref", "alt", "hidden"):
            bucket = glossary.get(kind) or {}
            if not isinstance(bucket, dict):
                continue
            for lang, value in bucket.items():
                texts = [value] if isinstance(value, str) else list(value or [])
                for text in texts:
                    found.add((str(concept), kind, str(lang), str(text)))
    return found


def _bucket(glossary: dict, kind: str) -> dict:
    if kind not in {"pref", "alt", "hidden"}:
        raise InvalidArgument("kind метки должен быть pref, alt или hidden")
    bucket = glossary.setdefault(kind, {})
    if not isinstance(bucket, dict):
        raise InvalidArgument("блок меток повреждён")
    return bucket


def _lang_text(op: dict) -> tuple[str, str]:
    lang, text = op.get("lang"), op.get("text")
    if not isinstance(lang, str) or not isinstance(text, str) or not text:
        raise InvalidArgument("у метки нужны lang и text")
    return lang, text
