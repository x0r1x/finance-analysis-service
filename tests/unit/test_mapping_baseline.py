"""База mapping: ключ следует из записанных входов, сдвиг — из членов отпечатка."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finance_analysis.application.catalog import load_git_document
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.sheet_roles import sheet_roles_version
from finance_analysis.domain.book import derive_key_for
from finance_analysis.domain.derive_fingerprint import (
    _files,
    configs_root,
    derive_fingerprint,
    package_root,
)
from finance_analysis.domain.glossary_release import version_for

MANIFEST = Path(__file__).resolve().parents[2] / "eval" / "mapping" / "baseline.json"


def _manifest() -> dict:
    assert MANIFEST.is_file()
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _members() -> dict[str, str]:
    pairs = _files(package_root(), configs_root())
    return {path: hashlib.sha256(body).hexdigest() for path, body in pairs}


def _changed(parent: dict[str, str], current: dict[str, str]) -> list[str]:
    paths = sorted(set(parent) | set(current))
    return [path for path in paths if parent.get(path) != current.get(path)]


def test_derive_key_matches_the_recorded_inputs():
    manifest = _manifest()
    inputs = dict(manifest["derive_inputs"])
    assert derive_fingerprint() == manifest["fas_derive_version"]
    assert derive_key_for(**inputs) == manifest["derive_key"]
    parent = manifest["parent"]
    pinned = derive_key_for(**inputs, fas_derive_version=parent["fas_derive_version"])
    assert pinned == parent["derive_key"]
    assert load_financial_catalog().version == manifest["catalog_version"]
    assert version_for(1, load_git_document()) == manifest["glossary"]
    assert load_model_types().version == inputs["model_types_version"]
    assert sheet_roles_version() == inputs["sheet_roles_version"]


def test_fingerprint_delta_is_the_changed_members():
    manifest = _manifest()
    changed = _changed(manifest["parent"]["members"], _members())
    assert changed == manifest["changed_members"]
