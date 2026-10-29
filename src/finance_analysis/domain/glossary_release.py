"""Релиз глоссария: канонический документ, ops и diff (§5.9)."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime

from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.glossary import GlossaryInvalid, build_package


def version_for(seq: int, document: dict) -> str:
    digest = hashlib.sha256(canonical_json(document).encode()).hexdigest()[:12]
    return f"g-{seq:04d}:{digest}"


def package_of(document: dict):
    try:
        return build_package(
            {"taxonomy": document["taxonomy"], "concepts": document["concepts"]},
            document["glossaries"],
            document["dictionaries"],
        )
    except GlossaryInvalid as exc:
        raise InvalidArgument("пакет глоссария не сходится", extra={"labels": exc.labels}) from exc


def apply_ops(document: dict, ops: list[dict]) -> dict:
    updated = copy.deepcopy(document)
    for op in ops:
        if not isinstance(op, dict):
            raise InvalidArgument("op должен быть объектом")
        kind = op.get("op")
        concept = op.get("concept")
        glossary = updated["glossaries"].get(concept)
        if not isinstance(glossary, dict):
            raise InvalidArgument(f"нет понятия {concept}")
        if kind == "set_pref":
            lang, text = _lang_text(op)
            glossary.setdefault("pref", {})[lang] = text
        elif kind == "add_label":
            lang, text = _lang_text(op)
            bucket = _label_bucket(glossary, op.get("kind"), op.get("scope"))
            values = bucket.setdefault(lang, [])
            if isinstance(values, str):
                raise InvalidArgument("pref меняется через set_pref")
            if text not in values:
                values.append(text)
        elif kind == "remove_label":
            lang, text = _lang_text(op)
            bucket = _label_bucket(glossary, op.get("kind"), op.get("scope"))
            values = bucket.get(lang)
            if isinstance(values, list) and text in values:
                values.remove(text)
            elif values == text:
                bucket.pop(lang, None)
            else:
                raise InvalidArgument(f"метки нет: {text}")
        elif kind == "add_negative":
            text = op.get("text")
            if not isinstance(text, str) or not text:
                raise InvalidArgument("у отрицательной метки нужен text")
            values = glossary.get("negative") or []
            if isinstance(values, str):
                values = [values]
            if text not in values:
                values.append(text)
            glossary["negative"] = values
        else:
            raise InvalidArgument(f"неизвестный op {kind}")
    package_of(updated)
    return updated


def label_diff(before: dict, after: dict) -> list[dict]:
    old = _flat(before)
    new = _flat(after)
    changes = []
    for key in sorted(old - new):
        changes.append(_change(key, "remove"))
    for key in sorted(new - old):
        changes.append(_change(key, "add"))
    return changes


def _change(key: tuple, change: str) -> dict:
    concept, kind, lang, text, scope = key
    row = {"concept": concept, "kind": kind, "lang": lang, "text": text, "change": change}
    if scope:
        row["scope"] = scope
    return row


def _flat(document: dict) -> set[tuple[str, str, str, str, str]]:
    found: set[tuple[str, str, str, str, str]] = set()

    def add(concept, kind, lang, text, scope: str = "") -> None:
        found.add((str(concept), kind, str(lang), str(text), scope))

    for concept, glossary in (document.get("glossaries") or {}).items():
        if not isinstance(glossary, dict):
            continue
        for kind in ("pref", "alt", "hidden"):
            bucket = glossary.get(kind) or {}
            if not isinstance(bucket, dict):
                continue
            for lang, value in bucket.items():
                texts = [value] if isinstance(value, str) else list(value or [])
                for text in texts:
                    add(concept, kind, lang, text)
        for profile, block in (glossary.get("scoped") or {}).items():
            if not isinstance(block, dict):
                continue
            for kind in ("alt", "hidden"):
                bucket = block.get(kind) or {}
                if not isinstance(bucket, dict):
                    continue
                for lang, value in bucket.items():
                    texts = [value] if isinstance(value, str) else list(value or [])
                    for text in texts:
                        add(concept, kind, lang, text, f"profile:{profile}")
    return found


def _label_bucket(glossary: dict, kind: str, scope) -> dict:
    if not scope:
        return _bucket(glossary, kind)
    if kind not in {"alt", "hidden"}:
        raise InvalidArgument("метка профиля: alt или hidden")
    if not isinstance(scope, str) or not scope.startswith("profile:") or scope == "profile:":
        raise InvalidArgument("scope: profile:{id}")
    profile = scope.split(":", 1)[1]
    block = glossary.setdefault("scoped", {}).setdefault(profile, {})
    if not isinstance(block, dict):
        raise InvalidArgument("блок меток профиля повреждён")
    bucket = block.setdefault(kind, {})
    if not isinstance(bucket, dict):
        raise InvalidArgument("блок меток повреждён")
    return bucket


def glossary_for_job(head: dict, job_id: str) -> str:
    """Доля `hash(job_id) % 100 < canary_share` читает canary. `hash()` процесса не подходит: он разный между запусками."""

    canary = head.get("canary")
    share = int(head.get("canary_share") or 0)
    if canary and 0 < share <= 100:
        bucket = int(hashlib.sha256(job_id.encode()).hexdigest(), 16) % 100
        if bucket < share:
            return canary
    return head["active"]


def canary_verdict(
    since: datetime,
    books: int,
    rows: int,
    now: datetime,
    *,
    hours: int,
    min_books: int,
    min_rows: int,
    max_hours: int,
) -> str:
    """promote — время и объём набраны раньше max_hours. Дальше wait: решает человек."""

    elapsed = (now - since).total_seconds() / 3600
    if elapsed >= max_hours:
        return "wait"
    if books >= min_books and rows >= min_rows and elapsed >= hours:
        return "promote"
    return "wait"


def summarize_stats(
    *,
    coverage: list[dict],
    proposals: list[dict],
    auto_labels: int,
    auto_rejected: int,
    shadow: dict | None,
    lf_accuracy: dict,
) -> dict:
    """Покрытие, авто-метки и очередь ревью для `GET /v1/glossary/stats`."""

    by_month: dict[str, dict[str, int]] = {}
    by_profile: dict[str, dict[str, int]] = {}
    for row in coverage:
        month = str(row.get("month") or "")
        profile = str(row.get("profile") or "")
        status = str(row.get("status") or "unknown")
        count = int(row.get("rows") or 0)
        for bucket, key in ((by_month, month), (by_profile, profile)):
            if not key:
                continue
            cell = bucket.setdefault(key, {})
            cell[status] = cell.get(status, 0) + count
    durations = []
    for item in proposals:
        start, end = item.get("created_at_utc"), item.get("decided_at_utc")
        if isinstance(start, str) and isinstance(end, str) and end >= start:
            durations.append(_seconds(start, end))
    durations.sort()
    delta = (((shadow or {}).get("eval") or {}).get("delta") or {}).get("all") or {}
    books = (shadow or {}).get("books") or []
    return {
        "unknown_by_month": {key: _share(cell, "unknown") for key, cell in sorted(by_month.items())},
        "ambiguous_by_month": {key: _share(cell, "ambiguous") for key, cell in sorted(by_month.items())},
        "by_profile": {
            key: {"unknown": _share(cell, "unknown"), "ambiguous": _share(cell, "ambiguous")}
            for key, cell in sorted(by_profile.items())
        },
        "auto": {
            "labels": auto_labels,
            "rejected_30d": auto_rejected,
            "rollback_rate": None if not auto_labels else round(auto_rejected / auto_labels, 6),
        },
        "review": {
            "open": sum(1 for item in proposals if item.get("status") == "open"),
            "median_sec": _percentile(durations, 0.5),
            "p90_sec": _percentile(durations, 0.9),
        },
        "shadow": None
        if not shadow
        else {
            "passed": shadow.get("passed"),
            "false_binding_delta": delta.get("delta"),
            "coverage_delta": sum(int(item.get("delta_bound") or 0) for item in books),
        },
        "lf_accuracy": lf_accuracy,
    }


def _share(cell: dict[str, int], status: str) -> float | None:
    total = sum(cell.values())
    if not total:
        return None
    return round(cell.get(status, 0) / total, 6)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * p)))
    return values[index]


def _seconds(start: str, end: str) -> float:
    left = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S")
    right = datetime.strptime(end[:19], "%Y-%m-%dT%H:%M:%S")
    return (right - left).total_seconds()


def _bucket(glossary: dict, kind: str) -> dict:
    if kind not in {"pref", "alt", "hidden"}:
        raise InvalidArgument("kind метки должен быть pref, alt или hidden")
    bucket = glossary.setdefault(kind, {})
    if not isinstance(bucket, dict):
        raise InvalidArgument("блок меток повреждён")
    return bucket


def _lang_text(op: dict) -> tuple[str, str]:
    lang, text = op.get("lang"), op.get("text")
    if not isinstance(lang, str) or not isinstance(text, str) or not text:
        raise InvalidArgument("у метки нужны lang и text")
    return lang, text
