"""Возврат задач из fas:dlq (§4.13.5)."""

from __future__ import annotations

import json

from finance_analysis.adapters.queue.names import DLQ
from finance_analysis.application.operations import append_event, read_op
from finance_analysis.domain.errors import InvalidId, NotFound


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return "" if value is None else str(value)


def _fields(raw: dict) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


async def requeue_dlq(redis, store, kick, *, entry_id: str | None = None) -> dict:
    """Ставит запись DLQ обратно в её очередь и снимает её со stream.

    Счётчик попыток обнуляется: иначе задача, уже помеченная poison,
    сразу вернётся в DLQ, не начав работу.
    """

    start = entry_id or "-"
    stop = entry_id or "+"
    rows = await redis.xrange(DLQ, min=start, max=stop)
    requeued = []
    for raw_id, raw_fields in rows:
        message_id = _text(raw_id)
        fields = _fields(raw_fields)
        payload = json.loads(fields.get("payload") or "{}")
        if not isinstance(payload, dict):
            raise TypeError(f"payload {message_id} не объект")
        op_id = fields.get("op_id") or payload.get("op_id") or ""
        if op_id:
            await redis.delete(f"fas:op:{op_id}:attempt", f"fas:op:{op_id}:hb")
            try:
                await read_op(store, op_id)
            except (NotFound, InvalidId):
                pass
            else:
                await append_event(store, op_id, {"status": "running", "type": "requeue"})
        await kick(payload)
        await redis.xdel(DLQ, message_id)
        requeued.append({"id": message_id, "op_id": op_id, "queue": payload.get("queue")})
    return {"requeued": len(requeued), "entries": requeued}
