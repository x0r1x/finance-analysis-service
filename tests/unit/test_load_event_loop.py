"""Загрузка большой книги не держит цикл событий: разбор снимка, привязка без embed, суммы фактов."""

import asyncio
import json
import threading
from types import SimpleNamespace

import httpx

from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.application import learning as learning_module
from finance_analysis.application import mapping_pipeline
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.learning import Learning
from finance_analysis.application.mapping_pipeline import MappingPipeline, expand
from finance_analysis.application.project import prepare_rows
from finance_analysis.domain.candidates import Candidate
from finance_analysis.domain.deadline import Deadline
from finance_analysis.settings import Settings
from tests.models import FakeRerank

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

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"), client=client)
    snapshot = await builder.context("job")
    await client.aclose()
    assert len(snapshot.rows) == 2
    assert seen == [seen[0]]
    assert seen[0] != main


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
    learning = Learning.__new__(Learning)
    learning.signals = _Append()
    learning.unmapped = _Append()
    learning.models = SimpleNamespace(embed=None)
    learning.embed_model = ""
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


def _watch_slow_callbacks(loop):
    slow = []

    def handler(_loop, context):
        message = context.get("message", "")
        if "Executing" in message and "took" in message:
            slow.append(message)

    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: handler(_loop, context) or None)
    loop.set_debug(True)
    return slow, previous


async def test_large_synthetic_book_does_not_block_the_event_loop():
    """Тот же признак, что test_event_loop_not_blocked_on_health, на синтетической книге.

    Маленькая книга не дотягивает до порога asyncio (0,1 с). Здесь разбор снимка,
    привязка без embed и сумма фактов сами по себе дольше порога, если идут в цикле.
    """

    raw = json.dumps(_context(15_000)).encode()
    rows = [_row(f"r{index}") for index in range(8_000)]
    facts = [
        {"row_key": f"r{index % 1000}", "axis_id": "ax", "period_id": f"p{index % 11}", "normalized_value": "12.5"}
        for index in range(600_000)
    ]
    await asyncio.sleep(0)
    loop = asyncio.get_running_loop()
    slow, previous = _watch_slow_callbacks(loop)

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
    prepared = [_row("a")]
    bindings = [{"binding_key": "a", "status": "unknown", "source": "inferred", "importance": "peripheral", "row_key": "a"}]
    try:
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
        loop.set_exception_handler(previous)
        loop.set_debug(False)
    assert len(snapshot.rows) == 15_000
    assert result.evidence
    assert derived["unmapped"] == 1
    assert slow == []
