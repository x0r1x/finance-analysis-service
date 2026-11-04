"""Роль component и сценарий строки (§5.5.2).

Часть итога — строка, которую формула другого кандидата того же понятия
складывает в итог. Если формулы нет, часть ставится только когда одна и та
же конечная метка на одном листе стоит под разными родителями и родитель
называет долговой инструмент. Сценарий `alt` — блок стресса, оптимизма или
пессимизма. Базовый сценарий этим словам уступает.
"""

from __future__ import annotations

import json
import re

from finance_analysis.domain.glossary import label_scan, normalize_label
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.references import referenced_row, summed_row_refs

# Слова раздела сильнее слова «базовый». Основа должна начинать слово.
_WORD = re.compile(r"[^\W\d_]+")
_ALT = (
    "стресс",
    "stress",
    "оптимист",
    "optimist",
    "пессимист",
    "pessimist",
    "downside",
    "upside",
)
# Родитель называет инструмент, а не просто повторяет метку.
_DEBT = (
    "кредит",
    "заем",
    "облигац",
    "транш",
    "loan",
    "bond",
    "tranche",
    "credit line",
    "creditline",
)


def scenario_of(row: dict) -> str:
    """Возвращает `alt` или `base` по заголовкам блока и метке.

    `row` — строка книги. Смотрятся путь метки, родитель и сама метка.
    Основа «стресс», «оптимист», «пессимист», `downside` или `upside` даёт
    `alt`, только если она стоит в начале слова. Поэтому «стрессовый» и
    `stressed` дают `alt`, а «бесстрессовый» и `unstressed` остаются
    базовыми. Слово «базовый» рядом с такой основой не возвращает строку в
    базовый сценарий. Если основы нет, сценарий базовый.
    """

    parts = list(_path(row))
    for key in ("parent_label", "label"):
        text = row.get(key)
        if text:
            parts.append(str(text))
    folded = [label_scan(part) for part in parts if part]
    if any(word.startswith(stem) for part in folded for word in _WORD.findall(part) for stem in _ALT):
        return "alt"
    return "base"


def debt_instrument(text: str | None) -> bool:
    """Родитель называет кредит, заём, облигацию, линию или транш.

    `text` — подпись родителя. Слова ищутся без учёта регистра, `ё` как `е`.
    Одной метки или одного словаря мало: это только проверка родителя.
    """

    folded = label_scan(str(text or ""))
    if not folded:
        return False
    return any(word in folded for word in _DEBT)


def component_records(
    rows: list[dict],
    concepts: dict[str, str],
    links: list[dict] | None,
    *,
    skip: set[str],
) -> dict[str, dict]:
    """Поля `evidence` для частей итога одного понятия.

    `rows` — строки книги. `concepts` сопоставляет `row_key` кандидата с
    понятием. `links` — рёбра графа формул. `skip` — строки, которые уже
    ссылки и частью не становятся. Сначала формула суммы. Без формулы часть
    ставится только при повторе конечной метки на одном листе под разными
    родителями, если родитель — долговой инструмент. Отступ сам по себе
    роль не меняет. Ключ ответа — `row_key` части.
    """

    cells = _cells(rows)
    grouped: dict[str, list[dict]] = {}
    for link in links or []:
        key = link.get("row_key")
        if key:
            grouped.setdefault(str(key), []).append(link)
    edges: dict[str, set[str]] = {}
    by_key = {str(row.get("row_key")): row for row in rows if row.get("row_key")}
    for key, concept in concepts.items():
        if key in skip:
            continue
        row = by_key.get(key)
        if row is None:
            continue
        for part in _sum_targets(row, grouped.get(key), cells):
            if part == key or part in skip or concepts.get(part) != concept:
                continue
            edges.setdefault(part, set()).add(key)
    records: dict[str, dict] = {}
    for part, owners in edges.items():
        plain = [owner for owner in owners if owner not in edges]
        total = min(plain or owners)
        records[part] = _record(by_key.get(part), total, formula=True)
    _debt_parts(rows, concepts, skip, records)
    return records


