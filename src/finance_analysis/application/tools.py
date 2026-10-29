"""Карточка tools для GET /v1/capabilities. FAS модель не вызывает.

Клиент выкидывает null, подставляет job_id в path и раскладывает остальные
аргументы по полю in (path, query, body). parameters — strict JSON Schema.
"""

from __future__ import annotations

from finance_analysis.application.analyses import (
    ANALYSIS_TYPES,
    RATIO_METRICS,
    SCOPE_LISTS,
    SCOPE_TEXT,
)
from finance_analysis.application.report import REPORT_FORMATS

_BOOK = "/v1/books/{job_id}"
_EMPTY = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}


def _text(description: str) -> dict:
    return {"type": "string", "description": description}


def _text_or_null(description: str) -> dict:
    return {"type": ["string", "null"], "description": description}


def _int_or_null(description: str) -> dict:
    return {"type": ["integer", "null"], "description": description}


def _enum_or_null(values, description: str) -> dict:
    return {"type": ["string", "null"], "enum": [*values, None], "description": description}


def _strings(description: str, *, enum=None, min_items: int | None = None) -> dict:
    items: dict = {"type": "string"}
    if enum is not None:
        items["enum"] = list(enum)
    schema: dict = {"type": "array", "items": items, "description": description}
    if min_items is not None:
        schema["minItems"] = min_items
    return schema


