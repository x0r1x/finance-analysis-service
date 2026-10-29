"""Экспорт определений в Apache Ossie. Без данных книг и без путей к Parquet (§5.1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from finance_analysis.application.catalog import catalog_file
from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.errors import DependencyUnavailable, NotFound

OSSIE_VERSION = "0.2.0.dev0"
_SCHEMA = Path(__file__).resolve().parents[3] / "configs" / "ossie" / "ossie-schema.json"
_RATIO_SQL = {
    "dscr": "SUM(CASE WHEN concept='cfads' THEN value END) / NULLIF(SUM(CASE WHEN concept='debt_service' THEN value END), 0)",
    "icr": "SUM(CASE WHEN concept='ebitda' THEN value END) / NULLIF(SUM(CASE WHEN concept='interest' THEN value END), 0)",
}
_STUBS = ("llcr", "plcr")


def schema_path() -> Path:
    return _SCHEMA


def _expr(*pairs: tuple[str, str]) -> dict:
    return {"dialects": [{"dialect": dialect, "expression": expression} for dialect, expression in pairs]}


def _field(name: str, datatype: str, *, time: bool = False, synonyms: list[str] | None = None) -> dict:
    body = {"name": name, "expression": _expr(("ANSI_SQL", name)), "datatype": datatype}
    if time:
        body["dimension"] = {"is_time": True}
    if synonyms:
        body["ai_context"] = {"synonyms": synonyms}
    return body


def _texts(glossary: dict, profile_id: str | None) -> list[str]:
    found: list[str] = []

    def take(bucket) -> None:
        if isinstance(bucket, str):
            found.append(bucket)
        elif isinstance(bucket, dict):
            for value in bucket.values():
                take(value)
        elif isinstance(bucket, list):
            found.extend(item for item in bucket if isinstance(item, str))

    for kind in ("pref", "alt", "hidden"):
        take(glossary.get(kind))
    if profile_id:
        take((glossary.get("scoped") or {}).get(profile_id))
    unique = []
    for text in found:
        if text and text not in unique:
            unique.append(text)
    return unique


def build_document(document: dict, *, glossary_version: str, profile_id: str | None, profile_version: str, metrics_text: str) -> dict:
    concepts = document.get("concepts") or {}
    glossaries = document.get("glossaries") or {}
    synonyms: list[str] = []
    extras: dict[str, dict] = {}
    for name in sorted(concepts):
        gloss = glossaries.get(name) or {}
        labels = _texts(gloss, profile_id)
        synonyms.extend(label for label in labels if label not in synonyms)
        concept = concepts[name] if isinstance(concepts[name], dict) else {}
        extras[name] = {
            "broader": gloss.get("broader"),
            "negative": list(gloss.get("negative") or []),
            "xref": concept.get("xref"),
        }
    taxonomy = str(document.get("taxonomy") or "core")
    metrics = [
        {
            "name": name,
            "description": "Считает FAS в Decimal; выражение справочное.",
            "expression": _expr(("ANSI_SQL", sql), ("OSSIE_SQL_2026", sql)),
            "datatype": "Decimal",
        }
        for name, sql in _RATIO_SQL.items()
    ]
    for name in _STUBS:
        metrics.append(
            {
                "name": name,
                "description": "Окно NPV считает FAS. SQL-агрегата нет.",
                "expression": _expr(("ANSI_SQL", "SELECT NULL")),
                "datatype": "Decimal",
            }
        )
    extension = {
        "taxonomy_version": taxonomy,
        "glossary_version": glossary_version,
        "profile_version": profile_version,
        "concepts": extras,
        "metrics_yaml": metrics_text,
    }
    return {
        "version": OSSIE_VERSION,
        "name": "fas_semantic_model",
        "description": "Определения FAS. Расчёт выполняет FAS, документ данных книг не содержит.",
        "ai_context": {"instructions": "Модель описывает понятия и метрики FAS. Значения книг здесь нет."},
        "datasets": [
            {
                "name": "series",
                "source": "fas.series",
                "description": "Логическое имя модели Wren, не путь к файлу.",
                "fields": [
                    _field("concept", "String", synonyms=synonyms),
                    _field("period_start", "Date", time=True),
                    _field("period_id", "String"),
                    _field("period_marker", "String"),
                    _field("phase", "String"),
                    _field("value", "Decimal"),
                ],
            },
            {
                "name": "concepts",
                "source": "fas.concepts",
                "fields": [
                    _field("concept_id", "String"),
                    _field("broader", "String"),
                    _field("unit", "String"),
                    _field("expected_sign", "String"),
                    _field("pref_ru", "String"),
                    _field("pref_en", "String"),
                ],
            },
        ],
        "relationships": [],
        "metrics": metrics,
        "custom_extensions": [{"vendor_name": "FAS", "data": json.dumps(extension, ensure_ascii=False, sort_keys=True)}],
    }


def render_md(document: dict) -> str:
    lines = [f"# {document['name']}", "", document.get("description") or ""]
    for dataset in document.get("datasets") or []:
        lines.extend(["", f"## {dataset['name']}", dataset.get("description") or ""])
        for field in dataset.get("fields") or []:
            lines.append(f"- {field['name']} ({field.get('datatype')})")
    lines.extend(["", "## metrics"])
    for metric in document.get("metrics") or []:
        dialect = metric["expression"]["dialects"][0]
        lines.append(f"- {metric['name']}: {dialect['expression']}")
    return "\n".join(lines).rstrip() + "\n"


def _metrics_text() -> str:
    path = catalog_file().parent.parent / "metrics" / "coverage.yaml"
    return path.read_text(encoding="utf-8")


def _metrics_version(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _profile_name(profile_id: str | None) -> str | None:
    name = (profile_id or "").split("@", 1)[0]
    if not name or name == "p-0":
        return None
    return name


async def export_model(glossary, support, *, glossary_version: str | None, profile_id: str | None, fmt: str) -> tuple[int, bytes, str, str]:
    """JSON кэшируется по версиям. yaml и md собираются из него. ETag включает формат."""

    raw, _media = await glossary.content(glossary_version, "json")
    document = json.loads(raw)
    version = glossary_version or (await glossary.ensure())["active"]
    profile = _profile_name(profile_id)
    if profile:
        pinned = await glossary.profile_ref(profile)
        if pinned is None:
            raise NotFound("профиль не найден", extra={"profile_id": profile})
    else:
        pinned = "none"
    metrics = _metrics_text()
    taxonomy = str(document.get("taxonomy") or "core")
    base = f"osi:{taxonomy}:{version}:{_metrics_version(metrics)}:{pinned}"
    cached = await support.cache_get(f"fas:osi:{base}")
    if cached:
        model = json.loads(cached)
    else:
        model = build_document(
            document,
            glossary_version=str(version),
            profile_id=profile,
            profile_version=pinned,
            metrics_text=metrics,
        )
        try:
            await support.cache_set(f"fas:osi:{base}", canonical_json(model).encode(), 86_400)
        except DependencyUnavailable:
            pass
    etag = f"{base}:{fmt}"
    if fmt == "yaml":
        body = yaml.safe_dump(model, allow_unicode=True, sort_keys=True).encode()
        media = "application/yaml"
    elif fmt == "md":
        body = render_md(model).encode()
        media = "text/markdown; charset=utf-8"
    else:
        body = canonical_json(model).encode()
        media = "application/json"
    return 200, body, media, etag
