"""Маршруты /v1/profiles."""

from __future__ import annotations

from fastapi import Request

from finance_analysis.domain.errors import NotFound
from finance_analysis.domain.ids import profile_id as check_profile


def register(app, *, svc, write, read) -> None:
    @app.get("/v1/profiles")
    async def list_profiles(request: Request):
        return await read(request, lambda _who: svc().glossary.list_profiles())

    @app.put("/v1/profiles/{profile}")
    async def put_profile(profile: str, request: Request):
        check_profile(profile)
        return await write(
            request,
            lambda gloss, body, match: gloss.put_profile(
                profile,
                body,
                if_match=match,
                if_none_match=request.headers.get("if-none-match"),
            ),
        )

    @app.get("/v1/profiles/{profile}")
    async def get_profile(profile: str, request: Request):
        check_profile(profile)

        async def load(_who):
            body = await svc().glossary.profile_body(profile)
            if body is None:
                raise NotFound("профиль не найден")
            ref = await svc().glossary.profile_ref(profile)
            return {"id": profile, "version": ref, "body": body}

        return await read(request, load)
