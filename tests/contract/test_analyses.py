"""Фаза 1: `…/analyses` (audit), история, `…/findings`, `results/` (§3.2, §6.1, §12)."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet, load_schema
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application import service as service_module
from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.model_types import load_metric_inputs
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from tests.books import BUILDER_ROOT, job_id
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio

RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def test_audit_history_and_findings(app, local_service):
    async with _client(app) as client:
        before = await client.get(f"/v1/books/{RVI}/findings", headers=HEADERS)
        assert before.status_code == 404, before.text
        assert before.json()["code"] == "no_audit"
        assert before.json()["hint"]["body"] == {"type": "audit"}

        ran = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        assert ran.status_code == 200, ran.text
        result = ran.json()
        analysis_id = result["analysis_id"]
        assert result["status"] == "succeeded"
        assert result["is_latest"] is True
        assert result["builder_ref"]["job_id"] == RVI
        assert result["versions"]["rules"]["hardcoded_formula"] == "1"
        findings = result["result_data"]["findings"]
        codes = {item["code"] for item in findings}
        assert {"missing_cached_value", "formula_inconsistent_in_row", "offset_indirect_used"} <= codes
        assert result["summary"]["params"]["findings"] == len(findings)
        assert len({item["fingerprint"] for item in findings}) == len(findings)
        first = findings[0]
        assert set(first) >= {"code", "version", "error_class", "severity", "params", "locations", "fingerprint", "truncated", "builder_ref", "basis"}
        cited = {item["cell_id"] for item in result["citations"]}
        assert "PF Model!M537" in cited
        assert all(item["sheet"] == "PF Model" for item in result["citations"])

        history = await client.get(f"/v1/books/{RVI}/analyses", headers=HEADERS, params={"type": "audit"})
        assert history.status_code == 200, history.text
        [summary] = history.json()["items"]
        assert summary["analysis_id"] == analysis_id
        assert summary["current"] is True
        assert summary["finding_count"] == len(findings)

        stored = await client.get(f"/v1/books/{RVI}/analyses/{analysis_id}", headers=HEADERS)
        assert stored.status_code == 200, stored.text
        assert stored.json()["result_data"]["findings"] == findings

        listed = await client.get(f"/v1/books/{RVI}/findings", headers=HEADERS, params={"page_size": 1000})
        assert listed.status_code == 200, listed.text
        assert listed.json()["analysis_id"] == analysis_id
        assert [item["fingerprint"] for item in listed.json()["items"]] == [item["fingerprint"] for item in findings]
        missing = await client.get(
            f"/v1/books/{RVI}/findings", headers=HEADERS, params={"rule": "missing_cached_value", "severity": "medium"}
        )
        assert {item["code"] for item in missing.json()["items"]} == {"missing_cached_value"}
        assert len(missing.json()["items"]) == 20
        paged = await client.get(f"/v1/books/{RVI}/findings", headers=HEADERS, params={"page_size": 5})
        assert len(paged.json()["items"]) == 5
        assert paged.json()["next_page_token"] == paged.json()["items"][-1]["fingerprint"]

        target = next(item for item in findings if item["code"] == "formula_inconsistent_in_row")
        detail = await client.get(f"/v1/books/{RVI}/findings/{target['fingerprint']}", headers=HEADERS)
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["finding"] == target
        assert body["rule"]["code"] == "formula_inconsistent_in_row"
        trace = body["trace"]
        assert trace["source"] == "builder"
        assert trace["direction"] == "precedents" and trace["depth"] == 8
        first_cell = target["locations"][0]["cell_id"]
        assert trace["items"][0]["origin"] == first_cell
        assert trace["items"][0]["nodes"][0]["node_id"] == first_cell
        assert trace["items"][0]["edges"]
        calls = local_service.builder.calls.count(("GET", "/graph/trace"))
        again = await client.get(
            f"/v1/books/{RVI}/findings/{target['fingerprint']}", headers=HEADERS, params={"depth": 2}
        )
        assert max(node["depth"] for node in again.json()["trace"]["items"][0]["nodes"]) <= 2
        cached = await client.get(f"/v1/books/{RVI}/findings/{target['fingerprint']}", headers=HEADERS)
        assert cached.json()["trace"] == trace
        # Повтор с той же глубиной — из кэша Redis по summary_etag, без нового вызова builder.
        assert local_service.builder.calls.count(("GET", "/graph/trace")) == calls + len(again.json()["trace"]["items"])
        bad_depth = await client.get(f"/v1/books/{RVI}/findings/{target['fingerprint']}", headers=HEADERS, params={"depth": 99})
        assert bad_depth.status_code == 400

        bad_size = await client.get(f"/v1/books/{RVI}/findings", headers=HEADERS, params={"page_size": "abc"})
        assert bad_size.status_code == 400, bad_size.text
        assert bad_size.json()["code"] == "invalid_argument"

        unknown = await client.get(f"/v1/books/{RVI}/findings/{'0' * 40}", headers=HEADERS)
        assert unknown.status_code == 404
        bad = await client.get(f"/v1/books/{RVI}/findings/not-a-print", headers=HEADERS)
        assert bad.status_code == 400 and bad.json()["code"] == "invalid_id"

    report = json.loads(await local_service.store.get(f"books/{RVI}/_reports/{analysis_id}.json"))
    build = report["build_key"]
    marker = json.loads(await local_service.store.get(f"books/{RVI}/{build}/results/{analysis_id}/result.json"))
    assert set(marker["files"]) == {f"results/{analysis_id}/findings.parquet", f"results/{analysis_id}/run.parquet"}
    for rel, meta in marker["files"].items():
        dataset = rel.rsplit("/", 1)[-1].removesuffix(".parquet")
        doc = load_schema(dataset)
        parquet = pq.ParquetFile(local_service.store.physical(f"books/{RVI}/{build}/{rel}"))
        assert parquet.metadata.num_row_groups == 1
        assert parquet.metadata.row_group(0).column(0).compression == "ZSTD"
        assert [field.name for field in parquet.schema_arrow] == [column["name"] for column in doc["columns"]]
        assert parquet.schema_arrow.metadata[b"fas.schema"] == f"{dataset}@{doc['version']}".encode()
        assert parquet.metadata.num_rows == meta["rows"]
    rows = pq.read_table(local_service.store.physical(f"books/{RVI}/{build}/results/{analysis_id}/findings.parquet")).to_pylist()
    assert {row["fingerprint"] for row in rows} == {item["fingerprint"] for item in findings}
    assert {row["analysis_id"] for row in rows} == {analysis_id}

    # Строка схемы в маркерах совпадает с fas.schema в footer файла.
    manifest = json.loads(await local_service.store.get(f"books/{RVI}/{build}/manifest.json"))
    done = json.loads(await local_service.store.get(f"books/{RVI}/{build}/derived/{marker['derive_key']}/_done.json"))
    for files in (manifest["files"], done["files"], marker["files"]):
        for rel, meta in files.items():
            footer = pq.ParquetFile(local_service.store.physical(f"books/{RVI}/{build}/{rel}")).schema_arrow.metadata
            assert footer[b"fas.schema"].decode() == meta["schema"], rel

    # GC не трогает зафиксированный результат даже при нулевом возрасте.
    swept = await local_service.gc(now=datetime.now(UTC) + timedelta(days=1), max_age_s=0)
    assert swept["removed"] == 0
    assert await local_service.store.stat(f"books/{RVI}/{build}/results/{analysis_id}/findings.parquet")


async def test_audit_arguments_and_async(app):
    async with _client(app) as client:
        ratios = await client.post(f"/v1/books/{JOB}/analyses", headers=HEADERS, json={"type": "ratios"})
        assert ratios.status_code == 400
        assert ratios.json()["supported"] == list(load_metric_inputs()) == list(RATIO_METRICS) == [
            "dscr",
            "icr",
            "adscr",
            "dscr_min",
            "dscr_avg",
            "llcr",
            "plcr",
            "net_debt_ebitda",
            "escrow_coverage",
        ]
        unknown = await client.post(f"/v1/books/{JOB}/analyses", headers=HEADERS, json={"type": "audit", "rules": ["nope"]})
        assert unknown.status_code == 400
        assert unknown.json()["rules"] == ["nope"]

        narrow = await client.post(
            f"/v1/books/{JOB}/analyses",
            headers=HEADERS,
            json={"type": "audit", "rules": ["no_master_check", "long_formula"], "scope": {"sheets": ["Debt"]}},
        )
        assert narrow.status_code == 200, narrow.text
        body = narrow.json()
        assert set(body["versions"]["rules"]) == {"no_master_check", "long_formula"}
        assert {item["code"] for item in body["result_data"]["findings"]} == {"long_formula"}
        assert all(
            location["cell_id"].startswith("Debt!")
            for item in body["result_data"]["findings"]
            for location in item["locations"]
        )
        odd = await client.post(f"/v1/books/{JOB}/analyses", headers=HEADERS, json={"type": "audit", "scope": {"phase": "x"}})
        assert odd.status_code == 400
        assert odd.json()["fields"] == ["phase"]

        deferred = await client.post(
            f"/v1/books/{JOB}/analyses",
            headers={**HEADERS, "Prefer": "respond-async"},
            json={"type": "audit"},
        )
        assert deferred.status_code == 202, deferred.text
        op_id = deferred.json()["id"]
        assert deferred.headers["Operation-Location"] == f"/v1/operations/{op_id}"
        done = await client.get(f"/v1/operations/{op_id}", params={"wait_ms": 20_000})
        assert done.json()["status"] == "succeeded", done.text
        assert done.json()["kind"] == "analysis"
        resource = done.json()["result"]["resource"]
        fetched = await client.get(resource, headers=HEADERS)
        assert fetched.status_code == 200
        assert fetched.json()["analysis_id"] == done.json()["result"]["analysis_id"]

        history = await client.get(f"/v1/books/{JOB}/analyses", headers=HEADERS, params={"page_size": 1})
        assert len(history.json()["items"]) == 1
        assert history.json()["items"][0]["analysis_id"] == done.json()["result"]["analysis_id"]
        assert history.json()["next_page_token"]

        caps = await client.get("/v1/capabilities")
        assert caps.json()["phase"] == "4"
        assert caps.json()["renderers"] == ["json", "md"]
        assert {"run_analysis", "list_findings", "explain_finding"} <= {tool["name"] for tool in caps.json()["tools"]}
        assert any(rule["code"] == "check_failure" and rule["severity"] == "critical" for rule in caps.json()["rules"])
        assert any(item["code"] == "no_audit" for item in caps.json()["problems"])


_AXIS = re.compile(r"!r(\d+)$")
_CELL = re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+)")


def _axis(value: str | None) -> str | None:
    return value if value is None else _AXIS.sub(lambda m: f"!r{int(m.group(1)) + 1}", value)


def _cell(value: str) -> str:
    sheet, _, addr = value.rpartition("!")
    return f"{sheet}!" + _CELL.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + 1}", addr)


def _row_key(value: str | None) -> str | None:
    if value is None:
        return None
    sheet, row, block = value.split("|")
    return f"{sheet}|{int(row) + 1}|{_axis(block)}"


def _insert_row_on_every_sheet(folder) -> None:
    """Пересборка на месте: над каждой шапкой вставлена строка.

    Меняются row_key, axis_id, номера строк и адреса ячеек. Подписи и пути
    подписей те же, поэтому binding_key не меняется.
    """

    context = json.loads((folder / "context.json").read_text())
    for axis in context["axes"]:
        axis["id"] = _axis(axis["id"])
        axis["timeline_id"] = _axis(axis.get("timeline_id"))
    for block in context["blocks"]:
        block["block_id"] = _axis(block["block_id"])
        for row in block["rows"]:
            row["row"] += 1
            row["row_key"] = _row_key(row["row_key"])
            row["formula_exceptions"] = [_cell(cell) for cell in row.get("formula_exceptions") or []]
            for series in row.get("series") or []:
                series["axis_id"] = _axis(series["axis_id"])
                series["formula_exceptions"] = [_cell(cell) for cell in series.get("formula_exceptions") or []]
    graph = json.loads((folder / "graph.json").read_text())
    for link in graph["links"]:
        link["cell"] = _cell(link["cell"])
        link["refs"] = [_cell(ref) for ref in link["refs"]]
        link["row_key"] = _row_key(link.get("row_key"))
    (folder / "context.json").write_text(json.dumps(context, ensure_ascii=False))
    (folder / "graph.json").write_text(json.dumps(graph, ensure_ascii=False))


async def test_fingerprint_stable_on_rebuild_in_place(tmp_path, settings, redis_runtime):
    root = tmp_path / "builder"
    shutil.copytree(BUILDER_ROOT / RVI, root / RVI)
    store = await open_storage(settings)
    service = FasService(settings, store, PyarrowParquet(), FixtureBuilder(root), WrenQuery(settings), redis_runtime)
    app = create_app(settings, service=service, support=redis_runtime)
    async with _client(app) as client:
        first = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        assert first.status_code == 200, first.text
        old_build = first.json()["build_key"]
        old = {item["fingerprint"]: item for item in first.json()["result_data"]["findings"]}

        _insert_row_on_every_sheet(root / RVI)

        stale = await client.get(f"/v1/books/{RVI}/findings", headers=HEADERS)
        assert stale.status_code == 404, stale.text
        assert stale.json()["code"] == "no_audit"
        assert stale.json()["build_key"] != old_build
        second = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        assert second.status_code == 200, second.text
        new_build = second.json()["build_key"]
        new = {item["fingerprint"]: item for item in second.json()["result_data"]["findings"]}
        builds = await client.get(f"/v1/books/{RVI}/builds", headers=HEADERS)

    assert new_build != old_build
    assert builds.json()["items"][0]["rebuild_reason"] == "builder_rebuild"
    old_rows = {location["row_key"] for item in old.values() for location in item["locations"]} - {None}
    new_rows = {location["row_key"] for item in new.values() for location in item["locations"]} - {None}
    assert old_rows and not old_rows & new_rows
    assert {item["code"] for item in old.values()} >= {"hardcoded_formula", "missing_cached_value"}
    assert set(new) == set(old)
    for print_, item in old.items():
        assert new[print_]["code"] == item["code"]
        assert new[print_]["binding_key"] == item["binding_key"]
        assert [loc["period_id"] for loc in new[print_]["locations"]] == [loc["period_id"] for loc in item["locations"]]


async def test_projection_upgrade_rebuilds_with_same_etag(app, local_service, monkeypatch):
    """Сборка проекции 1 при неизменном ETag builder перестраивается (§4.10)."""

    monkeypatch.setattr(service_module, "FAS_PROJECTION_VERSION", "1")
    old = await local_service.perform_load(RVI, actor=Actor(), fence=1)
    monkeypatch.undo()
    # Manifest до проекции 2 не знал fas_projection_version и счётчиков R1.
    key = f"books/{RVI}/{old.build_key}/manifest.json"
    manifest = json.loads(await local_service.store.get(key))
    manifest.pop("fas_projection_version")
    manifest.pop("builder_counters")
    await local_service.store.put(key, json.dumps(manifest).encode())

    async with _client(app) as client:
        book = await client.get(f"/v1/books/{RVI}", headers=HEADERS)
        assert book.status_code == 200, book.text
        assert book.json()["build_key"] != old.build_key
        builds = await client.get(f"/v1/books/{RVI}/builds", headers=HEADERS)
        assert builds.json()["items"][0]["rebuild_reason"] == "fas_projection_upgrade"
        audit = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        assert all(item["code"] != "builder_counters_missing" for item in audit.json()["warnings"])
        assert any(item["code"] == "formula_inconsistent_in_row" for item in audit.json()["result_data"]["findings"])

        # Аудит прошлой сборки: concept-фильтр берёт привязки той сборки, а не головы.
        old_audit = await client.post(
            f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit", "build_key": old.build_key}
        )
        assert old_audit.status_code == 200, old_audit.text
        assert old_audit.json()["is_latest"] is False
        assert old_audit.json()["versions"]["derive_key"] == old.derive_key
        filtered = await client.get(
            f"/v1/books/{RVI}/findings", headers=HEADERS, params={"build_key": old.build_key, "concept": "cfads"}
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["build_key"] == old.build_key
        assert filtered.json()["items"] == []


async def test_scope_periods_concepts_and_trace_fallback(app, local_service):
    async with _client(app) as client:
        full = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        findings = full.json()["result_data"]["findings"]
        missing = [item for item in findings if item["code"] == "missing_cached_value" and item["locations"]]
        axis_id = missing[0]["locations"][0]["axis_id"]
        period_id = missing[0]["locations"][0]["period_id"]
        expected = {
            item["fingerprint"]
            for item in missing
            if (item["locations"][0]["axis_id"], item["locations"][0]["period_id"]) == (axis_id, period_id)
        }
        narrowed = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={
                "type": "audit",
                "rules": ["missing_cached_value"],
                "scope": {"axis_id": axis_id, "period_from": period_id, "period_to": period_id},
            },
        )
        assert narrowed.status_code == 200, narrowed.text
        located = {item["fingerprint"] for item in narrowed.json()["result_data"]["findings"] if item["locations"]}
        assert located == expected
        marked = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={"type": "audit", "rules": ["missing_cached_value"], "scope": {"markers": ["план"]}},
        )
        # В RVI нет периодов с маркером: из находок со ссылкой на ячейку не остаётся ни одной.
        assert all(not item["locations"] for item in marked.json()["result_data"]["findings"])

        head = (await local_service._read_head(RVI))[0]
        facts = {row["binding_key"] for row in await local_service._dataset_rows(RVI, head, "bindings")}
        chosen = next(item for item in findings if item["binding_key"] in facts)
        decided = await client.post(
            f"/v1/books/{RVI}/decisions",
            headers=HEADERS,
            json={"decisions": [{"kind": "concept.set", "target": chosen["binding_key"], "value": "debt_service"}]},
        )
        assert decided.status_code == 200, decided.text
        bound = await client.post(
            f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit", "scope": {"concepts": ["debt_service"]}}
        )
        assert bound.status_code == 200, bound.text
        kept = [item for item in bound.json()["result_data"]["findings"] if item["locations"]]
        assert kept and {item["binding_key"] for item in kept} == {chosen["binding_key"]}

        # Builder пересобирает публикацию — цепочка на один уровень по graph_links.
        local_service.builder.rebuilding.add(RVI)
        target = kept[0]["fingerprint"]
        detail = await client.get(f"/v1/books/{RVI}/findings/{target}", headers=HEADERS, params={"depth": 3})
        local_service.builder.rebuilding.discard(RVI)
        assert detail.status_code == 200, detail.text
        assert detail.json()["trace"]["source"] == "graph_links"
        assert detail.json()["trace"]["warnings"][0]["code"] == "trace_unavailable"
