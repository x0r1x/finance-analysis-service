"""Словари потоков и маркеров периода из configs/glossary/dictionaries.yaml.

Единая загрузка для каталога глоссария и domain/periods: YAML — источник
истины, Python-константы токены не дублируют.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import yaml

from finance_analysis.domain.derive_fingerprint import configs_root
from finance_analysis.domain.glossary import GlossaryInvalid


def dictionaries_file() -> Path:
    return configs_root() / "configs" / "glossary" / "dictionaries.yaml"


@lru_cache(maxsize=8)
def load_dictionaries(path: str | None = None) -> Mapping[str, object]:
    """Читает dictionaries.yaml. path — явный файл; иначе каталог конфигов."""

    file = Path(path) if path else dictionaries_file()
    if not file.is_file():
        raise GlossaryInvalid(["dictionaries"])
    raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid(["dictionaries"])
    return MappingProxyType(raw)


def marker_token_sets(
    markers: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, frozenset[str]]:
    """Классы маркеров → frozenset токенов в casefold."""

    raw = markers if markers is not None else load_dictionaries().get("markers")
    if not isinstance(raw, Mapping):
        raise GlossaryInvalid(["markers"])
    out: dict[str, frozenset[str]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not isinstance(values, (list, tuple)):
            raise GlossaryInvalid(["markers", str(key)])
        out[key] = frozenset(str(item).casefold() for item in values if isinstance(item, str) and item)
    return out


def clear_dictionaries_cache() -> None:
    load_dictionaries.cache_clear()
