"""Словари потоков и маркеров периода из configs/glossary/dictionaries.yaml.

Единая загрузка для каталога глоссария и domain/periods: YAML — источник
истины, Python-константы токены не дублируют.

Контракты
---------
Кэш: файл словарей считается неизменным на время жизни процесса. ``lru_cache``
на ``load_dictionaries`` намеренный; обновление — рестарт процесса.
``clear_dictionaries_cache`` — только для тестов и явного сброса. Релизы /
canary / rollback глоссария несут свои ``dictionaries`` в документе релиза и
не подменяют этот файл; сбрасывать кэш при activate не требуется.

Alt-каталог: ``marker_class(marker)`` без ``markers=`` всегда читает
``dictionaries_file()`` (configs_root). ``load_catalog(custom_path)`` кладёт
словари соседнего ``glossary/dictionaries.yaml`` в ``package.markers`` /
``package.flows``. Периодная классификация по нестандартному каталогу —
только с явным ``markers=package.markers``. Иначе возможен split-brain;
молчаливой подмены default-пути нет.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import yaml

from finance_analysis.domain.derive_fingerprint import configs_root
from finance_analysis.domain.glossary import GlossaryInvalid, parse_dictionary_groups


def dictionaries_file() -> Path:
    return configs_root() / "configs" / "glossary" / "dictionaries.yaml"


@lru_cache(maxsize=8)
def load_dictionaries(path: str | None = None) -> Mapping[str, Mapping[str, tuple[str, ...]]]:
    """Читает и строго валидирует dictionaries.yaml.

    path — явный файл; иначе ``dictionaries_file()``. Вложенные группы
    неизменяемы (MappingProxyType + tuple), без «починки» битых элементов.
    """

    file = Path(path) if path else dictionaries_file()
    if not file.is_file():
        raise GlossaryInvalid(["dictionaries"])
    raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise GlossaryInvalid(["dictionaries"])
    flows = parse_dictionary_groups(raw.get("flows"), "flows")
    markers = parse_dictionary_groups(raw.get("markers"), "markers")
    return MappingProxyType(
        {
            "flows": MappingProxyType(flows),
            "markers": MappingProxyType(markers),
        }
    )


def marker_token_sets(
    markers: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, frozenset[str]]:
    """Классы маркеров → frozenset токенов в casefold. Битые списки — GlossaryInvalid."""

    raw = markers if markers is not None else load_dictionaries()["markers"]
    parsed = parse_dictionary_groups(raw, "markers")
    return {key: frozenset(item.casefold() for item in values) for key, values in parsed.items()}


def plain_dictionaries(
    loaded: Mapping[str, Mapping[str, tuple[str, ...]]] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """JSON-безопасная копия для git-документа / релиза (без MappingProxyType)."""

    source = loaded if loaded is not None else load_dictionaries()
    return {
        "flows": {key: list(values) for key, values in source["flows"].items()},
        "markers": {key: list(values) for key, values in source["markers"].items()},
    }


def clear_dictionaries_cache() -> None:
    """Сброс кэша ``load_dictionaries``. Для тестов; в проде — рестарт процесса."""

    load_dictionaries.cache_clear()
