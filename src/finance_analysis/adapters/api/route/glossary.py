"""Маршруты /v1/glossary."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from finance_analysis.adapters.api.http import actor
from finance_analysis.adapters.queue.names import GLOSSARY
from finance_analysis.application.glossary_store import (
    check_transition_request,
    state_of,
)
from finance_analysis.domain.errors import Forbidden, InvalidArgument


def agreed_dry_run(query: str | None, body: dict) -> bool:
    """Берёт флаг пробного прогона из строки запроса и из тела.

    `?dry_run=true` или `false` и поле `dry_run` в теле задают один и тот же
    прогон. В строке запроса это слова true и false без учёта регистра. В теле
    годится только логическое значение: строка `"false"` не считается пробным
    прогоном и не записывает релиз. Если задан только один источник, берётся он.
    Если заданы оба и значения разные, запрос отклоняется. Если не задан ни
    один, релиз записывается по-настоящему.
    """

    from_query = _query_flag(query) if query is not None else None
    if "dry_run" in body:
        from_body = _body_flag(body.get("dry_run"))
        if from_query is not None and from_query is not from_body:
            raise InvalidArgument("dry_run в строке запроса и в теле не совпадают")
        return from_body
    return bool(from_query)


def _query_flag(value: object) -> bool:
    if isinstance(value, str):
        token = value.casefold()
        if token == "true":
            return True
        if token == "false":
            return False
    raise InvalidArgument("dry_run должен быть true или false")


def _body_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise InvalidArgument("dry_run в теле должен быть логическим true или false")


def register(app, settings, *, svc, write, read) -> None:
    def _admin(request: Request) -> None:
        expected = settings.fas_admin_token
        if not expected:
            return
        if request.headers.get("x-admin-token") != expected:
            raise Forbidden("нужен токен администратора")

    @app.get("/v1/glossary")
    async def glossary_state(request: Request):
        async def load(_who):
            state = await svc().glossary.ensure()
            body = state_of(state)
            return JSONResponse(body, headers={"ETag": body["etag"]})

        return await read(request, load)

    @app.get("/v1/glossary/releases")
    async def glossary_releases(request: Request):
        return await read(request, lambda _who: svc().glossary.releases())

    @app.get("/v1/glossary/content")
    async def glossary_content(request: Request, version: str | None = None, format: str = "json"):
        async def load(_who):
            body, media = await svc().glossary.content(version, format)
            return Response(body, media_type=media)

        return await read(request, load)

    @app.get("/v1/glossary/labels")
    async def glossary_labels(request: Request, q: str = ""):
        return await read(request, lambda _who: svc().glossary.labels(q))

    @app.get("/v1/glossary/impact")
    async def glossary_impact(request: Request):
        return await read(request, lambda _who: svc().glossary.impact())

    @app.post("/v1/glossary:resolve")
    async def glossary_resolve(request: Request):
        return await write(
            request,
            lambda gloss, body, _match: svc().resolve_concept(body),
        )

    @app.post("/v1/glossary/releases")
    async def glossary_release(request: Request, dry_run: str | None = None):
        def fingerprint(raw: bytes, body: dict) -> bytes:
            # Флаг участвует в ключе идемпотентности. Иначе повтор с тем же телом
            # и другим ?dry_run= вернёт сохранённый ответ и не проверит расхождение.
            flag = agreed_dry_run(dry_run, body)
            mark = b"true" if flag else b"false"
            return raw + b"\ndry_run=" + mark

        async def run(gloss, body, match):
            _admin(request)
            preview = agreed_dry_run(dry_run, body)
            source = str(body.get("source") or "api")
            if body.get("mode") == "replace":
                return await gloss.release([], match, dry_run=preview, source=source, document=body.get("document"))
            return await gloss.release(body.get("ops") or [], match, dry_run=preview, source=source)

        return await write(request, run, fingerprint=fingerprint)

    @app.get("/v1/glossary/releases/{version}")
    async def glossary_release_one(version: str, request: Request):
        return await read(request, lambda _who: svc().glossary.release_view(version))

    @app.get("/v1/glossary/events")
    async def glossary_events(request: Request):
        return await read(request, lambda _who: svc().glossary.events())

    @app.get("/v1/glossary/diff")
    async def glossary_diff(request: Request, to: str | None = None):
        source = request.query_params.get("from")
        return await read(request, lambda _who: svc().glossary.diff(source, to))

    @app.get("/v1/glossary/concepts")
    async def glossary_concepts(request: Request):
        return await read(request, lambda _who: svc().glossary.concepts())

    @app.post("/v1/glossary/transitions")
    async def glossary_transition(request: Request):
        async def run(gloss, body, match):
            _admin(request)
            status = str(body.get("status") or "")
            version = body.get("version")
            force = bool(body.get("force"))
            reason = body.get("reason")
            check_transition_request(status, version, force=force, reason=reason)
            await svc().reject_glossary_busy()
            await gloss.require_match(match)
            return await svc().begin_glossary_transition(
                version,
                status,
                match,
                force=force,
                reason=reason,
                actor=actor(request),
                queue=GLOSSARY,
            )

        return await write(request, run)

    @app.get("/v1/glossary/stats")
    async def glossary_stats(request: Request, to: str | None = None, profile_id: str | None = None):
        start = request.query_params.get("from")
        return await read(request, lambda _who: svc().glossary_stats(start=start, end=to, profile_id=profile_id))

    @app.post("/v1/glossary:rollback")
    async def glossary_rollback(request: Request):
        async def run(gloss, _body, match):
            _admin(request)
            result = await gloss.rollback(match)
            await svc().begin_remap()
            return result

        return await write(request, run)

    @app.post("/v1/glossary/proposals")
    async def glossary_propose(request: Request):
        return await write(request, lambda gloss, body, _match: gloss.add_proposal(body))

    @app.get("/v1/glossary/proposals")
    async def glossary_proposals(request: Request, status: str | None = None, order_by: str | None = None):
        return await read(request, lambda _who: svc().glossary.proposals(status=status, order_by=order_by))

    @app.get("/v1/glossary/proposals/{proposal_id}")
    async def glossary_proposal(proposal_id: str, request: Request):
        return await read(request, lambda _who: svc().glossary.proposal(proposal_id))

    @app.post("/v1/glossary/proposals:decide")
    async def glossary_decide(request: Request):
        async def run(gloss, body, _match):
            _admin(request)
            decisions = body.get("decisions") or []
            accepts = isinstance(decisions, list) and any(
                isinstance(item, dict) and item.get("decision") == "accept" for item in decisions
            )
            if accepts:
                return await svc().begin_proposal_decision(decisions, actor(request), queue=GLOSSARY)
            result = await gloss.decide_proposals(decisions)
            await svc().learning.proposals_rejected(result.pop("rejected", []))
            return result

        return await write(request, run)
