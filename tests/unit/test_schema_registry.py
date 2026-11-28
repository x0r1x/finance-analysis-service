"""Реестр публичных ответов: схема с версией или исключение с причиной и задачей.

Закрытый объект отвергает незнакомое имя, поэтому пробел схемы нельзя оставлять
молча. https://json-schema.org/understanding-json-schema/reference/object
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

_REPO = Path(__file__).resolve().parents[2]
_API = _REPO / "src" / "finance_analysis" / "adapters" / "api"
_METHODS = {"get", "post", "put", "delete", "patch"}
_TRACE_ID = "https://fas.local/contracts/meta_layer_graphs@2.0.json"
_VERSION = re.compile(r"@(\d+\.\d+)")
_GAP_IS_THE_GOAL = re.compile(
    r"пробел — норма|оставить без схемы|без схемы навсегда|желаемое конечное",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResponseRecord:
    name: str
    status: str
    reason: str = ""
    follow_up: str = ""
    wanted: str = ""
    schema_path: str = ""
    version: str = ""
    pointer: str = ""
    routes: tuple[str, ...] = ()


_ADD_SCHEMA = "Следующая задача — JSON Schema этого ответа. Этот PR схему не добавляет."
_CATALOG_ID = "https://fas.local/contracts/financial_model_catalog.json"


def _gap(
    name: str,
    reason: str,
    *routes: str,
    follow_up: str = _ADD_SCHEMA,
) -> ResponseRecord:
    return ResponseRecord(
        name=name,
        status="uncovered",
        reason=reason,
        follow_up=follow_up,
        wanted="schema",
        routes=routes,
    )


def _media(name: str, reason: str, follow_up: str, route: str) -> ResponseRecord:
    return ResponseRecord(
        name=name,
        status="other_media",
        reason=reason,
        follow_up=follow_up,
        routes=(route,),
    )


REGISTRY: tuple[ResponseRecord, ...] = (
    ResponseRecord(
        name="metricTrace",
        status="documented",
        schema_path="src/finance_analysis/domain/contracts/meta_layer_graphs.json",
        version="2.0",
        pointer="#/$defs/metricTrace",
        routes=("GET /v1/books/{job_id}/metrics/{metric_id}/trace",),
    ),
    ResponseRecord(
        name="financialModelCatalog",
        status="documented",
        schema_path="src/finance_analysis/domain/contracts/financial_model_catalog.json",
        version=_CATALOG_ID,
        routes=("GET /v1/metrics",),
    ),
    ResponseRecord(
        name="book_rows",
        status="documented",
        schema_path="src/finance_analysis/adapters/storage/schemas/book_rows.json",
        version="1.0",
    ),
    _gap(
        "formula_origin",
        "Ответ следа описан meta_layer_graphs@2.0. formula_origin этой схемой не описан, "
        "файла схемы аудита нет. Это текущий пробел, не цель.",
        follow_up=(
            "Следующая задача — схема аудита formula_origin с полным content_sha256. "
            "Этот PR схему не добавляет."
        ),
    ),
    _gap(
        "problem",
        "problem_response собирает application/problem+json без локального файла JSON Schema. "
        "Поля extra копируются в тело.",
    ),
    _gap(
        "operation_event",
        "JSON в поле data события SSE не описан файлом схемы. "
        "Поток text/event-stream этой записью не подменяется.",
    ),
    _media(
        "prometheus",
        "Тело — текст Prometheus, не JSON-объект.",
        "Следующая задача — не заменять этот текст JSON. Схема понадобится, только если тело станет JSON.",
        "GET /metrics",
    ),
    _media(
        "operation_events",
        "HTTP-ответ — text/event-stream, не JSON-документ. JSON внутри data — запись operation_event.",
        "Следующая задача — не описывать поток схемой JSON-документа. Схема события — operation_event.",
        "GET /v1/operations/{op_id}/events",
    ),
    _gap(
        "health",
        "Тела /health/live и /health/ready не описаны JSON Schema.",
        "GET /health/live",
        "GET /health/ready",
    ),
    _gap(
        "capabilities",
        "Тело GET /v1/capabilities не описано JSON Schema. "
        "parameters инструментов — схема входа, не этого ответа.",
        "GET /v1/capabilities",
    ),
    _gap(
        "book",
        "JSON книги, сборки, привязки, семантики, покрытия, вопросов, решений, ряда, среза, "
        "выражения, периодов и загрузки не описан JSON Schema.",
        "GET /v1/books/{job_id}",
        "GET /v1/books/{job_id}/builds",
        "GET /v1/books/{job_id}/builds/{build_key}",
        "GET /v1/books/{job_id}/coverage",
        "GET /v1/books/{job_id}/decisions",
        "GET /v1/books/{job_id}/mapping",
        "GET /v1/books/{job_id}/questions",
        "GET /v1/books/{job_id}/semantics",
        "POST /v1/books/{job_id}/decisions",
        "POST /v1/books/{job_id}/expression",
        "POST /v1/books/{job_id}/periods:resolve",
        "POST /v1/books/{job_id}/series",
        "POST /v1/books/{job_id}/slice",
        "POST /v1/books/{job_id}:load",
    ),
    _gap(
        "mapping_infer",
        "Ответ 202 пересчёта привязки — операция без JSON Schema.",
        "POST /v1/books/{job_id}/mapping:infer",
    ),
    _gap(
        "analysis",
        "Конверт анализа, список, сравнение, удаление и отчёт json|md не описаны JSON Schema. "
        "book_rows и formula_origin — отдельные записи и не заменяют конверт.",
        "DELETE /v1/books/{job_id}/analyses/{analysis_id}",
        "GET /v1/books/{job_id}/analyses",
        "GET /v1/books/{job_id}/analyses/{analysis_id}",
        "GET /v1/books/{job_id}/analyses/{analysis_id}/report",
        "POST /v1/books/{job_id}/analyses",
        "POST /v1/books/{job_id}:compare",
    ),
    _gap(
        "calculation_trace",
        "Список и тело улик анализа — не metricTrace. meta_layer_graphs@2.0 их не описывает.",
        "GET /v1/books/{job_id}/analyses/{analysis_id}/traces",
        "GET /v1/books/{job_id}/analyses/{analysis_id}/traces/{execution_id}",
        follow_up=(
            "Следующая задача — отдельная JSON Schema списка и тела улик анализа. "
            "Не поднимать $id meta_layer_graphs@2.0."
        ),
    ),
    _gap(
        "finding",
        "Список и одна находка не описаны JSON Schema. Колонки Parquet findings — не этот JSON.",
        "GET /v1/books/{job_id}/findings",
        "GET /v1/books/{job_id}/findings/{fingerprint}",
    ),
    _gap(
        "glossary",
        "JSON глоссария не описан JSON Schema. content может быть и не JSON, форма json — тоже без схемы.",
        "GET /v1/glossary",
        "GET /v1/glossary/concepts",
        "GET /v1/glossary/content",
        "GET /v1/glossary/diff",
        "GET /v1/glossary/events",
        "GET /v1/glossary/impact",
        "GET /v1/glossary/labels",
        "GET /v1/glossary/proposals",
        "GET /v1/glossary/proposals/{proposal_id}",
        "GET /v1/glossary/releases",
        "GET /v1/glossary/releases/{version}",
        "GET /v1/glossary/stats",
        "POST /v1/glossary/bootstrap",
        "POST /v1/glossary/proposals",
        "POST /v1/glossary/proposals:decide",
        "POST /v1/glossary/releases",
        "POST /v1/glossary/transitions",
        "POST /v1/glossary:resolve",
        "POST /v1/glossary:rollback",
    ),
    _gap(
        "operation",
        "Список, одна операция и отмена не описаны JSON Schema.",
        "GET /v1/operations",
        "GET /v1/operations/{op_id}",
        "POST /v1/operations/{op_id}:cancel",
    ),
    _gap(
        "profile",
        "Список, чтение и запись профиля не описаны JSON Schema.",
        "GET /v1/profiles",
        "GET /v1/profiles/{profile}",
        "PUT /v1/profiles/{profile}",
    ),
    _gap(
        "metric_indicator",
        "Тело — поля показателя плюс catalog_version. $defs.indicator закрыт "
        "additionalProperties false и это имя отвергает. Отдельной схемы ответа нет.",
        "GET /v1/metrics/{metric_id}",
        follow_up=(
            "Следующая задача — JSON Schema ответа одного показателя, включая catalog_version. "
            "Тело этот PR не меняет."
        ),
    ),
)


def discover_handlers() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(_API.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                route = _route(deco)
                if route is None:
                    continue
                text = ast.get_source_segment(source, node) or ""
                found[route] = text
    return found


def discover_api_schemas() -> tuple[str, ...]:
    found: list[str] = []
    for path in sorted((_REPO / "src").rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and "$schema" in doc and "dataset" not in doc:
            found.append(str(path.relative_to(_REPO)))
    return tuple(found)


def embedded_names() -> tuple[str, ...]:
    names: list[str] = []
    analyses = (_REPO / "src/finance_analysis/application/analyses.py").read_text(encoding="utf-8")
    if "formula_origin" in analyses:
        names.append("formula_origin")
    problems = (_REPO / "src/finance_analysis/adapters/api/problems.py").read_text(encoding="utf-8")
    if "def problem_response" in problems:
        names.append("problem")
    operations = (_API / "route/operations.py").read_text(encoding="utf-8")
    if "def _sse" in operations:
        names.append("operation_event")
    return tuple(names)


def exception_errors(entry: ResponseRecord) -> tuple[str, ...]:
    errors: list[str] = []
    if entry.schema_path:
        errors.append("у исключения не должно быть схемы")
    if not entry.reason.strip():
        errors.append("нет причины")
    if not entry.follow_up.strip():
        errors.append("нет последующей задачи")
    elif "задач" not in entry.follow_up.casefold():
        errors.append("последующая запись не называет задачу")
    if _GAP_IS_THE_GOAL.search(entry.reason) or _GAP_IS_THE_GOAL.search(entry.follow_up):
        errors.append("пробел записан как цель")
    if entry.status == "uncovered":
        if entry.wanted != "schema":
            errors.append("uncovered допустим только как пробел на пути к схеме")
        if not _names_schema(entry.follow_up):
            errors.append("задача не называет схему")
    elif entry.status != "other_media":
        errors.append("статус исключения неизвестен")
    return tuple(errors)


def binding_errors(entry: ResponseRecord) -> tuple[str, ...]:
    errors: list[str] = []
    if entry.status != "documented":
        errors.append("привязка не documented")
    path = _REPO / entry.schema_path
    if not path.is_file():
        return ("нет файла схемы",)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "$schema" not in doc or "dataset" in doc:
        errors.append("файл не API-схема")
    try:
        node = _node(doc, entry.pointer)
    except (KeyError, TypeError) as exc:
        return (f"указатель схемы: {exc}",)
    if not isinstance(node, dict):
        errors.append("узел схемы не объект")
    stated = _declared_version(doc)
    if stated:
        if entry.version != stated:
            errors.append(f"версия {entry.version} не равна {stated} в файле")
    elif entry.version != doc.get("$id"):
        errors.append("в файле нет @версии; версия записи должна быть $id")
    if entry.name == "metricTrace":
        if doc.get("$id") != _TRACE_ID:
            errors.append("$id схемы 2.0 поднят")
        if entry.version != "2.0":
            errors.append("metricTrace не 2.0")
        if isinstance(node, dict) and node.get("additionalProperties") is not False:
            errors.append("metricTrace не закрытый объект")
    return tuple(errors)


def test_public_response_without_a_schema_is_a_named_exception() -> None:
    bare = ResponseRecord(
        name="probe",
        status="uncovered",
        follow_up="Следующая задача — JSON Schema.",
        wanted="schema",
    )
    assert "нет причины" in exception_errors(bare)
    silent = ResponseRecord(
        name="probe",
        status="uncovered",
        reason="файла схемы нет",
        wanted="schema",
    )
    assert "нет последующей задачи" in exception_errors(silent)
    goal = ResponseRecord(
        name="probe",
        status="uncovered",
        reason="пробел — норма",
        follow_up="Следующая задача — оставить без схемы навсегда",
        wanted="uncovered",
    )
    goal_errors = exception_errors(goal)
    assert "пробел записан как цель" in goal_errors
    assert "uncovered допустим только как пробел на пути к схеме" in goal_errors
    named = ResponseRecord(
        name="probe",
        status="uncovered",
        reason="файла схемы нет, это не цель",
        follow_up="Следующая задача — JSON Schema этого тела.",
        wanted="schema",
    )
    assert exception_errors(named) == ()

    schema = json.loads(
        (_REPO / "src/finance_analysis/domain/contracts/meta_layer_graphs.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$id"] == _TRACE_ID
    trace = schema["$defs"]["metricTrace"]
    assert trace["additionalProperties"] is False
    validator = Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], **trace}
    )
    body = {
        "metric_id": "dscr",
        "variant": None,
        "build_key": None,
        "model_id": None,
        "steps": [],
        "missing_trace": None,
        "integrity": [],
        "physical_lineage_complete": False,
    }
    assert list(validator.iter_errors(body)) == []
    rejected = {**body, "formula_origin": {}}
    assert any("formula_origin" in error.message for error in validator.iter_errors(rejected))

    api = (_REPO / "docs/ru/api.md").read_text(encoding="utf-8")
    assert "`formula_origin` ею не описан" in api

    handlers = discover_handlers()
    by_name = {entry.name: entry for entry in REGISTRY}
    assert len(by_name) == len(REGISTRY)
    owners: dict[str, ResponseRecord] = {}
    duplicates: list[str] = []
    for entry in REGISTRY:
        for route in entry.routes:
            if route in owners:
                duplicates.append(route)
            owners[route] = entry
    assert duplicates == []
    missing = sorted(set(handlers) - set(owners))
    assert missing == []
    extra = sorted(set(owners) - set(handlers))
    assert extra == []

    schema_names: dict[str, str] = {}
    for entry in REGISTRY:
        if not entry.schema_path:
            continue
        assert entry.schema_path not in schema_names
        schema_names[entry.schema_path] = entry.name
        assert binding_errors(entry) == ()
    assert set(schema_names) == set(discover_api_schemas())

    for route, source in handlers.items():
        entry = owners[route]
        if "StreamingResponse" in source or "CONTENT_TYPE_LATEST" in source:
            assert entry.status == "other_media"
            assert exception_errors(entry) == ()
        elif entry.schema_path:
            assert entry.status == "documented"
        else:
            assert entry.status == "uncovered"
            assert exception_errors(entry) == ()

    for name in embedded_names():
        assert name in by_name, name
        entry = by_name[name]
        assert entry.routes == ()
        assert exception_errors(entry) == ()
        assert entry.status == "uncovered"
        assert entry.wanted == "schema"

    mentioned = [
        path
        for path in discover_api_schemas()
        if "formula_origin" in (_REPO / path).read_text(encoding="utf-8")
    ]
    origin = by_name["formula_origin"]
    if mentioned:
        assert origin.schema_path in mentioned
        assert binding_errors(origin) == ()
    else:
        assert exception_errors(origin) == ()
        assert origin.status == "uncovered"
        assert origin.wanted == "schema"

    assert "metricTrace" in by_name
    assert "financialModelCatalog" in by_name
    metric_trace = by_name["metricTrace"]
    assert metric_trace.version == "2.0"
    assert metric_trace.routes == ("GET /v1/books/{job_id}/metrics/{metric_id}/trace",)
    assert "metric_trace_view" in handlers[metric_trace.routes[0]]
    catalog = by_name["financialModelCatalog"]
    assert catalog.routes == ("GET /v1/metrics",)
    assert "financial_model_catalog" in handlers[catalog.routes[0]]
    assert "GET /v1/metrics/{metric_id}" not in catalog.routes


def _route(deco: ast.expr) -> str | None:
    if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
        return None
    if deco.func.attr not in _METHODS:
        return None
    if not isinstance(deco.func.value, ast.Name) or deco.func.value.id != "app":
        return None
    if not deco.args or not isinstance(deco.args[0], ast.Constant):
        return None
    path = deco.args[0].value
    if not isinstance(path, str):
        return None
    return f"{deco.func.attr.upper()} {path}"


def _names_schema(text: str) -> bool:
    folded = text.casefold()
    return "схем" in folded or "schema" in folded


def _declared_version(doc: dict) -> str:
    for key in ("$id", "$comment"):
        found = _VERSION.search(str(doc.get(key, "")))
        if found:
            return found.group(1)
    return ""


def _node(doc: dict, pointer: str) -> object:
    if not pointer:
        return doc
    node: object = doc
    for part in pointer.removeprefix("#/").split("/"):
        if not isinstance(node, dict):
            raise TypeError(pointer)
        node = node[part]
    return node
