"""Загрузка большой книги не держит цикл событий: разбор снимка, привязка без embed, суммы фактов."""

import json
import threading
import time
from types import SimpleNamespace

import anyio
import httpx

from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.application import learning as learning_module
from finance_analysis.application import mapping_pipeline
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.learning import Learning
from finance_analysis.application.mapping_pipeline import MappingPipeline, expand
from finance_analysis.application.project import derive_rows, prepare_rows
from finance_analysis.application.service import FasService
from finance_analysis.domain.candidates import Candidate
from finance_analysis.domain.deadline import Deadline
from finance_analysis.settings import Settings
from tests.models import FakeRerank
from tests.unit.loop_gap import LIMIT, loop_gaps

CATALOG = load_catalog()


class _Concepts(dict):
    def __init__(self, concepts):
        super().__init__(concepts)
        self.scans = 0

    def values(self):
        self.scans += 1
        return super().values()


class _Package:
    def __init__(self, concepts):
        self.concepts = concepts


def _package(concepts: dict):
    return _Package(concepts)


def test_expand_reads_abbreviations_once_and_keeps_overlaps():
    concepts = _Concepts(
        {
            "earnings": SimpleNamespace(
                expand={
                    "EBIT": "earnings before interest and tax",
                    "EBITDA": "earnings before interest, tax, depreciation and amortization",
                }
            )
        }
    )
    package = _package(concepts)
    first = expand("EBIT / EBITDA", package)
    second = expand("без аббревиатуры", package)
    assert "earnings before interest and tax" in first
    assert "depreciation and amortization" in first
    assert second == "без аббревиатуры"
    assert concepts.scans == 1
    assert "cash flow available for debt service" in expand("CF › CFADS", CATALOG)
    assert "денежный поток для обслуживания долга" in expand("CFADS и ДПОД", CATALOG)


def _row(key: str) -> dict:
    return {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": f"zzz {key}",
        "label_path_text": f"zzz {key}",
        "sheet": "S",
        "unit": "money",
        "check_row": False,
    }


async def test_score_without_embed_builds_the_catalog_once():
    created = 0
    real = Candidate

    def counting(concept, **kwargs):
        nonlocal created
        created += 1
        return real(concept, **kwargs)

    mapping_pipeline.Candidate = counting
    try:
        rows = prepare_rows({"dim_row": [_row("a"), _row("b")]}, [], CATALOG, None)
        pipeline = MappingPipeline(
            type("M", (), {"embed": None, "rerank": FakeRerank(), "clm": None, "llm": None})(),
            settings=Settings(FAS_REDIS_URL="redis://unused"),
        )
        result = await pipeline.score(
            "job",
            "run",
            rows,
            CATALOG,
            glossary_version="g",
            deadline=Deadline.after_ms(5000),
            clm=False,
        )
    finally:
        mapping_pipeline.Candidate = real
    assert created == len(CATALOG.concepts)
    assert result.evidence["a"].candidates is not result.evidence["b"].candidates
    assert {item.concept for item in result.evidence["a"].candidates}


def _context(rows: int, periods: int = 11) -> dict:
    body = []
    for index in range(rows):
        body.append(
            {
                "row_key": f"r{index}",
                "sheet": "Model",
                "row": index + 1,
                "label": "Выручка",
                "kind": "fact",
                "series": [
                    {
                        "axis_id": "years",
                        "values": ["1"] * periods,
                        "value_statuses": ["cached"] * periods,
                        "normalized_values": ["1"] * periods,
                    }
                ],
            }
        )
    return {
        "axes": [
            {
                "id": "years",
                "sheet": "Model",
                "periods": [
                    {"col": 4 + period, "period_key": str(2020 + period), "index": period, "text": str(2020 + period)}
                    for period in range(periods)
                ],
            }
        ],
        "blocks": [{"block_id": "b", "sheet": "Model", "kind": "matrix", "rows": body}],
    }


