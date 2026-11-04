"""Отпечаток файлов свёртки."""

from __future__ import annotations

from pathlib import Path

from finance_analysis.domain.book import derive_key_for
from finance_analysis.domain.derive_fingerprint import (
    CONFIG_SOURCES,
    PACKAGE_SOURCES,
    _live_fingerprint,
    derive_fingerprint,
)


def _shared() -> dict:
    return {
        "state_seq": 0,
        "glossary_version": "none",
        "taxonomy_version": "core-1",
        "calibrator_version": "none",
        "embed_model": "",
        "rerank_model": "",
        "clm_model": "",
        "profile_version": "p-0",
    }


def _checkout(root: Path, label: str) -> Path:
    if label.startswith("configs/"):
        return root / label
    return root / "src" / "finance_analysis" / label


def _seed(root: Path, *, newline: bytes) -> None:
    for item in (*PACKAGE_SOURCES, *CONFIG_SOURCES):
        path = _checkout(root, item)
        if item.endswith((".yaml", "model_types")):
            if item.endswith("model_types"):
                path = path / "corporate.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"id: core" + newline)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"def value():" + newline + b"    return 1" + newline)


def test_fingerprint_is_stable_across_runs():
    assert derive_fingerprint() == derive_fingerprint()
    assert derive_key_for(**_shared()) == derive_key_for(**_shared())


def test_line_endings_do_not_change_the_fingerprint(tmp_path: Path):
    _seed(tmp_path, newline=b"\r\n")
    crlf = derive_fingerprint(tmp_path)
    _seed(tmp_path, newline=b"\n")
    assert derive_fingerprint(tmp_path) == crlf
    lone = _checkout(tmp_path, "domain/mapping.py")
    lone.write_bytes(lone.read_bytes().replace(b"\n", b"\r"))
    assert derive_fingerprint(tmp_path) == crlf


def test_covered_file_changes_the_fingerprint(tmp_path: Path):
    _seed(tmp_path, newline=b"\n")
    left = derive_fingerprint(tmp_path)
    mapping = _checkout(tmp_path, "domain/mapping.py")
    mapping.write_bytes(mapping.read_bytes() + b"\nreturn 2\n")
    assert derive_fingerprint(tmp_path) != left


def test_unrelated_file_does_not_change_the_fingerprint(tmp_path: Path):
    _seed(tmp_path, newline=b"\n")
    left = derive_fingerprint(tmp_path)
    note = tmp_path / "README.md"
    note.write_text("Этот файл не входит в свёртку.\n", encoding="utf-8")
    other = tmp_path / "src" / "finance_analysis" / "domain" / "errors.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("class Error(Exception):\n    pass\n", encoding="utf-8")
    assert derive_fingerprint(tmp_path) == left


def test_installed_package_and_configs_live_in_different_parents(tmp_path: Path, monkeypatch) -> None:
    """Образ кладёт пакет в site-packages, а конфиги — в другой каталог.

    Вызов без аргумента читает обе стороны. Подписи путей совпадают с
    рабочей копией, поэтому хеш один.
    """

    checkout = tmp_path / "checkout"
    _seed(checkout, newline=b"\n")
    package = tmp_path / "site-packages" / "finance_analysis"
    opt = tmp_path / "opt"
    for item in PACKAGE_SOURCES:
        source = _checkout(checkout, item)
        target = package / item
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    for item in CONFIG_SOURCES:
        source = _checkout(checkout, item)
        if source.is_dir():
            for file in source.rglob("*"):
                if not file.is_file():
                    continue
                target = opt / file.relative_to(checkout)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(file.read_bytes())
            continue
        target = opt / item
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    monkeypatch.setattr("finance_analysis.domain.derive_fingerprint.package_root", lambda: package)
    monkeypatch.setattr("finance_analysis.domain.derive_fingerprint.configs_root", lambda: opt)
    _live_fingerprint.cache_clear()
    try:
        assert derive_fingerprint() == derive_fingerprint(checkout)
        touched = package / "domain" / "mapping.py"
        touched.write_bytes(touched.read_bytes() + b"\nreturn 2\n")
        _live_fingerprint.cache_clear()
        assert derive_fingerprint() != derive_fingerprint(checkout)
    finally:
        _live_fingerprint.cache_clear()
