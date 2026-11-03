"""Локальная проверка типа книги К3. В CI файла нет — тест пропускается.

Ожидаемый тип лежит рядом с книгой в `.local.yaml` и в репозиторий не входит.
Имя клиента в тесте не пишется.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.model_type import infer

_PATH = os.environ.get("FAS_LOCAL_BOOK_K3")


@pytest.mark.skipif(not _PATH, reason="FAS_LOCAL_BOOK_K3 не задан")
def test_k3_type_matches_local_expectation():
    book = Path(_PATH or "")
    if not book.is_file():
        pytest.skip("файл К3 не найден")
    spec_path = book.with_suffix(".local.yaml")
    if not spec_path.is_file():
        pytest.skip("ожидания К3 лежат в соседнем .local.yaml и не коммитятся")
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    primary = spec.get("primary")
    if not isinstance(primary, str):
        pytest.skip("в .local.yaml нет primary")
    got = infer(
        load_model_types(),
        bound=frozenset(spec.get("bound") or ()),
        sheets=frozenset(spec.get("sheets") or ()),
        accept=0.6,
        gap=0.15,
    )
    assert got.primary == primary
