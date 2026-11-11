"""Общие куски HTTP: актёр, Accept, идемпотентность, заголовки операции."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import Forbidden, InvalidId
from finance_analysis.domain.ids import actor_token


def accept_ok(path: str, accept: str) -> bool:
    """json везде. markdown — отчёт. SSE — только поток событий."""

    header = accept.lower()
    if path == "/metrics":
        return True
    if "application/json" in header or "*/*" in header or "application/problem+json" in header:
        return True
    if path.endswith("/report"):
        return "text/markdown" in header
    return path.startswith("/v1/operations/") and path.endswith("/events") and "text/event-stream" in header


def actor(request: Request) -> Actor:
    """Opaque actor labels for audit, quotas, and idempotency — not authentication.

    Raw ``X-User-Id`` / ``X-Client-Id`` are never verified. Prod must not treat them as
    proof of identity; privileged glossary writes use ``FAS_ADMIN_TOKEN`` instead.
    """

    user = request.headers.get("x-user-id")
    client = request.headers.get("x-client-id")
    if user:
        user = actor_token(user, header="X-User-Id")
    if client:
        client = actor_token(client, header="X-Client-Id")
    return Actor(user_id=user or "anonymous", client_id=client or "anonymous")


def require_admin(request: Request, settings) -> None:
    """Gate privileged writes when ``FAS_ADMIN_TOKEN`` is set.

    Call before idempotency begin so a replay without ``X-Admin-Token`` is 403,
    not a cached admin success.
    """

    expected = settings.fas_admin_token
    if not expected:
        return
    if request.headers.get("x-admin-token") != expected:
        raise Forbidden("нужен токен администратора")


def prefer_async(request: Request) -> bool:
    prefer = (request.headers.get("prefer") or "").lower()
    return "respond-async" in prefer


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


def op_headers(result: Accepted) -> dict:
    op_id = result.operation["id"]
    return {
        "Operation-Location": f"/v1/operations/{op_id}",
        "Location": f"/v1/operations/{op_id}",
        "Retry-After": str(result.retry_after),
    }


def idem_key(request: Request) -> str | None:
    return request.headers.get("idempotency-key") or None


async def idem_abort(support, who, method, route, request: Request, raw: bytes) -> None:
    key = idem_key(request)
    if not key or support is None:
        return
    await support.idem_abort(who, method, route, key, raw)


async def idem_begin(support, who, method, route, request: Request, raw: bytes):
    key = request.headers.get("idempotency-key")
    if not key:
        return None
    if len(key) > 200:
        raise InvalidId("Idempotency-Key слишком длинный")
    return await support.idem_begin(who, method, route, key, raw)


async def idem_finish(support, who, method, route, request: Request, raw: bytes, response: dict, status: int) -> None:
    key = request.headers.get("idempotency-key")
    if not key:
        return
    await support.idem_finish(who, method, route, key, raw, response, status)


def idem_response(stored: dict):
    return JSONResponse(stored["response"], status_code=int(stored["http_status"]))
