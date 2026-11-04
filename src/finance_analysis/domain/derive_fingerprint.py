"""Отпечаток файлов, от которых зависит производное состояние.

Список путей объявлен в `DERIVE_SOURCES`. Хеш подставляется в `derive_key`
вместо ручного счётчика. Правка любого из этих файлов меняет ключ сама.
Переводы строк приводятся к LF, поэтому одни и те же байты текста дают
один хеш. Версия глоссария в список не входит: её задаёт релиз, а не эти
файлы. `sheet_roles_version` остаётся отдельным входом ключа: это хеш уже
разобранных ролей листа.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

# Выбор строки и роли листа живут в mapping.py. Отдельного модуля способа
# показа периода ещё нет: когда он появится, его путь добавляется сюда.
DERIVE_SOURCES = (
    "src/finance_analysis/domain/derive_fingerprint.py",
    "src/finance_analysis/domain/mapping.py",
    "src/finance_analysis/domain/components.py",
    "src/finance_analysis/domain/references.py",
    "src/finance_analysis/domain/semantics.py",
    "src/finance_analysis/domain/glossary.py",
    "src/finance_analysis/domain/candidates.py",
    "src/finance_analysis/domain/calibration.py",
    "src/finance_analysis/domain/model_type.py",
    "src/finance_analysis/domain/periods.py",
    "src/finance_analysis/domain/phases.py",
    "src/finance_analysis/domain/currency.py",
    "src/finance_analysis/domain/state.py",
    "src/finance_analysis/application/project.py",
    "src/finance_analysis/application/sheet_roles.py",
    "src/finance_analysis/application/catalog.py",
    "configs/sheet_roles.yaml",
    "configs/concepts/core.yaml",
    "configs/model_types",
)


def derive_fingerprint(root: Path | None = None) -> str:
    """Возвращает sha256 объявленных файлов.

    `root` — корень репозитория. Если он не передан, берётся корень этой
    установки. Каталог читается целиком, файлы идут по относительному пути.
    Перевод строки CRLF и одиночный CR считаются как LF.
    """

    if root is None:
        return _repo_fingerprint()
    return _fingerprint(root)


def repo_root() -> Path:
    """Возвращает каталог, в котором лежат `configs/concepts/core.yaml`."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "configs" / "concepts" / "core.yaml").is_file():
            return parent
    raise FileNotFoundError("Корень репозитория не найден: нет configs/concepts/core.yaml.")


def _fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path, body in _files(root):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def _files(root: Path) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for item in DERIVE_SOURCES:
        path = root / item
        if path.is_dir():
            files = sorted(
                file for file in path.rglob("*") if file.is_file() and "__pycache__" not in file.parts
            )
            if not files:
                raise FileNotFoundError(f"Каталог отпечатка свёртки пуст: {item}.")
            for file in files:
                found.append((file.relative_to(root).as_posix(), _lf(file.read_bytes())))
            continue
        if not path.is_file():
            raise FileNotFoundError(f"Файл отпечатка свёртки не найден: {item}.")
        found.append((item, _lf(path.read_bytes())))
    found.sort()
    return found


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


@lru_cache(maxsize=1)
def _repo_fingerprint() -> str:
    return _fingerprint(repo_root())
