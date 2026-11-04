"""Понятия книги — то, что glossary.resolve находит в подписях ячеек."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from finance_analysis.application.catalog import load_catalog

_ROOT = Path(__file__).resolve().parent / "fixtures" / "model_books"


def resolved_workbook(relative: str) -> tuple[frozenset[str], frozenset[str]]:
    package = load_catalog()
    book = openpyxl.load_workbook(_ROOT / relative, data_only=False)
    bound: set[str] = set()
    try:
        sheets = frozenset(book.sheetnames)
        for sheet in book.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    text = cell.value
                    if not isinstance(text, str) or not text.strip() or text.startswith("="):
                        continue
                    found = package.resolve(text)
                    if found is not None:
                        bound.add(found.concept)
    finally:
        book.close()
    return frozenset(bound), sheets
