"""Пояснение по code + params. Числа подставляет код, не модель (§6.6)."""

from __future__ import annotations

import json
import re

_DIGIT = re.compile(r"\d")
_PLACE = re.compile(r"\{([^{}]*)\}")


def scalars(params: dict | None) -> dict[str, str]:
    found = {}
    for key, value in (params or {}).items():
        if isinstance(value, bool | dict | list):
            continue
        if value is None or isinstance(value, str | int | float):
            found[str(key)] = "" if value is None else str(value)
    return found


def template_text(code: str, params: dict | None, title: str | None = None) -> str:
    shown = scalars(params)
    head = title or code
    if not shown:
        return head
    body = ", ".join(f"{key}={shown[key]}" for key in sorted(shown))
    return f"{head}: {body}"


def _fill(phrase: str, params: dict | None) -> str | None:
    """Фраза модели годится, только если в ней нет цифр: числа приходят из params."""

    if not isinstance(phrase, str) or not phrase.strip() or _DIGIT.search(phrase):
        return None
    names = scalars(params)
    if any(field not in names for field in _PLACE.findall(phrase)):
        return None
    try:
        return phrase.format_map(names).strip()
    except (KeyError, IndexError, ValueError, AttributeError):
        return None


def _object(text: str) -> dict:
    raw = text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def narrate(llm, items: list[dict], deadline) -> dict[str, str]:
    """`items`: `{id, code, params, title?}`. Нет модели или цифры в ответе — шаблон.

    Один вызов на пачку. Имена params уходят в промпт, значения — только в format.
    """

    fallback = {item["id"]: template_text(item["code"], item.get("params"), item.get("title")) for item in items}
    if llm is None or not items:
        return fallback
    brief = [
        {"id": item["id"], "code": item["code"], "params": sorted(scalars(item.get("params")))}
        for item in items
    ]
    prompt = (
        "Напиши по одной короткой фразе на id. Верни JSON-объект {id: фраза}. "
        "В фразе нет цифр. Числа обозначай плейсхолдерами {имя} из списка params. "
        f"Вход: {json.dumps(brief, ensure_ascii=False)}"
    )
    try:
        text = await llm.complete(
            [{"role": "user", "content": prompt}],
            deadline=deadline,
            max_tokens=800,
        )
    except Exception:  # noqa: BLE001 — пояснение не валит расчёт
        return fallback
    parsed = _object(text)
    out = dict(fallback)
    by_id = {item["id"]: item for item in items}
    for key, phrase in parsed.items():
        item = by_id.get(str(key))
        if item is None:
            continue
        filled = _fill(phrase, item.get("params"))
        if filled:
            out[item["id"]] = filled
    return out
