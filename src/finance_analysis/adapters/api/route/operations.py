"""Операции и поток событий."""

from __future__ import annotations

import asyncio
import json

from fastapi import Request
from fastapi.responses import StreamingResponse

from finance_analysis.application.operations import read_events
from finance_analysis.domain.errors import NotFound
from finance_analysis.domain.ids import job_id as check_job

_TERMINAL = {"succeeded", "failed", "cancelled"}


def _resume_after(header: str | None) -> int:
    text = (header or "").strip()
    return int(text) if text.isdigit() else 0


def _sse(event: dict) -> str:
    status = event.get("status")
    if status in _TERMINAL:
        name = "done"
    elif event.get("type") == "progress" or event.get("stage"):
        name = "progress"
    else:
        name = "status"
    data = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
    return f"id: {event['seq']}\nevent: {name}\ndata: {data}\n\n"


def register(app, settings, *, actor, limited, svc, support) -> None:
    @app.get("/v1/operations/{op_id}")
    async def get_operation(op_id: str, request: Request, wait_ms: int = 0):
        who = actor(request)
        await limited(request, who)
        try:
            body = await svc().wait_op(op_id, wait_ms)
        finally:
            app.state.inflight -= 1
        return body

    @app.get("/v1/operations/{op_id}/events")
    async def operation_events(op_id: str, request: Request):
        if not settings.sse_enabled:
            raise NotFound("SSE выключен")
        who = actor(request)
        await limited(request, who)
        try:
            op = await svc().get_op(op_id)
        except Exception:
            app.state.inflight -= 1
            raise

        async def stream():
            last = _resume_after(request.headers.get("last-event-id"))
            for event in await read_events(svc().store, op_id, last):
                yield _sse(event)
                last = int(event["seq"])
                if event.get("status") in _TERMINAL:
                    return
            if op["status"] in _TERMINAL:
                return
            agen = support().messages(f"fas:op:{op_id}").__aiter__()
            pending: asyncio.Task | None = asyncio.create_task(agen.__anext__())
            probe = True
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    if svc().draining:
                        yield "retry: 1000\n\n"
                        return
                    woke = True
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(pending),
                            timeout=0.05 if probe else settings.sse_heartbeat_sec,
                        )
                    except TimeoutError:
                        woke = False
                    except StopAsyncIteration:
                        woke = False
                        pending = None
                    else:
                        pending = asyncio.create_task(agen.__anext__())
                    for event in await read_events(svc().store, op_id, last):
                        yield _sse(event)
                        last = int(event["seq"])
                        if event.get("status") in _TERMINAL:
                            return
                    if pending is None:
                        return
                    if not woke and not probe:
                        yield ": ping\n\n"
                    probe = False
            finally:
                if pending is not None and not pending.done():
                    pending.cancel()
                    try:
                        await pending
                    except (asyncio.CancelledError, StopAsyncIteration, Exception):  # noqa: BLE001, S110
                        pass
                try:
                    await agen.aclose()
                except RuntimeError:
                    pass

        try:
            return StreamingResponse(stream(), media_type="text/event-stream")
        finally:
            app.state.inflight -= 1

    @app.get("/v1/operations")
    async def list_operations(
        request: Request,
        kind: str | None = None,
        job_id: str | None = None,
        status: str | None = None,
    ):
        who = actor(request)
        await limited(request, who)
        try:
            if job_id:
                check_job(job_id)
            rows = await svc().list_ops(kind=kind, job_id=job_id, status=status)
        finally:
            app.state.inflight -= 1
        return {"operations": rows}

    @app.post("/v1/operations/{op_id}:cancel")
    async def cancel(op_id: str, request: Request):
        who = actor(request)
        runtime = await limited(request, who)
        try:
            await request.body()
            async with runtime.user_inflight(who):
                return await svc().cancel_op(op_id, who)
        finally:
            app.state.inflight -= 1
