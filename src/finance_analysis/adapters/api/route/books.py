"""Книга, сборки и расчёты по уже загруженным числам."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from finance_analysis.adapters.api.http import (
    idem_abort,
    idem_begin,
    idem_finish,
    idem_key,
    idem_response,
    op_headers,
    prefer_async,
)
from finance_analysis.application.service import Accepted, Freshness
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.ids import build_key as check_build
from finance_analysis.domain.ids import job_id as check_job


def register(app, settings, *, actor, limited, svc, support, calc) -> None:
    @app.post("/v1/books/{job_id}:load")
    async def load_book(job_id: str, request: Request):
        checked = check_job(job_id)
        who = actor(request)
        runtime = await limited(request, who)
        method, route = "POST", "/v1/books/{job_id}:load"
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await idem_begin(runtime, who, method, route, request, raw)
            if cached is not None:
                return idem_response(cached)
            pending = idem_key(request) is not None
            async with runtime.user_inflight(who):
                result = await svc().ensure(
                    checked,
                    who,
                    wait_sec=settings.load_sync_sec,
                    prefer_async=prefer_async(request),
                )
            if isinstance(result, Accepted):
                response = JSONResponse(result.operation, status_code=202, headers=op_headers(result))
                await idem_finish(runtime, who, method, route, request, raw, result.operation, 202)
                pending = False
                return response
            if isinstance(result, Freshness):
                view = await svc().describe(checked, result.head, fresh=True)
            else:
                view = await svc().describe(checked, result, fresh=False)
            if isinstance(view, Accepted):
                response = JSONResponse(view.operation, status_code=202, headers=op_headers(view))
                await idem_finish(runtime, who, method, route, request, raw, view.operation, 202)
                pending = False
                return response
            await idem_finish(runtime, who, method, route, request, raw, view.body, 200)
            pending = False
            return view.body
        except BaseException:
            if pending:
                await idem_abort(runtime, who, method, route, request, raw)
            raise
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/builds")
    async def list_builds(job_id: str, request: Request, page_size: int = 50, page_token: str | None = None):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            if page_size < 1 or page_size > 1000:
                raise InvalidArgument("page_size должен быть от 1 до 1000")
            async with support().user_inflight(who):
                return await svc().list_builds(checked, page_size=page_size, page_token=page_token)
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/builds/{build_key}")
    async def get_build(job_id: str, build_key: str, request: Request):
        checked = check_job(job_id)
        build = check_build(build_key)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                return await svc().get_build(checked, build)
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}")
    async def get_book(job_id: str, request: Request, min_state_seq: int | None = None):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                view = await svc().book_view(
                    checked, who, wait_sec=settings.load_sync_sec, min_state_seq=min_state_seq,
                )
        finally:
            app.state.inflight -= 1
        if isinstance(view, Accepted):
            return JSONResponse(view.operation, status_code=202, headers=op_headers(view))
        return view.body

    @app.post("/v1/books/{job_id}/series")
    async def series(job_id: str, request: Request):
        return await calc(job_id, request, svc().series)

    @app.post("/v1/books/{job_id}/slice")
    async def slice_route(job_id: str, request: Request):
        return await calc(job_id, request, svc().slice)

    @app.post("/v1/books/{job_id}/expression")
    async def expression(job_id: str, request: Request):
        return await calc(job_id, request, svc().expression)

    @app.post("/v1/books/{job_id}/periods:resolve")
    async def periods(job_id: str, request: Request):
        return await calc(job_id, request, svc().resolve_periods)

    @app.post("/v1/books/{job_id}/decisions")
    async def decisions(job_id: str, request: Request):
        header = request.headers.get("if-match")

        async def method(checked, body, who, *, wait_sec: float):
            return await svc().submit_decisions(checked, body, who, wait_sec=wait_sec, if_match=header)

        return await calc(job_id, request, method)