async def test_context_parse_runs_off_the_event_loop(monkeypatch):
    from finance_analysis.adapters.builder import http as http_module

    main = threading.get_ident()
    seen = []
    real = http_module.parse_context

    def marking(payload):
        seen.append(threading.get_ident())
        return real(payload)

    monkeypatch.setattr(http_module, "parse_context", marking)
    raw = json.dumps(_context(2, periods=1)).encode()
    limiter = anyio.CapacityLimiter(2)
    limiters = []
    real_sync = http_module.anyio.to_thread.run_sync

    async def spy(func, *args, **kwargs):
        limiters.append(kwargs.get("limiter"))
        return await real_sync(func, *args, **kwargs)

    monkeypatch.setattr(http_module.anyio.to_thread, "run_sync", spy)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"), client=client, cpu=limiter)
    snapshot = await builder.context("job")
    await client.aclose()
    assert len(snapshot.rows) == 2
    assert seen == [seen[0]]
    assert seen[0] != main
    assert limiters == [limiter]


class _Append:
    def __init__(self):
        self.rows = None

    async def append(self, rows, sub=None):
        self.rows = rows


async def test_after_derive_sums_facts_off_the_event_loop(monkeypatch):
    main = threading.get_ident()
    seen = []
    real = learning_module._abs_by_row

    def marking(facts):
        seen.append(threading.get_ident())
        return real(facts)

    monkeypatch.setattr(learning_module, "_abs_by_row", marking)
    limiter = anyio.CapacityLimiter(2)
    limiters = []
    real_sync = learning_module.anyio.to_thread.run_sync

    async def spy(func, *args, **kwargs):
        limiters.append(kwargs.get("limiter"))
        return await real_sync(func, *args, **kwargs)

    monkeypatch.setattr(learning_module.anyio.to_thread, "run_sync", spy)
    learning = Learning.__new__(Learning)
    learning.signals = _Append()
    learning.unmapped = _Append()
    learning.models = SimpleNamespace(embed=None)
    learning.embed_model = ""
    learning._cpu = limiter
    prepared = [_row("a")]
    bindings = [{"binding_key": "a", "status": "unknown", "source": "inferred", "importance": "peripheral", "row_key": "a"}]
    facts = [{"row_key": "a", "axis_id": "ax", "period_id": "p", "normalized_value": "12.5"}]
    found = await learning.after_derive(
        "job",
        prepared=prepared,
        bindings=bindings,
        facts=facts,
        links=[],
        embeddings={},
        nearest={},
        package=CATALOG,
        glossary_version="g",
        profile=None,
        identities={},
    )
    assert found["unmapped"] == 1
    assert seen == [seen[0]]
    assert seen[0] != main
    assert limiters == [limiter, limiter]


async def test_heartbeat_notices_a_blocked_loop():
    async with loop_gaps() as gaps:
        time.sleep(0.25)  # noqa: ASYNC251 — stall the test must notice
    assert max(gaps) >= LIMIT


async def test_large_synthetic_book_does_not_block_the_event_loop():
    """Тот же порог, что test_event_loop_not_blocked_on_health, на синтетической книге.

    Маленькая книга не дотягивает до 0,1 с. Здесь разбор снимка, привязка без embed
    и сумма фактов сами по себе дольше порога, если идут в цикле.
    """

    raw = json.dumps(_context(15_000)).encode()
    rows = [_row(f"r{index}") for index in range(8_000)]
    facts = [
        {"row_key": f"r{index % 1000}", "axis_id": "ax", "period_id": f"p{index % 11}", "normalized_value": "12.5"}
        for index in range(600_000)
    ]

    class _Rerank:
        async def rerank(self, _query, _documents, *, deadline, top_n):
            return [(0, 1.0)]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"), client=client)
    pipeline = MappingPipeline(
        type("M", (), {"embed": None, "rerank": _Rerank(), "clm": None, "llm": None})(),
        settings=Settings(FAS_REDIS_URL="redis://unused"),
    )
    learning = Learning.__new__(Learning)
    learning.signals = _Append()
    learning.unmapped = _Append()
    learning.models = SimpleNamespace(embed=None)
    learning.embed_model = ""
    learning._cpu = anyio.CapacityLimiter(2)
    prepared = [_row("a")]
    bindings = [{"binding_key": "a", "status": "unknown", "source": "inferred", "importance": "peripheral", "row_key": "a"}]
    try:
        async with loop_gaps() as gaps:
            snapshot = await builder.context("job")
            result = await pipeline.score(
                "job",
                "run",
                rows,
                CATALOG,
                glossary_version="g",
                deadline=Deadline.after_ms(5000),
                clm=False,
            )
            derived = await learning.after_derive(
                "job",
                prepared=prepared,
                bindings=bindings,
                facts=facts,
                links=[],
                embeddings={},
                nearest={},
                package=CATALOG,
                glossary_version="g",
                profile=None,
                identities={},
            )
    finally:
        await client.aclose()
    assert len(snapshot.rows) == 15_000
    assert result.evidence
    assert derived["unmapped"] == 1
    assert max(gaps) < LIMIT


