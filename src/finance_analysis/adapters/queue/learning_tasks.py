"""Задачи обучения глоссария (§4.13.5): cluster_unmapped и glossary_mine — `batch`, слияние — `maintenance`.

Все задачи идемпотентны: повтор даёт те же предложения (дедупликация по кластеру и метке).
"""

from __future__ import annotations

import os
from pathlib import Path

from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.adapters.ml.cluster import HdbscanCluster
from finance_analysis.adapters.ml.http import build_models
from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.calibrators import CalibratorStore
from finance_analysis.application.examples import ExampleStore
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.application.learning import Learning
from finance_analysis.application.service import FasService
from finance_analysis.domain.glossary_release import package_of

CLUSTER_TASK = "fas.cluster_unmapped"
MINE_TASK = "fas.glossary_mine"
COMPACT_TASK = "fas.compact_learning"
RECALIBRATE_TASK = "fas.recalibrate"

_CACHE: dict = {}
_SERVICE: dict = {}


def _learning() -> tuple[Learning, GlossaryStore, CalibratorStore]:
    rt = runtime_mod.RUNTIME
    if rt is None:
        raise RuntimeError("worker runtime не привязан")
    cached = _CACHE.get(id(rt))
    if cached:
        return cached
    settings = rt.settings
    parquet = PyarrowParquet()
    models = build_models(settings)
    glossary = GlossaryStore(rt.store, rt.locks, lock_ttl_ms=settings.lock_ttl_ms)
    examples = ExampleStore(rt.store, parquet, NumpyIndex(), model=settings.embed_model if models.embed else "")
    learning = Learning(rt.store, parquet, glossary, examples, models, HdbscanCluster(), settings)
    built = (learning, glossary, CalibratorStore(rt.store))
    _CACHE.clear()
    _CACHE[id(rt)] = built
    return built


async def _active(glossary: GlossaryStore):
    state = await glossary.ensure()
    document = await glossary.document(state["active"])
    return package_of(document), document


async def cluster_unmapped() -> dict:
    learning, glossary, _cal = _learning()
    package, _document = await _active(glossary)
    return await learning.cluster_unmapped(package)


async def _mine_service() -> FasService:
    """Ночной mine идёт через FasService: там shadow-гейт и ремап. Хранилище и замки — те же, что у воркера."""

    rt = runtime_mod.RUNTIME
    if rt is None:
        raise RuntimeError("worker runtime не привязан")
    cached = _SERVICE.get(id(rt))
    if cached:
        return cached
    settings = rt.settings
    fixture = os.environ.get("FAS_FIXTURE_DIR")
    builder = FixtureBuilder(Path(fixture)) if fixture else HttpBuilder(settings)
    service = FasService(
        settings,
        rt.store,
        PyarrowParquet(),
        builder,
        WrenQuery(settings),
        rt.locks,
        models=build_models(settings),
        vector_index=NumpyIndex(),
        cluster=HdbscanCluster(),
    )
    _SERVICE.clear()
    _SERVICE[id(rt)] = service
    return service


async def glossary_mine() -> dict:
    service = await _mine_service()
    package, document = await _active(service.glossary)
    return await service.learning.mine(package, document)


async def compact_learning() -> dict:
    learning, _glossary, _cal = _learning()
    return await learning.compact()


async def recalibrate() -> dict:
    """Обучает калибратор-кандидат; активирует его только `fas calibrator activate` (§5.6)."""

    learning, _glossary, calibrators = _learning()
    rt = runtime_mod.RUNTIME
    body = await calibrators.train(await learning.examples.all_rows(), max_risk=rt.settings.calibrator_max_risk)
    return {"version": body["version"], "metrics": body["metrics"]}


def register_learning(broker, *, schedules: bool, settings, batch: str, maintenance: str) -> None:
    plan = [
        (cluster_unmapped, CLUSTER_TASK, batch, getattr(settings, "unmapped_cluster_cron", None)),
        (glossary_mine, MINE_TASK, batch, getattr(settings, "glossary_mine_cron", None)),
        (compact_learning, COMPACT_TASK, maintenance, getattr(settings, "compact_cron", None)),
        (recalibrate, RECALIBRATE_TASK, batch, None),
    ]
    for function, name, queue, cron in plan:
        if schedules and cron:
            broker.register_task(function, task_name=name, schedule=[{"cron": cron}], queue_name=queue)
        else:
            broker.register_task(function, task_name=name, queue_name=queue)
