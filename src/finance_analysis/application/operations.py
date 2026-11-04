"""События операции в object store (§4.14.4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from finance_analysis.application import keys
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import AlreadyExists, PreconditionFailed

_TERMINAL = {"succeeded", "failed", "cancelled"}


def dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def create_op(
    store, kind: str, job_id: str | None, actor: Actor, payload: dict, *, owner: str | None = None
) -> dict:
    from ulid import ULID

    op_id = str(ULID())
    now = _now()
    body = {
        "id": op_id,
        "kind": kind,
        "status": "running",
        "job_id": job_id,
        "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
        "created_at": now,
        "updated_at": now,
        "progress": 0,
        "payload": payload,
        "result": None,
        "error": None,
        "run_attempt": 0,
        "owner": owner,
    }
    await store.put_if_absent(keys.operation_key(op_id), dumps(body))
    return body


async def append_event(store, op_id: str, event: dict) -> dict:
    stamp = _now()
    for seq in range(1, 64):
        body = {"seq": seq, "at": stamp, **event}
        try:
            await store.put_if_absent(keys.operation_event_key(op_id, seq), dumps(body))
        except AlreadyExists:
            continue
        return body
    raise PreconditionFailed("слишком много событий операции")


async def read_events(store, op_id: str, after: int = 0) -> list[dict]:
    found = []
    start = after + 1 if after > 0 else 1
    for seq in range(start, 64):
        meta = await store.stat(keys.operation_event_key(op_id, seq))
        if meta is None:
            break
        found.append(json.loads(await store.get(keys.operation_event_key(op_id, seq))))
    return found


async def read_op(store, op_id: str) -> dict:
    body = json.loads(await store.get(keys.operation_key(op_id)))
    closed = False
    for seq in range(1, 64):
        meta = await store.stat(keys.operation_event_key(op_id, seq))
        if meta is None:
            break
        event = json.loads(await store.get(keys.operation_event_key(op_id, seq)))
        # requeue пишет running после failed и снова открывает операцию.
        # Поздний succeeded после cancelled статус не переписывает.
        if closed and event.get("status") in _TERMINAL:
            body["updated_at"] = event.get("at", body["updated_at"])
            continue
        if "status" in event:
            body["status"] = event["status"]
            closed = event["status"] in _TERMINAL
        if "result" in event:
            body["result"] = event["result"]
        if "error" in event:
            body["error"] = event["error"]
        if isinstance(event.get("payload"), dict):
            # Поздний курсор пересчёта дописывается в нагрузку, чтобы повтор
            # задачи увидел шаг и место, с которого продолжать.
            merged = dict(body.get("payload") or {})
            for key, value in event["payload"].items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value
            body["payload"] = merged
        if "run_attempt" in event:
            body["run_attempt"] = event["run_attempt"]
        body["updated_at"] = event.get("at", body["updated_at"])
    return body


def is_terminal(status: str) -> bool:
    return status in _TERMINAL
