"""DSCR и ICR на книге RVI (§12 п. 1–2)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor
from finance_analysis.domain.metrics import _payment, quantize_ratio
from tests.books import job_id

pytestmark = pytest.mark.asyncio
RVI = job_id("rvi")


def _number(facts: list[dict], row_key: str, axis: str, period: str) -> Decimal | None:
    for fact in facts:
        if fact.get("row_key") != row_key or fact.get("axis_id") != axis or fact.get("period_id") != period:
            continue
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None:
            return None
        return Decimal(str(number))
    return None


async def _ratios(service, metrics: list[str]) -> dict:
    result = await service.analyses.run(RVI, {"type": "ratios", "metrics": metrics}, Actor(), wait_sec=120)
    if not isinstance(result, Accepted):
        return result
    operation = await service.wait_op(result.operation["id"], 120_000)
    assert operation["status"] == "succeeded", operation
    analysis_id = operation["result"]["analysis_id"]
    head = (await service._read_head(RVI))[0]
    marker = json.loads(await service.store.get(f"books/{RVI}/{head.build_key}/results/{analysis_id}/result.json"))
    return marker["result"]


async def _row(service, label: str) -> dict:
    head = (await service._read_head(RVI))[0]
    rows = await service._dataset_rows(RVI, head, "dim_row")
    return next(row for row in rows if row["label"] == label and row["kind"] == "fact")


async def test_rvi_dscr_quotient_and_icr(local_service):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    missing = await _ratios(local_service, ["dscr"])
    assert missing["needs_input"][0]["reason"] == "concept_unknown"
    assert all(row.get("value") is None for row in missing["result_data"]["ratios"])

    debt = await _row(local_service, "Total debt service")
    decided = await local_service.submit_decisions(
        RVI,
        {"decisions": [{"kind": "concept.set", "target": debt["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert decided["results"][0]["status"] == "accepted", decided
    got = await _ratios(local_service, ["dscr"])
    rows = [row for row in got["result_data"]["ratios"] if row.get("value") is not None]
    assert rows
    head = (await local_service._read_head(RVI))[0]
    facts = await local_service._dataset_rows(RVI, head, "fact_observation")
    bindings = await local_service._dataset_rows(RVI, head, "bindings")
    cfads = next(row for row in bindings if row.get("effective_concept") == "cfads" and row.get("is_primary"))
    debt_binding = next(row for row in bindings if row.get("effective_concept") == "debt_service" and row.get("is_primary"))
    model = await _row(local_service, "DSCR Metrics")
    cached = [
        fact
        for fact in facts
        if fact.get("row_key") == model["row_key"] and _number(facts, model["row_key"], fact["axis_id"], fact["period_id"]) is not None
    ]
    compared = 0
    for row in rows:
        num = _number(facts, cfads["row_key"], row["axis_id"], row["period_id"])
        den = _number(facts, debt_binding["row_key"], row["axis_id"], row["period_id"])
        assert num is not None and den is not None
        assert Decimal(row["value"]) == quantize_ratio(num / _payment(den, "outflow_negative"))
        model_value = _number(facts, model["row_key"], row["axis_id"], row["period_id"])
        if model_value is not None:
            assert abs(Decimal(row["value"]) - model_value) <= Decimal("0.005")
            compared += 1
    # Кэш строки «DSCR Metrics» в фикстуре пустой. Формула строки — частное двух соседей.
    if cached:
        assert compared
    else:
        assert "/" in (model.get("formula") or "")

    interest = await _row(local_service, "Interest")
    posted = await local_service.submit_decisions(
        RVI,
        {"decisions": [{"kind": "concept.set", "target": interest["binding_key"], "value": "interest", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted
    icr = await _ratios(local_service, ["icr"])
    assert any(item["code"] == "icr_numerator" for item in icr["warnings"])
    assert any(row.get("value") is not None for row in icr["result_data"]["ratios"])
