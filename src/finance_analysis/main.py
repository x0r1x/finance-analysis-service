"""Composition root API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.adapters.ml.cluster import HdbscanCluster
from finance_analysis.adapters.ml.http import build_models, close_models
from finance_analysis.adapters.redis.runtime import RedisRuntime, version_at_least
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.settings import Settings, load_settings


async def assemble(settings: Settings) -> tuple[FasService, RedisRuntime]:
    if not settings.fas_redis_url:
        from finance_analysis.domain.errors import StartupError

        raise StartupError("FAS_REDIS_URL не задан")
    store = await open_storage(settings)
    support = RedisRuntime.connect(settings)
    if not await support.ping():
        from finance_analysis.domain.errors import StartupError

        raise StartupError("Redis не отвечает")
    version = await support.server_version()
    if not version_at_least(version):
        from finance_analysis.domain.errors import StartupError

        raise StartupError(f"нужен Redis 8.6.5 или новее, сейчас {version}")
    fixture = os.environ.get("FAS_FIXTURE_DIR")
    if fixture:
        builder = FixtureBuilder(Path(fixture))
    else:
        builder = HttpBuilder(settings)
    service = FasService(
        settings,
        store,
        PyarrowParquet(),
        builder,
        WrenQuery(settings),
        support,
        models=build_models(settings),
        vector_index=NumpyIndex(),
        cluster=HdbscanCluster(),
    )
    return service, support


async def _watch_glossary(service, support) -> None:
    cached = await support.cache_get("fas:glossary:version")
    if cached:
        text = cached.decode() if isinstance(cached, bytes) else str(cached)
        await service.catch_glossary(text)
    async for version in support.messages("fas:glossary:changed"):
        await service.catch_glossary(version)


def main() -> None:
    settings = load_settings()
    asgi = create_app(settings)
    api = asgi.fastapi

    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service, support = await assemble(settings)
        _app.state.service = service
        _app.state.support = support
        _app.state.settings = settings
        _app.state.inflight = 0
        watch = asyncio.create_task(_watch_glossary(service, support))
        yield
        watch.cancel()
        try:
            await watch
        except asyncio.CancelledError:
            pass
        service.draining = True
        await service.settle()
        await close_models(service.models)
        await support.close()
        await service.builder.aclose()

    api.router.lifespan_context = lifespan
    uvicorn.run(asgi, host=os.environ.get("FAS_HOST", "0.0.0.0"), port=int(os.environ.get("FAS_PORT", "8080")))


if __name__ == "__main__":
    main()
