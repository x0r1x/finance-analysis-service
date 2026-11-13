"""Тип модели на книгах Packt и RVI и запись model_type.set."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor, question_digest
from finance_analysis.domain.cover_metrics import METRIC_INPUTS
from finance_analysis.domain.model_type import asks_for, decision_labels
from tests.books import job_id

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
PACKT = job_id("packt")
RVI = job_id("rvi")
# Счётчики fact-строк: связанные, неоднозначные, неизвестные и неприменимые.
# У Packt роль reference снимает ничьи interest и principal, поэтому связанных строк 9, а неоднозначных 2.
# У RVI «Merchant price (real)» и «Merchant price (nominal)» — точные метки
# forecast_energy_tariff с разной основой цены. Обе строки bound, ни одна не основная.
# Mid case, Low case и Applied (real terms) под заголовком
# Electricity price forecast (real terms) связаны по заголовку и тоже не основные.
# Ожидаемый инвариант: Packt 9/2/82, RVI 10/6/213.
# 5/6/218 — счёт RVI на main после решения 42, не текущий инвариант.
_COUNTS = {
    "packt": {"bound": 9, "ambiguous": 2, "unknown": 82, "not_applicable": 4},
    "rvi": {"bound": 10, "ambiguous": 6, "unknown": 213, "not_applicable": 9},
}
# Неизвестные и неоднозначные строки минус входы метрик, которые тип модели не спрашивает.
_OPEN = {"packt": 84, "rvi": 216}
# У Packt interest уже основная строка. У RVI три неоднозначные строки interest остаются.
_DROPPED = {"packt": (0, []), "rvi": (3, ["interest"])}
# У Packt interest связан, поэтому ICR считается. LLCR и PLCR по-прежнему пропущены.
_SKIPPED = {"packt": ["llcr", "plcr"], "rvi": ["icr", "icr_ebit", "llcr", "plcr"]}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def _fact_counts(service, job: str) -> dict[str, int]:
    head = (await service._read_head(job))[0]
    rows = await service._dataset_rows(job, head, "dim_row")
    bindings = await service._dataset_rows(job, head, "bindings")
    facts = {row["binding_key"] for row in rows if row.get("kind") == "fact" and row.get("binding_key")}
    counts: dict[str, int] = {}
    for item in bindings:
        if item.get("binding_key") not in facts:
            continue
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


async def _ratios(service, job: str) -> dict:
    result = await service.analyses.run(job, {"type": "ratios", "metrics": list(RATIO_METRICS)}, Actor(), wait_sec=120)
    if not isinstance(result, Accepted):
        return result
    operation = await service.wait_op(result.operation["id"], 120_000)
    assert operation["status"] == "succeeded", operation
    analysis_id = operation["result"]["analysis_id"]
    head = (await service._read_head(job))[0]
    marker = json.loads(await service.store.get(f"books/{job}/{head.build_key}/results/{analysis_id}/result.json"))
    return marker["result"]


async def test_packt_and_rvi_are_project_finance(local_service):
    """CFADS и debt service дают project_finance. Счётчики привязок не хуже среза глоссария."""

    for alias, job in (("packt", PACKT), ("rvi", RVI)):
        await local_service.perform_load(job, actor=Actor(), fence=1)
        head = (await local_service._read_head(job))[0]
        verdict = await local_service.resolve_model_type(job, head)
        assert verdict.primary == "project_finance" and verdict.source == "inferred", alias
        assert verdict.scores["project_finance"] >= 0.6
        counts = await _fact_counts(local_service, job)
        assert {key: counts.get(key, 0) for key in _COUNTS[alias]} == _COUNTS[alias], counts
        mapped = await local_service.mapping_view(job, Actor(), wait_sec=30)
        assert not isinstance(mapped, Accepted)
        labels = decision_labels(verdict)
        dropped = [
            row
            for row in mapped["rows"]
            if row.get("status") in {"unknown", "ambiguous"}
            and row.get("source") != "confirmed"
            and (users := METRIC_INPUTS.get(row.get("effective_concept"))) is not None
            and not asks_for(tuple(users), local_service.model_types, labels)
        ]
        asked = await local_service.questions_view(job, Actor(), wait_sec=30)
        assert not isinstance(asked, Accepted)
        assert all(item["kind"] != "model_type" for item in asked["questions"])
        subjects = [item["subject"] for item in asked["questions"]]
        # cfads и debt_service уже привязаны: обязательных открытых понятий нет.
        assert subjects == []
        pool = [
            row
            for row in mapped["rows"]
            if row.get("status") in {"unknown", "ambiguous"} and row.get("source") != "confirmed"
        ]
        # Пакет вопросов: неизвестные и неоднозначные минус необязательные входы метрик.
        before = len(pool) - len(dropped)
        assert (alias, before, len(subjects)) == (alias, _OPEN[alias], 0)
        ratios = await _ratios(local_service, job)
        hidden = sorted(
            item["metric"] for item in ratios["result_data"]["metrics"] if item["applicability"] == "not_applicable"
        )
        # Новые метрики среза 2 на project_finance не считаются. Вопросы и привязки из-за них не меняются.
        assert hidden == ["escrow_coverage", "irr", "net_debt_ebitda", "npv"], alias
        assert ratios["model_type"]["primary"] == "project_finance"
        assert "book_rows" not in ratios["result_data"], alias
        assert ratios["versions"]["model_types"] == local_service.model_types.version
        concepts = sorted({row.get("effective_concept") for row in dropped})
        skipped = [item["metric"] for item in ratios["result_data"]["metrics"] if item.get("skipped")]
        assert (len(dropped), concepts) == _DROPPED[alias], alias
        assert skipped == _SKIPPED[alias], alias


async def test_model_type_set_needs_confirm_then_keeps_history(local_service):
    await local_service.perform_load(PACKT, actor=Actor(), fence=1)
    corporate = {"labels": ["corporate"], "primary": "corporate"}
    denied = await local_service.submit_decisions(
        PACKT,
        {"decisions": [{"kind": "model_type.set", "target": "book", "value": corporate, "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert denied["results"][0]["status"] == "needs_confirm", denied
    assert denied["results"][0]["warnings"][0]["code"] == "model_type_contradicts_signals"
    accepted = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "model_type.set",
                    "target": "book",
                    "value": corporate,
                    "expected_seq": None,
                    "confirm": True,
                    "warnings_ack": ["model_type_contradicts_signals"],
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert accepted["results"][0]["status"] == "accepted", accepted
    seq = accepted["results"][0]["record_seq"]
    again = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "model_type.set",
                    "target": "book",
                    "value": {"labels": ["project_finance"], "primary": "project_finance"},
                    "expected_seq": None,
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert again["results"][0]["status"] == "rejected", again
    assert again["results"][0]["errors"][0]["code"] == "supersede_required"
    restored = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "model_type.set",
                    "target": "book",
                    "value": {"labels": ["project_finance"], "primary": "project_finance"},
                    "expected_seq": seq,
                    "supersedes": {"seq": seq},
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert restored["results"][0]["status"] == "accepted", restored
    listed = await local_service.list_decisions(PACKT)
    types = [item for item in listed["items"] if item.get("type") == "model_type.set"]
    assert [item["value"]["primary"] for item in types] == ["corporate", "project_finance"]
    head = (await local_service._read_head(PACKT))[0]
    verdict = await local_service.resolve_model_type(PACKT, head)
    assert verdict.source == "confirmed" and verdict.primary == "project_finance"


async def test_profile_model_type_default_has_no_numbers(app):
    async with _client(app) as client:
        numbered = await client.put(
            "/v1/profiles/desk",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"model_type_default": {"labels": ["corporate"], "primary": "corporate", "score": 0.9}},
        )
        assert numbered.status_code == 400, numbered.text
        numbered_definition = await client.put(
            "/v1/profiles/desk",
            headers={**HEADERS, "If-None-Match": "*"},
            json={
                "dscr_definition": {
                    "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes"]},
                    "denominator": {"plus": ["interest"]},
                    "window": "LTM",
                    "threshold": 1.2,
                }
            },
        )
        assert numbered_definition.status_code == 400, numbered_definition.text
        definition = {
            "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes", "capex"]},
            "denominator": {"plus": ["interest", "principal"]},
            "window": "LTM",
            "basis_ref": "кредитный договор, п. 4.2",
        }
        created = await client.put(
            "/v1/profiles/desk",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"model_type_default": {"labels": ["corporate"], "primary": "corporate"}, "dscr_definition": definition},
        )
        assert created.status_code == 200, created.text
        body = await client.get("/v1/profiles/desk", headers=HEADERS)
        assert body.status_code == 200, body.text
        assert body.json()["body"]["model_type_default"] == {"labels": ["corporate"], "primary": "corporate"}
        assert body.json()["body"]["dscr_definition"] == definition


async def test_concept_answer_keeps_question_id_and_binds_the_row(local_service):
    """Ответ на вопрос понятия привязывает строку и остаётся в журнале с question_id."""

    await local_service.perform_load(PACKT, actor=Actor(), fence=1)
    head = (await local_service._read_head(PACKT))[0]
    bindings = await local_service._dataset_rows(PACKT, head, "bindings")
    unknown = [row for row in bindings if row.get("status") == "unknown" and row.get("binding_key")]
    assert len(unknown) >= 2
    target, other = unknown[0], unknown[1]
    digest = question_digest("concept", "capex", PACKT)
    denied = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "concept.set",
                    "target": target["binding_key"],
                    "value": "capex",
                    "expected_seq": None,
                    "question_id": "0" * 40,
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert denied["results"][0]["status"] == "rejected", denied
    assert denied["results"][0]["errors"][0]["code"] == "schema_invalid"
    accepted = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "concept.set",
                    "target": target["binding_key"],
                    "value": "capex",
                    "expected_seq": None,
                    "question_id": digest,
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert accepted["results"][0]["status"] == "accepted", accepted
    assert accepted["results"][0]["question_id"] == digest
    listed = await local_service.list_decisions(PACKT)
    recorded = [item for item in listed["items"] if item.get("type") == "concept.set"]
    assert recorded[-1]["question_id"] == digest
    assert recorded[-1]["value"] == "capex"
    mapped = await local_service.mapping_view(PACKT, Actor(), wait_sec=30)
    assert not isinstance(mapped, Accepted)
    bound = next(row for row in mapped["rows"] if row["binding_key"] == target["binding_key"])
    assert bound["status"] == "bound" and bound["effective_concept"] == "capex"
    reject_id = question_digest("concept", "ebitda", PACKT)
    rejected = await local_service.submit_decisions(
        PACKT,
        {
            "decisions": [
                {
                    "kind": "concept.reject",
                    "target": other["binding_key"],
                    "value": "ebitda",
                    "expected_seq": None,
                    "question_id": reject_id,
                }
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert rejected["results"][0]["status"] == "accepted", rejected
    listed = await local_service.list_decisions(PACKT)
    reject_row = next(item for item in listed["items"] if item.get("type") == "concept.rejected")
    assert reject_row["question_id"] == reject_id
    mapped = await local_service.mapping_view(PACKT, Actor(), wait_sec=30)
    left = next(row for row in mapped["rows"] if row["binding_key"] == other["binding_key"])
    assert left["status"] == "unknown"
