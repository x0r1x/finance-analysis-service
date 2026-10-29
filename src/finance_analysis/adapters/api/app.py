"""Оболочка HTTP: middleware, дедлайн и служебные маршруты."""

from __future__ import annotations

import asyncio
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

from finance_analysis.adapters.api.http import accept_ok, actor, route_template
from finance_analysis.adapters.api.problems import problem_response
from finance_analysis.adapters.api.route import register as register_routes
from finance_analysis.domain.book import FAS_VERSION, Actor
from finance_analysis.domain.deadline import (
    Deadline,
    bind_request_deadline,
    reset_request_deadline,
)
from finance_analysis.domain.errors import (
    DeadlineExceeded,
    DependencyUnavailable,
    FasError,
    NotAcceptable,
)
from finance_analysis.settings import Settings

REQUESTS = Counter("fas_http_requests_total", "HTTP-запросы", ["method", "path", "status"])
LATENCY = Histogram("fas_http_request_seconds", "Длительность HTTP", ["path"])
LOOP_LAG = Gauge("fas_event_loop_lag_seconds", "Задержка event loop")

_SYNC_SKIP = ("/health/", "/metrics", "/v1/operations", "/v1/capabilities")


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
        if not accept_ok(path, accept):
            return problem_response(
                NotAcceptable("допустим application/json", extra={"formats": ["json"]}),
                request_id,
            )
        synchronous = not any(path.startswith(prefix) for prefix in _SYNC_SKIP) and ":load" not in path
        limit_ms = settings.sync_deadline_ms
        raw_deadline = request.headers.get("x-fas-deadline-ms")
        explicit = bool(raw_deadline and raw_deadline.strip().isdigit())
        if explicit:
            limit_ms = max(1, min(int(raw_deadline.strip()), limit_ms))
        # Дедлайн передаётся стадиям моделей (§4.13.4); у асинхронных маршрутов — только явный.
        bound = bind_request_deadline(Deadline.after_ms(limit_ms) if synchronous or explicit else None)
        try:
            handler = asyncio.create_task(call_next(request))
        finally:
            reset_request_deadline(bound)
        try:
            if synchronous:
                response = await asyncio.wait_for(handler, timeout=limit_ms / 1000)
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
        template = route_template(request)
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

    async def _limited(request: Request, who: Actor):
        runtime = _support()
        try:
            await runtime.rate_limit(who)
        except DependencyUnavailable:
            if request.method == "GET":
                return
            raise
        app.state.inflight += 1
        if app.state.inflight > settings.api_max_inflight:
            app.state.inflight -= 1
            from finance_analysis.domain.errors import Overloaded

            raise Overloaded("реплика перегружена", extra={"retry_after": 1})
        return runtime

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
        who = actor(request)
        await _limited(request, who)
        try:
            return _svc().capabilities()
        finally:
            app.state.inflight -= 1

    register_routes(app, settings, actor=actor, limited=_limited, svc=_svc, support=_support)

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