def _sheet_row(key: str, label: str, **extra) -> dict:
    return {
        "model_id": "m",
        "build_key": "b",
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": label,
        "check_row": False,
        "sheet": "CF",
        "unit": "money",
        "row_num": 1,
        **extra,
    }


def _without_clock(derived: dict) -> dict:
    bindings = []
    for row in derived["bindings"]:
        item = dict(row)
        item.pop("updated_at_utc", None)
        bindings.append(item)
    return {**derived, "bindings": bindings}


async def test_large_derive_does_not_block_the_event_loop():
    """Полный `_derive` на книге, где синхронный проход фактов дольше 0,1 с."""

    rows = [
        _sheet_row("valued", "Выручка"),
        _sheet_row("blank", "Пустая"),
        _sheet_row("missing", "Нет фактов"),
        _sheet_row("check", "Проверка", check_row=True),
        _sheet_row("hidden", "Скрытая", hidden=True),
        _sheet_row("helper", "Служебная", kind="helper"),
    ]
    facts = [
        {
            "row_key": "valued",
            "axis_id": "ax",
            "period_id": "p1",
            "value_status": "cached",
            "normalized_value": "1",
            "value_dec": "1",
        }
        for _ in range(600_000)
    ]
    facts.append(
        {
            "row_key": "blank",
            "axis_id": "ax",
            "period_id": "p1",
            "value_status": "empty",
            "normalized_value": None,
            "value_dec": None,
        }
    )
    projected = {
        "dim_row": rows,
        "dim_period": [
            {
                "model_id": "m",
                "build_key": "b",
                "axis_id": "ax",
                "period_id": "p1",
                "period_index": 0,
                "axis_kind": "timeline",
            }
        ],
    }
    direct = derive_rows(
        projected,
        state_seq=1,
        derive="d",
        versions={"glossary": "none"},
        events=[],
        glossary=CATALOG,
        facts=facts,
        prepared=prepare_rows(projected, [], CATALOG, facts),
    )
    service = FasService.__new__(FasService)
    service._cpu = anyio.CapacityLimiter(2)

    async def package(_version, _events):
        return CATALOG

    class _Calibrators:
        async def active(self):
            return None

    service._book_package = package
    service.calibrators = _Calibrators()
    service.pipeline = SimpleNamespace(enabled=False)
    async with loop_gaps() as gaps:
        derived = await service._derive(
            "job",
            projected,
            state_seq=1,
            derive="d",
            versions={"glossary": "none"},
            events=[],
            facts=facts,
            links=[],
            learn=False,
        )
    assert max(gaps) < LIMIT
    assert _without_clock(derived) == _without_clock(direct)
    reasons = {row["row_key"]: row["exclusion_reason"] for row in derived["row_semantics"]}
    assert reasons == {
        "valued": None,
        "blank": "empty_series",
        "missing": "empty_series",
        "check": "check_row",
        "hidden": "hidden",
        "helper": "helper",
    }
