"""Маршруты фазы 0."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from finance_analysis.adapters.api.problems import problem_response
from finance_analysis.application.service import Accepted, Freshness
from finance_analysis.domain.book import FAS_VERSION, Actor
from finance_analysis.domain.errors import (
    DeadlineExceeded,
    DependencyUnavailable,
    FasError,
    InvalidArgument,
    InvalidId,
    NotAcceptable,
)
from finance_analysis.domain.ids import actor_token
from finance_analysis.domain.ids import build_key as check_build
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.settings import Settings

REQUESTS = Counter("fas_http_requests_total", "HTTP-запросы", ["method", "path", "status"])
LATENCY = Histogram("fas_http_request_seconds", "Длительность HTTP", ["path"])
LOOP_LAG = Gauge("fas_event_loop_lag_seconds", "Задержка event loop")

_SYNC_SKIP = ("/health/", "/metrics", "/v1/operations", "/v1/capabilities")


def _actor(request: Request) -> Actor:
    user = request.headers.get("x-user-id")
    client = request.headers.get("x-client-id")
    if user:
        user = actor_token(user, header="X-User-Id")
    if client:
        client = actor_token(client, header="X-Client-Id")
    return Actor(user_id=user or "anonymous", client_id=client or "anonymous")


def _prefer_async(request: Request) -> bool:
    prefer = (request.headers.get("prefer") or "").lower()
    return "respond-async" in prefer


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


def create_app(settings: Settings, *, service=None, support=None) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.service = service
        app.state.support = support
        app.state.inflight = 0
        stop = asyncio.Event()

        async def _lag() -> None:
            loop = asyncio.get_running_loop()
            while not stop.is_set():
                started = loop.time()
                await asyncio.sleep(0)
                LOOP_LAG.set(max(0.0, loop.time() - started))
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.5)
                except TimeoutError:
                    pass

        task = asyncio.create_task(_lag())
        yield
        stop.set()
        task.cancel()

    app = FastAPI(title="finance-analysis-service", version=FAS_VERSION, lifespan=_lifespan)
    app.state.settings = settings
    app.state.service = service
    app.state.support = support
    app.state.inflight = 0

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        path = request.url.path
        started = time.perf_counter()
        accept = request.headers.get("accept") or "*/*"
        if path != "/metrics" and "application/json" not in accept and "*/*" not in accept and "application/problem+json" not in accept:
            return problem_response(
                NotAcceptable("допустим application/json", extra={"formats": ["json"]}),
                request_id,
            )
        handler = asyncio.create_task(call_next(request))
        try:
            if not any(path.startswith(prefix) for prefix in _SYNC_SKIP) and ":load" not in path:
                response = await asyncio.wait_for(handler, timeout=settings.sync_deadline_ms / 1000)
            else:
                response = await handler
        except TimeoutError:
            handler.cancel()
            response = problem_response(
                DeadlineExceeded("синхронный дедлайн истёк", extra={"retry_after": 1}),
                request_id,
            )
        except FasError as exc:
            response = problem_response(exc, request_id)
        except asyncio.CancelledError:
            handler.cancel()
            raise
        except Exception as exc:  # noqa: BLE001 — неизвестное исключение становится 503, не 500
            response = problem_response(DependencyUnavailable(str(exc)), request_id)
        response.headers["X-Request-Id"] = request_id
        template = _route_template(request)
        REQUESTS.labels(request.method, template, str(response.status_code)).inc()
        LATENCY.labels(template).observe(time.perf_counter() - started)
        return response

    @app.exception_handler(FasError)
    async def _fas_error(request: Request, exc: FasError):
        return problem_response(exc, getattr(request.state, "request_id", "unknown"))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        if isinstance(exc, FasError):
            return problem_response(exc, getattr(request.state, "request_id", "unknown"))
        return problem_response(
            DependencyUnavailable("внутренняя ошибка"),
            getattr(request.state, "request_id", "unknown"),
        )

    def _svc():
        current = app.state.service
        if current is None:
            raise DependencyUnavailable("сервис не собран")
        return current

    def _support():
        current = app.state.support
        if current is None:
            raise DependencyUnavailable("Redis не подключён")
        return current

    async def _limited(request: Request, actor: Actor):
        support = _support()
        try:
            await support.rate_limit(actor)
        except DependencyUnavailable:
            if request.method == "GET":
                return
            raise
        app.state.inflight += 1
        if app.state.inflight > settings.api_max_inflight:
            app.state.inflight -= 1
            from finance_analysis.domain.errors import Overloaded

            raise Overloaded("реплика перегружена", extra={"retry_after": 1})
        return support

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready():
        body = await _svc().ready()
        code = 200 if body["status"] == "ok" else 503
        return JSONResponse(body, status_code=code)

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/capabilities")
    async def capabilities(request: Request):
        actor = _actor(request)
        await _limited(request, actor)
        try:
            return _svc().capabilities()
        finally:
            app.state.inflight -= 1

    @app.post("/v1/books/{job_id}:load")
    async def load_book(job_id: str, request: Request):
        checked = check_job(job_id)
        actor = _actor(request)
        support = await _limited(request, actor)
        method, route = "POST", "/v1/books/{job_id}:load"
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await _idem_begin(support, actor, method, route, request, raw)
            if cached is not None:
                return _idem_response(cached)
            pending = _idem_key(request) is not None
            async with support.user_inflight(actor):
                result = await _svc().ensure(
                    checked,
                    actor,
                    wait_sec=settings.load_sync_sec,
                    prefer_async=_prefer_async(request),
                )
            if isinstance(result, Accepted):
                response = JSONResponse(result.operation, status_code=202, headers=_op_headers(result))
                await _idem_finish(support, actor, method, route, request, raw, result.operation, 202)
                pending = False
                return response
            if isinstance(result, Freshness):
                view = await _svc().describe(checked, result.head, fresh=True)
            else:
                view = await _svc().describe(checked, result, fresh=False)
            if isinstance(view, Accepted):
                response = JSONResponse(view.operation, status_code=202, headers=_op_headers(view))
                await _idem_finish(support, actor, method, route, request, raw, view.operation, 202)
                pending = False
                return response
            await _idem_finish(support, actor, method, route, request, raw, view.body, 200)
            pending = False
            return view.body
        except BaseException:
            if pending:
                await _idem_abort(support, actor, method, route, request, raw)
            raise
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/builds")
    async def list_builds(job_id: str, request: Request, page_size: int = 50, page_token: str | None = None):
        checked = check_job(job_id)
        actor = _actor(request)
        await _limited(request, actor)
        try:
            if page_size < 1 or page_size > 1000:
                raise InvalidArgument("page_size должен быть от 1 до 1000")
            async with _support().user_inflight(actor):
                return await _svc().list_builds(checked, page_size=page_size, page_token=page_token)
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/builds/{build_key}")
    async def get_build(job_id: str, build_key: str, request: Request):
        checked = check_job(job_id)
        build = check_build(build_key)
        actor = _actor(request)
        await _limited(request, actor)
        try:
            async with _support().user_inflight(actor):
                return await _svc().get_build(checked, build)
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}")
    async def get_book(job_id: str, request: Request):
        checked = check_job(job_id)
        actor = _actor(request)
        await _limited(request, actor)
        try:
            async with _support().user_inflight(actor):
                view = await _svc().book_view(checked, actor, wait_sec=settings.load_sync_sec)
        finally:
            app.state.inflight -= 1
        if isinstance(view, Accepted):
            return JSONResponse(view.operation, status_code=202, headers=_op_headers(view))
        return view.body

    async def _calc(job_id: str, request: Request, method):
        checked = check_job(job_id)
        actor = _actor(request)
        support = await _limited(request, actor)
        route = _route_template(request)
        raw = b""
        pending = False
        try:
            raw = await request.body()
            cached = await _idem_begin(support, actor, "POST", route, request, raw)
            if cached is not None:
                return _idem_response(cached)
            pending = _idem_key(request) is not None
            try:
                body = await request.json() if raw else {}
            except Exception as exc:
                raise InvalidArgument("тело не JSON") from exc
            if not isinstance(body, dict):
                raise InvalidArgument("тело должно быть объектом")
            digest = hashlib.sha256(raw or b"{}").hexdigest()
            flight = f"{checked}:{route}:{digest}"

            async def _run():
                async with support.user_inflight(actor):
                    return await method(checked, body, actor, wait_sec=settings.sync_deadline_ms / 1000)

            result = await support.singleflight(flight, _run)
            if isinstance(result, Accepted):
                await _idem_finish(support, actor, "POST", route, request, raw, result.operation, 202)
                pending = False
                return JSONResponse(result.operation, status_code=202, headers=_op_headers(result))
            await _idem_finish(support, actor, "POST", route, request, raw, result, 200)
            pending = False
            return result
        except BaseException:
            if pending:
                await _idem_abort(support, actor, "POST", route, request, raw)
            raise
        finally:
            app.state.inflight -= 1

    @app.post("/v1/books/{job_id}/series")
    async def series(job_id: str, request: Request):
        return await _calc(job_id, request, _svc().series)

    @app.post("/v1/books/{job_id}/slice")
    async def slice_route(job_id: str, request: Request):
        return await _calc(job_id, request, _svc().slice)

    @app.post("/v1/books/{job_id}/expression")
    async def expression(job_id: str, request: Request):
        return await _calc(job_id, request, _svc().expression)

    @app.post("/v1/books/{job_id}/periods:resolve")
    async def periods(job_id: str, request: Request):
        return await _calc(job_id, request, _svc().resolve_periods)

    @app.post("/v1/books/{job_id}/decisions")
    async def decisions(job_id: str, request: Request):
        return await _calc(job_id, request, _svc().submit_decisions)

    @app.get("/v1/operations/{op_id}")
    async def get_operation(op_id: str, request: Request, wait_ms: int = 0):
        actor = _actor(request)
        await _limited(request, actor)
        try:
            body = await _svc().wait_op(op_id, wait_ms)
        finally:
            app.state.inflight -= 1
        return body

    @app.get("/v1/operations")
    async def list_operations(request: Request, kind: str | None = None, job_id: str | None = None, status: str | None = None):
        actor = _actor(request)
        await _limited(request, actor)
        try:
            if job_id:
                check_job(job_id)
            rows = await _svc().list_ops(kind=kind, job_id=job_id, status=status)
        finally:
            app.state.inflight -= 1
        return {"operations": rows}

    @app.post("/v1/operations/{op_id}:cancel")
    async def cancel(op_id: str, request: Request):
        actor = _actor(request)
        support = await _limited(request, actor)
        try:
            await request.body()
            async with support.user_inflight(actor):
                return await _svc().cancel_op(op_id, actor)
        finally:
            app.state.inflight -= 1

    wrapped = CancelOnDisconnect(app)
    wrapped.fastapi = app
    return wrapped


class CancelOnDisconnect:
    """Отменяет обработчик, когда ASGI присылает http.disconnect."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        queue: asyncio.Queue = asyncio.Queue()
        disconnected = asyncio.Event()

        async def feed() -> None:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected.set()
                await queue.put(message)
                if message["type"] == "http.disconnect":
                    return

        async def inner_receive():
            return await queue.get()

        feeder = asyncio.create_task(feed())
        handler = asyncio.create_task(self.app(scope, inner_receive, send))

        async def watch() -> None:
            while not handler.done():
                if disconnected.is_set():
                    handler.cancel()
                    return
                await asyncio.sleep(0.01)

        watcher = asyncio.create_task(watch())
        try:
            await handler
        except asyncio.CancelledError:
            return
        finally:
            watcher.cancel()
            feeder.cancel()


def _op_headers(result: Accepted) -> dict:
    op_id = result.operation["id"]
    return {
        "Operation-Location": f"/v1/operations/{op_id}",
        "Location": f"/v1/operations/{op_id}",
        "Retry-After": str(result.retry_after),
    }


def _idem_key(request: Request) -> str | None:
    return request.headers.get("idempotency-key") or None


async def _idem_abort(support, actor, method, route, request: Request, raw: bytes) -> None:
    key = _idem_key(request)
    if not key or support is None:
        return
    await support.idem_abort(actor, method, route, key, raw)


async def _idem_begin(support, actor, method, route, request: Request, raw: bytes):
    key = request.headers.get("idempotency-key")
    if not key:
        return None
    if len(key) > 200:
        raise InvalidId("Idempotency-Key слишком длинный")
    return await support.idem_begin(actor, method, route, key, raw)


async def _idem_finish(support, actor, method, route, request: Request, raw: bytes, response: dict, status: int) -> None:
    key = request.headers.get("idempotency-key")
    if not key:
        return
    await support.idem_finish(actor, method, route, key, raw, response, status)


def _idem_response(stored: dict):
    return JSONResponse(stored["response"], status_code=int(stored["http_status"]))
