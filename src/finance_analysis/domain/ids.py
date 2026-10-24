"""Белые списки идентификаторов (§4.1)."""

from __future__ import annotations

import re

from finance_analysis.domain.errors import InvalidId

JOB_RE = re.compile(r"^[0-9a-f]{64}$")
HEX16_RE = re.compile(r"^[0-9a-f]{16}$")
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ACTOR_RE = re.compile(r"^[A-Za-z0-9._@:-]{1,128}$")
DATASET_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{40}$")


def _check(raw: str, pattern: re.Pattern[str], kind: str) -> str:
    if not isinstance(raw, str) or not pattern.fullmatch(raw):
        raise InvalidId(f"{kind} вне белого списка", extra={"value": str(raw)[:80]})
    return raw


def job_id(raw: str) -> str:
    return _check(raw, JOB_RE, "job_id")


def build_key(raw: str) -> str:
    return _check(raw, HEX16_RE, "build_key")


def derive_key(raw: str) -> str:
    return _check(raw, HEX16_RE, "derive_key")


def ulid(raw: str) -> str:
    return _check(raw, ULID_RE, "ulid")


def profile_id(raw: str) -> str:
    return _check(raw, NAME_RE, "profile_id")


def concept_id(raw: str) -> str:
    return _check(raw, NAME_RE, "concept_id")


def model_id(raw: str) -> str:
    return _check(raw, MODEL_RE, "model_id")


def fingerprint(raw: str) -> str:
    return _check(raw, FINGERPRINT_RE, "fingerprint")


def dataset_name(raw: str) -> str:
    return _check(raw, DATASET_RE, "dataset")


def actor_token(raw: str, *, header: str) -> str:
    if not isinstance(raw, str) or not ACTOR_RE.fullmatch(raw):
        raise InvalidId(f"{header} должен быть [A-Za-z0-9._@:-] длиной 1..128")
    return raw
