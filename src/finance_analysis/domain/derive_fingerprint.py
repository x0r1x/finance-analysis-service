"""Отпечаток файлов, от которых зависит производное состояние.

Список путей объявлен в `PACKAGE_SOURCES` и `CONFIG_SOURCES`. Хеш
подставляется в `derive_key` вместо ручного счётчика. Правка любого из
этих файлов меняет ключ сама. Переводы строк приводятся к LF, поэтому
одни и те же байты текста дают один хеш.

Код читается из установленного пакета `finance_analysis`, а не из каталога
`src/` репозитория. Конфиги читаются из каталога, который находится тем же
обходом, что и файл таксономии. Поэтому установка в образ и рабочая копия
дают один и тот же отпечаток. Версия глоссария в список не входит: её
задаёт релиз, а не эти файлы. `sheet_roles_version` остаётся отдельным
входом ключа: это хеш уже разобранных ролей листа.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

# Выбор строки и роли листа живут в mapping.py. Отдельного модуля способа
# показа периода ещё нет: когда он появится, его путь добавляется сюда.
# Путь указан от каталога пакета, без `src/finance_analysis`: в образе
# пакет лежит в site-packages, а не в дереве исходников.
PACKAGE_SOURCES = (
    "domain/derive_fingerprint.py",
    "domain/mapping.py",
    "domain/components.py",
    "domain/references.py",
    "domain/semantics.py",
    "domain/glossary.py",
    "domain/candidates.py",
    "domain/calibration.py",
    "domain/model_type.py",
    "domain/periods.py",
    "domain/phases.py",
    "domain/currency.py",
    "domain/state.py",
    "application/project.py",
    "application/sheet_roles.py",
    "application/catalog.py",
    "application/mapping_pipeline.py",
)
CONFIG_SOURCES = (
    "configs/sheet_roles.yaml",
    "configs/concepts/core.yaml",
    "configs/model_types",
)


def derive_fingerprint(root: Path | None = None) -> str:
    """Возвращает sha256 объявленных файлов.

    Без аргумента код берётся из пакета, в котором лежит этот модуль, а
    конфиги — из каталога с `configs/concepts/core.yaml`. `root` задаёт
    рабочую копию: пакет в `src/finance_analysis`, конфиги рядом с `src`.
    Подписи путей в хеше одинаковы в обеих раскладках. Перевод строки CRLF
    и одиночный CR считаются как LF.
    """

    if root is None:
        return _live_fingerprint()
    return _fingerprint(root / "src" / "finance_analysis", root)


def package_root() -> Path:
    """Возвращает каталог пакета `finance_analysis` этой установки."""

    return Path(__file__).resolve().parents[1]


def configs_root() -> Path:
    """Возвращает каталог, в котором лежит `configs/concepts/core.yaml`.

    Обход совпадает с поиском таксономии: в рабочей копии это корень
    репозитория, в образе — каталог, куда скопированы конфиги.
    """

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "configs" / "concepts" / "core.yaml").is_file():
            return parent
    raise FileNotFoundError("Каталог конфигов не найден: нет configs/concepts/core.yaml.")


def _fingerprint(package: Path, configs: Path) -> str:
    digest = hashlib.sha256()
    for path, body in _files(package, configs):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def _files(package: Path, configs: Path) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for item in PACKAGE_SOURCES:
        found.extend(_read(package, item))
    for item in CONFIG_SOURCES:
        found.extend(_read(configs, item))
    found.sort()
    return found


def _read(root: Path, item: str) -> list[tuple[str, bytes]]:
    path = root / item
    if path.is_dir():
        files = sorted(file for file in path.rglob("*") if file.is_file() and "__pycache__" not in file.parts)
        if not files:
            raise FileNotFoundError(f"Каталог отпечатка свёртки пуст: {item}.")
        return [(file.relative_to(root).as_posix(), _lf(file.read_bytes())) for file in files]
    if not path.is_file():
        raise FileNotFoundError(f"Файл отпечатка свёртки не найден: {item}.")
    return [(item, _lf(path.read_bytes()))]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


@lru_cache(maxsize=1)
def _live_fingerprint() -> str:
    return _fingerprint(package_root(), configs_root())
