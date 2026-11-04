"""Регистрация маршрутов. Общий обвес живёт здесь, пути — в соседних модулях."""

from __future__ import annotations

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse

from finance_analysis.adapters.api.http import (
    idem_abort,
    idem_begin,
    idem_finish,
    idem_key,
    idem_response,
    op_headers,
    route_template,
)
from finance_analysis.adapters.api.http import (
    prefer_async as header_async,
)
from finance_analysis.adapters.api.route import (
    analyses,
    book_views,
    books,
    glossary,
    operations,
    profiles,
)
from finance_analysis.application.service import Accepted
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.ids import job_id as check_job


def register(app, settings, *, actor, limited, svc, support) -> None:
    async def write(request: Request, run):
        who = actor(request)
        runtime = await limited(request, who)
        method = request.method
        route = route_template(request)
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await idem_begin(runtime, who, method, route, request, raw)
            if cached is not None:
                return idem_response(cached)
            pending = bool(request.headers.get("idempotency-key"))
            try:
                body = await request.json() if raw else {}
            except Exception as exc:
                raise InvalidArgument("тело не JSON") from exc
            if not isinstance(body, dict):
                raise InvalidArgument("тело должно быть объектом")
            result = await run(svc().glossary, body, request.headers.get("if-match"))
            if isinstance(result, Accepted):
                await idem_finish(runtime, who, method, route, request, raw, result.operation, 202)
                pending = False
                return JSONResponse(result.operation, status_code=202, headers=op_headers(result))
            etag = result.get("etag") if isinstance(result, dict) else None
            encoded = result if isinstance(result, dict) else {"ok": True}
            await idem_finish(runtime, who, method, route, request, raw, encoded, 200)
            pending = False
            if etag and isinstance(result, dict):
                return JSONResponse(result, headers={"ETag": etag})
            return result
        except BaseException:
            if pending:
                await idem_abort(runtime, who, method, route, request, raw)
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
                return JSONResponse(result.operation, status_code=202, headers=op_headers(result))
            return result
        finally:
            app.state.inflight -= 1

    async def calc(job_id: str, request: Request, method, *, prefer_async: bool = False):
        checked = check_job(job_id)
        who = actor(request)
        runtime = await limited(request, who)
        route = route_template(request)
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await idem_begin(runtime, who, "POST", route, request, raw)
            if cached is not None:
                return idem_response(cached)
            pending = idem_key(request) is not None
            try:
                body = await request.json() if raw else {}
            except Exception as exc:
                raise InvalidArgument("тело не JSON") from exc
            if not isinstance(body, dict):
                raise InvalidArgument("тело должно быть объектом")
            if prefer_async and header_async(request):
                body = {**body, "async": True}
            digest = hashlib.sha256(raw or b"{}").hexdigest()
            flight = f"{checked}:{route}:{digest}:{body.get('async') is True}"

            async def _run():
                async with runtime.user_inflight(who):
                    return await method(checked, body, who, wait_sec=settings.sync_deadline_ms / 1000)

            result = await runtime.singleflight(flight, _run)
            if isinstance(result, Accepted):
                await idem_finish(runtime, who, "POST", route, request, raw, result.operation, 202)
                pending = False
                return JSONResponse(result.operation, status_code=202, headers=op_headers(result))
            await idem_finish(runtime, who, "POST", route, request, raw, result, 200)
            pending = False
            return result
        except BaseException:
            if pending:
                await idem_abort(runtime, who, "POST", route, request, raw)
            raise
        finally:
            app.state.inflight -= 1

    async def findings_read(job_id: str, request: Request, load):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                result = await load(checked, who, dict(request.query_params))
        finally:
            app.state.inflight -= 1
        if isinstance(result, Accepted):
            return JSONResponse(result.operation, status_code=202, headers=op_headers(result))
        return result

    books.register(app, settings, actor=actor, limited=limited, svc=svc, support=support, calc=calc)
    analyses.register(
        app,
        settings,
        actor=actor,
        limited=limited,
        svc=svc,
        support=support,
        calc=calc,
        findings_read=findings_read,
    )
    operations.register(app, settings, actor=actor, limited=limited, svc=svc, support=support)
    glossary.register(app, settings, svc=svc, write=write, read=read)
    profiles.register(app, svc=svc, write=write, read=read)
    book_views.register(app, settings, svc=svc, book_get=book_get, read=read, op_headers=op_headers)