def _closed(properties: dict, *, description: str | None = None, nullable: bool = False) -> dict:
    schema: dict = {
        "type": ["object", "null"] if nullable else "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }
    if description:
        schema["description"] = description
    return schema


def _tool(name: str, description: str, method: str, path: str, parameters: dict, where: dict, *, strict: bool = True) -> dict:
    return {
        "name": name,
        "description": description,
        "method": method,
        "path": path,
        "parameters": parameters,
        "in": where,
        "strict": strict,
    }


def _where(parameters: dict, place: str) -> dict:
    return {name: place for name in parameters["properties"]}


def build_tools(*, decision_kinds: tuple[str, ...], measures: tuple[str, ...], dims: tuple[str, ...], ops: tuple[str, ...]) -> list[dict]:
    """Шестнадцать tools §3.4. Enum берутся из констант кода, не из скопированных строк."""

    scope_fields = {
        "sheets": {**_strings("Листы."), "type": ["array", "null"]},
        "row_keys": {**_strings("Строки."), "type": ["array", "null"]},
        "markers": {**_strings("Маркеры периодов."), "type": ["array", "null"]},
        "concepts": {**_strings("Понятия."), "type": ["array", "null"]},
        "axis_id": _text_or_null("Ось периода."),
        "period_from": _text_or_null("Начало интервала."),
        "period_to": _text_or_null("Конец интервала."),
    }
    scope = _closed(
        {key: scope_fields[key] for key in (*SCOPE_LISTS, *SCOPE_TEXT)},
        description="Ограничение прогона. null — вся книга.",
        nullable=True,
    )
    target = _closed(
        {
            "cell_id": _text_or_null("Ячейка, например CF!H40."),
            "row_key": _text_or_null("Строка книги."),
            "concept": _text_or_null("Понятие глоссария."),
        },
        description="Ровно одно поле непустое для impact.",
    )
    metrics = _strings("Метрики покрытия.", enum=RATIO_METRICS, min_items=1)
    rules = {"type": ["array", "null"], "items": {"type": "string"}, "description": "Коды правил. null — все, пустой список — ни одного."}
    flag = {"type": "boolean", "description": "true — ответить 202 и считать в операции."}
    binding = _closed(
        {
            "row_key": _text_or_null("Строка."),
            "binding_key": _text_or_null("Ключ привязки."),
            "period_id": _text_or_null("Период."),
            "axis_id": _text_or_null("Ось периода."),
        },
        description="Одна привязка выражения. Нужен row_key или binding_key.",
    )
    series = _closed(
        {
            "row_keys": _strings("Строки. Хотя бы один из трёх списков непустой."),
            "binding_keys": _strings("Ключи привязок."),
            "concepts": _strings("Понятия."),
            "periods": _strings("Периоды. Пустой список — все."),
            "axis_id": _text_or_null("Ось периода."),
            "marker": _text_or_null("Маркер периода."),
        }
    )
    time_item = _closed(
        {
            "dimension": {"type": "string", "enum": ["period_start"], "description": "Измерение времени."},
            "granularity": _text("Шаг."),
            "dateRange": _strings("Границы диапазона."),
        }
    )
    filters = {
        "type": "array",
        "description": "Фильтры среза. Пустой список — без фильтра.",
        "items": _closed(
            {
                "dimension": {"type": "string", "enum": list(dims), "description": "Измерение."},
                "operator": {"type": "string", "enum": list(ops), "description": "Оператор."},
                "value": _text_or_null("Значение. null для is_null."),
            }
        ),
    }
    sliced = _closed(
        {
            "measures": _strings("Меры среза.", enum=measures, min_items=1),
            "dimensions": _strings("Группировка. Пустой список допустим.", enum=dims),
            "filters": filters,
            "time": {"type": ["array", "null"], "items": time_item, "description": "Ось времени. null — без неё."},
        }
    )
    expression = _closed(
        {
            "expression": _text("Выражение, например a - b."),
            "bindings": {
                "type": "object",
                "description": "Имена привязок задаёт выражение.",
                "additionalProperties": binding,
                "properties": {},
                "required": [],
            },
        }
    )
    analysis = _closed(
        {
            "type": {"type": "string", "enum": list(ANALYSIS_TYPES), "description": "Вид анализа."},
            "render": _enum_or_null(REPORT_FORMATS, "Формат отчёта."),
            "build_key": _text_or_null("Сборка. null — текущая голова."),
            "async": flag,
            "rules": rules,
            "scope": scope,
            "metrics": metrics,
            "target": target,
            "direction": _enum_or_null(("precedents", "dependents"), "Направление графа для impact."),
            "depth": _int_or_null("Глубина графа. null — глубина по умолчанию."),
        }
    )
    findings = _closed(
        {
            "rule": _text_or_null("Коды правил через запятую."),
            "severity": _text_or_null("Уровни через запятую."),
            "concept": _text_or_null("Понятие."),
            "build_key": _text_or_null("Сборка."),
            "page_token": _text_or_null("Токен следующей страницы."),
            "page_size": _int_or_null("Размер страницы."),
        }
    )
    base = _closed(
        {
            "build_key": _text_or_null("Сборка."),
            "scenario": _text_or_null("Сценарий."),
        },
        description="Левая сторона сравнения.",
    )
    other = _closed(
        {
            "build_key": _text_or_null("Сборка."),
            "scenario": _text_or_null("Сценарий."),
            "job_id": _text_or_null("Вторая книга."),
        },
        description="Правая сторона. job_id — другая книга, не сессия.",
    )
    compared = _closed(
        {
            "base": base,
            "other": other,
            "metrics": metrics,
            "rules": rules,
            "async": flag,
        }
    )
    decision = _closed(
        {
            "kind": {"type": "string", "enum": list(decision_kinds), "description": "Вид решения."},
            "target": _text("Цель: строка, период или book."),
            "value": _text_or_null("Новое значение."),
            "expected_seq": _int_or_null("Ожидаемый seq слота."),
            "supersedes": _closed(
                {"seq": {"type": "integer", "description": "Seq заменяемого решения."}},
                description="Замена прежнего решения. null — нет.",
                nullable=True,
            ),
        }
    )
    decisions = _closed(
        {"decisions": {"type": "array", "minItems": 1, "items": decision, "description": "Пакет решений."}}
    )
    report = _closed(
        {
            "analysis_id": _text("Идентификатор анализа."),
            "format": _enum_or_null(REPORT_FORMATS, "Формат отчёта."),
        }
    )
    operation = _closed(
        {
            "op_id": _text("Идентификатор операции."),
            "wait_ms": _int_or_null("Сколько ждать завершения, мс. null — не ждать."),
        }
    )
    concept = _closed(
        {
            "label": _text_or_null("Метка. Вместе с path_text нельзя."),
            "path_text": _text_or_null("Путь метки. Берётся последний сегмент."),
            "unit": _text_or_null("Единица строки."),
            "profile_id": _text_or_null("Профиль книги."),
            "version": _text_or_null("Релиз глоссария. null — активный."),
        }
    )
    periods = _closed({"text": _text("Фраза про период, например первый операционный год.")})
    mapping = _closed(
        {
            "status": _text_or_null("Статус привязки."),
            "concept": _text_or_null("Понятие или эффективное понятие."),
            "importance": _text_or_null("Важность."),
            "q": _text_or_null("Подстрока пути метки."),
        }
    )
    return [
        _tool("get_book", "Голова книги и предупреждения загрузки.", "GET", _BOOK, _EMPTY, {}),
        _tool("get_coverage", "Покрытие книги понятиями.", "GET", f"{_BOOK}/coverage", _EMPTY, {}),
        _tool("get_mapping", "Строки привязки. counts считаются до фильтра.", "GET", f"{_BOOK}/mapping", mapping, _where(mapping, "query")),
        _tool("get_semantics", "Семантический слой книги.", "GET", f"{_BOOK}/semantics", _EMPTY, {}),
        _tool("resolve_periods", "Периоды по фразе.", "POST", f"{_BOOK}/periods:resolve", periods, _where(periods, "body")),
        _tool("get_series", "Значения строк по периодам. Хотя бы один из списков row_keys, binding_keys, concepts непустой.", "POST", f"{_BOOK}/series", series, _where(series, "body")),
        _tool("get_slice", "Срез куба series.", "POST", f"{_BOOK}/slice", sliced, _where(sliced, "body")),
        _tool(
            "evaluate_expression",
            "Выражение по привязкам строк.",
            "POST",
            f"{_BOOK}/expression",
            expression,
            _where(expression, "body"),
            strict=False,
        ),
        _tool("run_analysis", "Аудит, коэффициенты, влияние или полный прогон.", "POST", f"{_BOOK}/analyses", analysis, _where(analysis, "body")),
        _tool("list_findings", "Находки последнего аудита.", "GET", f"{_BOOK}/findings", findings, _where(findings, "query")),
        _tool(
            "explain_finding",
            "Пояснение одной находки.",
            "GET",
            f"{_BOOK}/findings/{{fingerprint}}",
            _closed(
                {
                    "fingerprint": _text("Отпечаток находки."),
                    "build_key": _text_or_null("Сборка. null — текущая голова."),
                    "direction": _enum_or_null(("precedents", "dependents"), "Направление графа."),
                    "depth": _int_or_null("Глубина графа. null — глубина по умолчанию."),
                }
            ),
            {"fingerprint": "path", "build_key": "query", "direction": "query", "depth": "query"},
        ),
        _tool("compare", "Сравнение сборок, сценариев или двух книг.", "POST", f"{_BOOK}:compare", compared, _where(compared, "body")),
        _tool("submit_decisions", "Пакет решений по книге.", "POST", f"{_BOOK}/decisions", decisions, _where(decisions, "body")),
        _tool("get_report", "Отчёт анализа.", "GET", f"{_BOOK}/analyses/{{analysis_id}}/report", report, {"analysis_id": "path", "format": "query"}),
        _tool("get_operation", "Состояние операции.", "GET", "/v1/operations/{op_id}", operation, {"op_id": "path", "wait_ms": "query"}),
        _tool("resolve_concept", "Понятие по метке или пути. Ничего не записывает.", "POST", "/v1/glossary:resolve", concept, _where(concept, "body")),
    ]
