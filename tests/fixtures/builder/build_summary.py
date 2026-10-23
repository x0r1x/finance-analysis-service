"""Тело GET /summary из публикации фикстуры.

Живой checkout `x0r1x/finance-context-builder` @ 8f0b1b9 из этой среды
недоступен. Функция повторяет поле `SummaryDocument` (`summary-2`), которое
маршрут `/summary` собирает из `context.json` и `graph.json`:
`warnings` — список `context.warnings`, `missing_cached_values` — число из
`workbook`. `meta.json` не читается.

Запуск из корня репозитория перезаписывает `summary.json` обеих книг:

    python3 tests/fixtures/builder/build_summary.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build_summary(context: dict, graph: dict) -> dict:
    meta = context["meta"]
    workbook = context["workbook"]
    return {
        "context_schema_version": context["schema_version"],
        "graph_schema_version": graph["schema_version"],
        "source_filename": meta["source_filename"],
        "content_sha256": meta["content_sha256"],
        "status": meta["status"],
        "stage": meta["stage"],
        "sheets": list(workbook["sheets"]),
        "formula_count": workbook["formula_count"],
        "missing_cached_values": workbook["missing_cached_values"],
        "unparsed_formulas": workbook["unparsed_formulas"],
        "iterate": graph["iterate"],
        "defined_name_count": len(workbook["defined_names"]),
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "kinds": graph["kinds"],
        "unresolved": graph["unresolved"],
        "external": graph["external"],
        "dangling": graph["dangling"],
        "dynamic": graph["dynamic"],
        "truncated": graph["truncated"],
        "dangling_classes": graph["dangling_classes"],
        "cycles": graph["cycles"],
        "circularity_hints": graph["circularity_hints"],
        "warnings": list(context["warnings"]),
    }


def write_job(folder: Path) -> None:
    context = json.loads((folder / "context.json").read_text(encoding="utf-8"))
    graph = json.loads((folder / "graph.json").read_text(encoding="utf-8"))
    body = build_summary(context, graph)
    text = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    (folder / "summary.json").write_text(text, encoding="utf-8")


def main() -> None:
    for folder in sorted(path for path in ROOT.iterdir() if path.is_dir()):
        if (folder / "context.json").is_file() and (folder / "graph.json").is_file():
            write_job(folder)


if __name__ == "__main__":
    main()
