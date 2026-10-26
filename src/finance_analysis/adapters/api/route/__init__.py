"""Регистрация маршрутов глоссария, профилей и представлений книги."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from finance_analysis.application.service import Accepted
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.ids import job_id as check_job


def register(app, settings, *, actor, limited, svc, support) -> None:
    # app импортирует этот пакет из create_app, поэтому хелперы берём здесь.
    from finance_analysis.adapters.api.app import (
        _idem_abort,
        _idem_begin,
        _idem_finish,
        _idem_response,
        _op_headers,
        _route_template,
    )
    from finance_analysis.adapters.api.route import book_views, glossary, profiles

    async def write(request: Request, run):
        who = actor(request)
        runtime = await limited(request, who)
        method = request.method
        route = _route_template(request)
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await _idem_begin(runtime, who, method, route, request, raw)
            if cached is not None:
                return _idem_response(cached)
            pending = bool(request.headers.get("idempotency-key"))
            try:
                body = await request.json() if raw else {}
            except Exception as exc:
                raise InvalidArgument("тело не JSON") from exc
            if not isinstance(body, dict):
                raise InvalidArgument("тело должно быть объектом")
            result = await run(svc().glossary, body, request.headers.get("if-match"))
            etag = result.get("etag") if isinstance(result, dict) else None
            encoded = result if isinstance(result, dict) else {"ok": True}
            await _idem_finish(runtime, who, method, route, request, raw, encoded, 200)
            pending = False
            if etag and isinstance(result, dict):
                return JSONResponse(result, headers={"ETag": etag})
            return result
        except BaseException:
            if pending:
                await _idem_abort(runtime, who, method, route, request, raw)
            raise
        finally:
            app.state.inflight -= 1

    async def read(request: Request, load):
        who = actor(request)
        await limited(request, who)
        try:
            return await load(who)
        finally:
            app.state.inflight -= 1

    async def book_get(job_id: str, request: Request, method):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                result = await method(checked, who)
            if isinstance(result, Accepted):
                return JSONResponse(result.operation, status_code=202, headers=_op_headers(result))
            return result
        finally:
            app.state.inflight -= 1

    glossary.register(app, settings, svc=svc, write=write, read=read)
    profiles.register(app, svc=svc, write=write, read=read)
    book_views.register(
        app,
        settings,
        svc=svc,
        book_get=book_get,
        read=read,
        op_headers=_op_headers,
    )
