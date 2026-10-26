"""Маршруты /v1/glossary."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from finance_analysis.application.glossary_store import state_of
from finance_analysis.domain.errors import Forbidden


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
            lambda gloss, body, _match: gloss.resolve(str(body.get("text") or "")),
        )

    @app.post("/v1/glossary/releases")
    async def glossary_release(request: Request):
        async def run(gloss, body, match):
            _admin(request)
            dry_run = bool(body.get("dry_run"))
            source = str(body.get("source") or "api")
            if body.get("mode") == "replace":
                return await gloss.release([], match, dry_run=dry_run, source=source, document=body.get("document"))
            return await gloss.release(body.get("ops") or [], match, dry_run=dry_run, source=source)

        return await write(request, run)

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
            result = await gloss.transition(
                body.get("version"),
                str(body.get("status") or ""),
                match,
                force=bool(body.get("force")),
                reason=body.get("reason"),
            )
            await svc().remap_glossary()
            return result

        return await write(request, run)

    @app.post("/v1/glossary:rollback")
    async def glossary_rollback(request: Request):
        async def run(gloss, _body, match):
            _admin(request)
            result = await gloss.rollback(match)
            await svc().remap_glossary()
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
            result = await gloss.decide_proposals(body.get("decisions") or [])
            await svc().learning.proposals_rejected(result.pop("rejected", []))
            if (result.get("release") or {}).get("status") == "active":
                await svc().remap_glossary()
            return result

        return await write(request, run)
