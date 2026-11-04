"""Локальная проверка чужой модели девелопмента. В CI файлов нет — тест пропускается.

Каталог задаёт FAS_LOCAL_DIR_DEV_ESCROW. У каждого xlsx рядом лежит .local.yaml
со схемой и ожиданием. Имена файлов в репозиторий не пишутся, числа из книг тоже.
Цитата: Buildings 15(16):2843. Книги не лицензированы и не коммитятся.
"""

from __future__ import annotations

import os
from pathlib import Path

import openpyxl
import pytest
import yaml

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.model_type import infer
from tests.dev_escrow_expect import assert_variant

_DIR = os.environ.get("FAS_LOCAL_DIR_DEV_ESCROW")


def _books() -> list[Path]:
    if not _DIR:
        return []
    root = Path(_DIR)
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("*.xlsx") if path.is_file())


def pytest_generate_tests(metafunc) -> None:
    if "book" not in metafunc.fixturenames:
        return
    found = _books()
    if not found:
        metafunc.parametrize("book", [None], ids=["no-local-files"])
        return
    metafunc.parametrize("book", found, ids=[path.stem for path in found])


def _resolved(book: Path) -> tuple[frozenset[str], frozenset[str]]:
    package = load_catalog()
    workbook = openpyxl.load_workbook(book, data_only=False, read_only=True)
    bound: set[str] = set()
    try:
        sheets = frozenset(workbook.sheetnames)
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    text = cell.value
                    if not isinstance(text, str) or not text.strip() or text.startswith("="):
                        continue
                    found = package.resolve(text)
                    if found is not None:
                        bound.add(found.concept)
    finally:
        workbook.close()
    return frozenset(bound), sheets


def test_external_model_type_follows_its_local_yaml(book):
    if book is None:
        pytest.skip("FAS_LOCAL_DIR_DEV_ESCROW не задан или в каталоге нет xlsx")
    spec_path = Path(book).with_suffix(".local.yaml")
    if not spec_path.is_file():
        pytest.skip("ожидания лежат в соседнем .local.yaml и не коммитятся")
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    bound, sheets = _resolved(Path(book))
    got = infer(load_model_types(), bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    assert_variant(got, spec, accept=0.6)
