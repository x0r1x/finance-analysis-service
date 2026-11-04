"""Отпечаток файлов свёртки."""

from __future__ import annotations

from pathlib import Path

from finance_analysis.domain.book import derive_key_for
from finance_analysis.domain.derive_fingerprint import (
    DERIVE_SOURCES,
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


def _seed(root: Path, *, newline: bytes) -> None:
    for item in DERIVE_SOURCES:
        path = root / item
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
    lone = tmp_path / "src/finance_analysis/domain/mapping.py"
    lone.write_bytes(lone.read_bytes().replace(b"\n", b"\r"))
    assert derive_fingerprint(tmp_path) == crlf


def test_covered_file_changes_the_fingerprint(tmp_path: Path):
    _seed(tmp_path, newline=b"\n")
    left = derive_fingerprint(tmp_path)
    mapping = tmp_path / "src/finance_analysis/domain/mapping.py"
    mapping.write_bytes(mapping.read_bytes() + b"\nreturn 2\n")
    assert derive_fingerprint(tmp_path) != left


def test_unrelated_file_does_not_change_the_fingerprint(tmp_path: Path):
    _seed(tmp_path, newline=b"\n")
    left = derive_fingerprint(tmp_path)
    note = tmp_path / "README.md"
    note.write_text("Этот файл не входит в свёртку.\n", encoding="utf-8")
    other = tmp_path / "src/finance_analysis/domain/errors.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("class Error(Exception):\n    pass\n", encoding="utf-8")
    assert derive_fingerprint(tmp_path) == left