def _record(row: dict | None, total: str, *, formula: bool) -> dict:
    parent = ""
    if row is not None:
        parent = normalize_label(str(row.get("parent_label") or ""))
    found = {"role": "component", "member": parent, "component_of": total}
    if formula:
        found["total_row"] = total
    return found


def _debt_parts(rows: list[dict], concepts: dict[str, str], skip: set[str], records: dict[str, dict]) -> None:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = str(row.get("row_key") or "")
        concept = concepts.get(key)
        if not key or not concept or key in skip or key in records:
            continue
        if row.get("formula") or row.get("has_formula"):
            continue
        label = normalize_label(str(row.get("label") or ""))
        sheet = sheet_name_key(str(row.get("sheet") or ""))
        if not label or not sheet:
            continue
        groups.setdefault((sheet, label, concept), []).append(row)
    for grouped in groups.values():
        if len(grouped) < 2:
            continue
        parents = {normalize_label(str(row.get("parent_label") or "")) for row in grouped}
        if len(parents) < 2:
            continue
        plain = [row for row in grouped if not debt_instrument(str(row.get("parent_label") or ""))]
        instruments = [row for row in grouped if debt_instrument(str(row.get("parent_label") or ""))]
        if not instruments:
            continue
        total = str(plain[0]["row_key"]) if len(plain) == 1 else None
        for row in instruments:
            key = str(row["row_key"])
            if total is None:
                records[key] = {
                    "role": "component",
                    "member": normalize_label(str(row.get("parent_label") or "")),
                    "component_of": concepts[key],
                }
                continue
            records[key] = _record(row, total, formula=False)


def _sum_targets(row: dict, links: list[dict] | None, cells: dict[tuple[str, int], str]) -> set[str]:
    """Строки других кандидатов, которые складывает именно формула суммы.

    Сумма по столбцам той же строки (`SUM(C30:Z30)`) не делает ссылкой
    чужую строку, даже если рядом есть формула смены знака. В часть итога
    попадают только ссылки той формулы, которая сама является суммой.
    """

    own = str(row.get("row_key") or "")
    sheet = str(row.get("sheet") or "")
    grouped: dict[str, list[dict]] = {}
    for link in links or []:
        grouped.setdefault(str(link.get("formula") or ""), []).append(link)
    if not grouped and row.get("formula"):
        grouped[str(row.get("formula"))] = []
    found: set[str] = set()
    for formula, items in grouped.items():
        parsed = summed_row_refs(formula, default_sheet=sheet)
        if parsed is None:
            continue
        local: set[str] = set()
        for link in items:
            ref = link.get("ref_cell")
            if not ref:
                continue
            target = _ref_row(str(ref), sheet, cells)
            if target and target != own:
                local.add(target)
        if local:
            found |= local
            continue
        for item in parsed:
            target = cells.get((sheet_name_key(item[0]), item[1]))
            if target and target != own:
                found.add(target)
    return found


def _ref_row(ref: str, default_sheet: str, cells: dict[tuple[str, int], str]) -> str | None:
    address = referenced_row(ref, default_sheet=default_sheet)
    if address is None:
        return None
    return cells.get((sheet_name_key(address[0]), address[1]))


def _cells(rows: list[dict]) -> dict[tuple[str, int], str]:
    found: dict[tuple[str, int], str] = {}
    for row in rows:
        number = row.get("row_num")
        sheet = row.get("sheet")
        key = row.get("row_key")
        if isinstance(number, int) and not isinstance(number, bool) and sheet and key:
            found[(sheet_name_key(str(sheet)), number)] = str(key)
    return found


def _path(row: dict) -> tuple[str, ...]:
    raw = row.get("label_path")
    if isinstance(raw, (list, tuple)):
        return tuple(str(part) for part in raw)
    text = row.get("label_path_json")
    if not isinstance(text, str) or not text:
        return ()
    try:
        found = json.loads(text)
    except json.JSONDecodeError:
        return ()
    if not isinstance(found, list):
        return ()
    return tuple(str(part) for part in found)
