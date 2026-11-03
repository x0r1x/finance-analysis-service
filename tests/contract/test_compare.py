"""Расчёты на прошлой сборке и `POST …:compare` двух сборок (§3.2, §6.4, §12 фаза 3)."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from tests.books import BUILDER_ROOT, job_id

pytestmark = pytest.mark.asyncio
RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
DEBT_LABEL = "Total debt service"
CHANGED_INDEX = 3


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


def _double_debt_service(folder) -> None:
    """Пересборка builder: обслуживание долга в одном периоде удвоено."""

    context = json.loads((folder / "context.json").read_text())
    for block in context["blocks"]:
        for row in block["rows"]:
            if row.get("label") != DEBT_LABEL or row.get("kind") != "fact":
                continue
            for series in row.get("series") or []:
                for name in ("values", "normalized_values"):
                    series[name][CHANGED_INDEX] = str(Decimal(series[name][CHANGED_INDEX]) * 2)
    (folder / "context.json").write_text(json.dumps(context, ensure_ascii=False))


async def _bind(service, label: str, concept: str) -> None:
    head = (await service._read_head(RVI))[0]
    rows = await service._dataset_rows(RVI, head, "dim_row")
    row = next(item for item in rows if item["label"] == label and item["kind"] == "fact")
    posted = await service.submit_decisions(
        RVI,
        {"decisions": [{"kind": "concept.set", "target": row["binding_key"], "value": concept, "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted


async def test_ratios_on_a_past_build_and_compare_two_builds(tmp_path, settings, redis_runtime):
    root = tmp_path / "builder"
    shutil.copytree(BUILDER_ROOT / RVI, root / RVI)
    store = await open_storage(settings)
    service = FasService(settings, store, PyarrowParquet(), FixtureBuilder(root), WrenQuery(settings), redis_runtime)
    await service.perform_load(RVI, actor=Actor(), fence=1)
    # cfads на этой книге неоднозначен (§5.5): для частного нужна выбранная строка.
    await _bind(service, "CFADS", "cfads")
    await _bind(service, DEBT_LABEL, "debt_service")
    # Скобка (EBITDA) делает понятие неоднозначным, а расчёт DSCR смотрит и на него.
    await _bind(service, "EBITDA", "ebitda")
    app = create_app(settings, service=service, support=redis_runtime)
    async with _client(app) as client:
        first = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "ratios", "metrics": ["dscr"]})
        assert first.status_code == 200, first.text
        old_build = first.json()["build_key"]

        _double_debt_service(root / RVI)
        second = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "ratios", "metrics": ["dscr"]})
        assert second.status_code == 200, second.text
        new_build = second.json()["build_key"]
        assert new_build != old_build

        # Новое подтверждение после пересборки: на прошлой сборке нужна свёртка на новом state_seq.
        await _bind(service, "Interest", "interest")
        head = (await service._read_head(RVI))[0]
        assert await service.analyses._derived_at(RVI, old_build, head.state_seq) is None
        past = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={"type": "ratios", "metrics": ["dscr", "dscr_min"], "build_key": old_build},
        )
        assert past.status_code == 200, past.text
        assert past.json()["build_key"] == old_build
        assert past.json()["is_latest"] is False
        assert await service.analyses._derived_at(RVI, old_build, head.state_seq) == head.derive_key
        old_rows = [row for row in past.json()["result_data"]["ratios"] if row["metric"] == "dscr" and row["value"]]
        assert old_rows

        compared = await client.post(
            f"/v1/books/{RVI}:compare",
            headers=HEADERS,
            json={"base": {"build_key": old_build}, "other": {"build_key": new_build}, "metrics": ["dscr"], "rules": ["missing_unit"]},
        )
        assert compared.status_code == 200, compared.text
        body = compared.json()
        assert body["base"]["build_key"] == old_build
        assert body["other"]["build_key"] == new_build
        moved = [row for row in body["metrics"] if row["delta_abs"] not in (None, "0")]
        assert len(moved) == 1
        assert Decimal(moved[0]["other"]) * 2 == pytest.approx(Decimal(moved[0]["base"]), abs=Decimal("0.0000001"))
        debt = [row for row in body["concepts"] if row["concept"] == "debt_service"]
        assert len(debt) == 1 and debt[0]["period_id"] == moved[0]["period_id"]
        assert body["structure"]["rows_added"] == [] and body["structure"]["bindings_changed"] == []
        assert body["findings"]["added"] == [] and body["findings"]["removed"] == []

        later = await client.post(
            f"/v1/books/{RVI}:compare", headers=HEADERS, json={"other": {"job_id": RVI, "build_key": old_build}}
        )
        assert later.status_code == 200, later.text
        assert later.json()["other"]["build_key"] == old_build
        assert later.json()["base"]["build_key"] == new_build
        assert later.json()["metrics"]
        same = await client.post(f"/v1/books/{RVI}:compare", headers=HEADERS, json={"other": {"build_key": new_build}})
        assert same.status_code == 400, same.text
