"""Свёртка журнала: побеждает запись с большим seq (§4.5)."""

from __future__ import annotations


def fold(events: list[dict]) -> dict[str, dict]:
    ordered = sorted(events, key=lambda item: int(item["seq"]))
    state: dict[str, dict] = {}
    seen: set[int] = set()
    for event in ordered:
        seq = int(event["seq"])
        if seq in seen:
            raise ValueError(f"дубль seq {seq}")
        seen.add(seq)
        target = event.get("target") or event.get("binding_key")
        if not target:
            continue
        # Последняя запись каждого вида на одной цели. Иначе concept.set стирает sign.set.
        state[f"{event.get('type') or ''}\x1f{target}"] = event
    if seen:
        expected = set(range(1, max(seen) + 1))
        if seen != expected:
            missing = sorted(expected - seen)[:5]
            raise ValueError(f"в журнале есть пропуски: {missing}")
    return state
