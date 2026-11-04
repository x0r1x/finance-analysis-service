"""Входы derive_key."""

from finance_analysis.domain.book import derive_key_for
from finance_analysis.domain.derive_fingerprint import derive_fingerprint


def test_sheet_roles_version_changes_derive_key():
    shared = {
        "state_seq": 0,
        "glossary_version": "none",
        "taxonomy_version": "core-1",
        "calibrator_version": "none",
        "embed_model": "",
        "rerank_model": "",
        "clm_model": "",
        "profile_version": "p-0",
        "model_types_version": "abc",
        "model_type_seq": 0,
    }
    left = derive_key_for(**shared, sheet_roles_version="aaa")
    assert derive_key_for(**shared, sheet_roles_version="aaa") == left
    assert derive_key_for(**shared, sheet_roles_version="bbb") != left
    assert derive_key_for(**shared, sheet_roles_version="aaa", fas_derive_version="1") != left
    assert derive_key_for(**shared) == derive_key_for(**shared, fas_derive_version=derive_fingerprint())
