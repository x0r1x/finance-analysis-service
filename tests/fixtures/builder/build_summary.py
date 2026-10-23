"""Тело GET /summary из публикации фикстуры.

Скрипт повторяет сборку `SummaryDocument` (`summary-2`), которую маршрут
`/summary` делает из `context.json`, `graph.json` и, если файл есть,
`meta.json`. Репозиторий `x0r1x/finance-context-builder` @ 8f0b1b9 из этой
среды недоступен, поэтому функция не импортирует код builder и следует
сверенной форме:

- `schema_version` — `"summary-2"`;
- `cycles` — `{id, class, members}`, где `members` это число членов;
- `circularity_hints` — `{sheet, row, label}` без `cell_ids`;
- `iterate` — `workbook.iterate`;
- `source_filename`, `content_sha256`, `status`, `stage` — из `meta.json`,
  иначе из `context.meta`;
- `warnings` — список `context.warnings`;
- `missing_cached_values` — число из `workbook`.

Запуск из корня репозитория перезаписывает `summary.json` обеих книг:

    python3 tests/fixtures/builder/build_summary.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _cycle(item: dict) -> dict:
    return {"id": item["id"], "class": item["class"], "members": len(item["members"])}


def _hint(item: dict) -> dict:
    return {"sheet": item["sheet"], "row": item["row"], "label": item["label"]}


def build_summary(context: dict, graph: dict, meta: dict | None = None) -> dict:
    identity = meta if meta is not None else context["meta"]
    workbook = context["workbook"]
    return {
        "schema_version": "summary-2",
        "context_schema_version": context["schema_version"],
        "graph_schema_version": graph["schema_version"],
        "source_filename": identity["source_filename"],
        "content_sha256": identity["content_sha256"],
        "status": identity["status"],
        "stage": identity["stage"],
        "sheets": list(workbook["sheets"]),
        "formula_count": workbook["formula_count"],
        "missing_cached_values": workbook["missing_cached_values"],
        "unparsed_formulas": workbook["unparsed_formulas"],
        "iterate": workbook["iterate"],
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
        "cycles": [_cycle(item) for item in graph["cycles"]],
        "circularity_hints": [_hint(item) for item in graph["circularity_hints"]],
        "warnings": list(context["warnings"]),
    }


def write_job(folder: Path) -> None:
    context = json.loads((folder / "context.json").read_text(encoding="utf-8"))
    graph = json.loads((folder / "graph.json").read_text(encoding="utf-8"))
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else None
    body = build_summary(context, graph, meta)
    text = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    (folder / "summary.json").write_text(text, encoding="utf-8")


def main() -> None:
    for folder in sorted(path for path in ROOT.iterdir() if path.is_dir()):
        if (folder / "context.json").is_file() and (folder / "graph.json").is_file():
            write_job(folder)


if __name__ == "__main__":
    main()
