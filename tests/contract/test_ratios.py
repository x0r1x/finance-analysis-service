"""DSCR, ICR и их свёртки на книге RVI (§12 фазы 2–3)."""

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


async def _set(service, decisions: list[dict]) -> None:
    decided = await service.submit_decisions(RVI, {"decisions": decisions}, Actor(), wait_sec=60)
    assert [item["status"] for item in decided["results"]] == ["accepted"] * len(decisions), decided


def _concept(row: dict, concept: str) -> dict:
    return {"kind": "concept.set", "target": row["binding_key"], "value": concept, "expected_seq": None}


async def test_rvi_dscr_quotient_and_icr(local_service):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    cash = await _row(local_service, "CFADS")
    debt = await _row(local_service, "Total debt service")
    ebitda = await _row(local_service, "EBITDA")
    await _set(
        local_service,
        [_concept(cash, "cfads"), _concept(debt, "debt_service"), _concept(ebitda, "ebitda")],
    )
    got = await _ratios(local_service, ["dscr"])
    rows = [row for row in got["result_data"]["ratios"] if row.get("value") is not None]
    assert rows
    head = (await local_service._read_head(RVI))[0]
    facts = await local_service._dataset_rows(RVI, head, "fact_observation")
    bindings = await local_service._dataset_rows(RVI, head, "bindings")
    cfads = next(row for row in bindings if row.get("effective_concept") == "cfads" and row.get("is_primary"))
    debt_binding = next(row for row in bindings if row.get("effective_concept") == "debt_service" and row.get("is_primary"))
    cited = {item["cell_id"]: item for item in got["citations"]}
    for row in rows:
        assert row["cell_ids"], row
        assert {cited[cell]["row_key"] for cell in row["cell_ids"]} == {cfads["row_key"], debt_binding["row_key"]}
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


def _first_value(facts: list[dict], row_key: str) -> Decimal:
    ordered = sorted((fact for fact in facts if fact.get("row_key") == row_key), key=lambda fact: fact["period_id"])
    return Decimal(str(ordered[0]["normalized_value"]))


async def test_rvi_min_and_average_dscr_match_the_model_summary(local_service):
    """Re-performance (§12 фаза 3): min и среднее DSCR FAS = сводка Live-кейса книги."""

    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    cash = await _row(local_service, "CFADS")
    debt = await _row(local_service, "Total debt service")
    ebitda = await _row(local_service, "EBITDA")
    await _set(
        local_service,
        [_concept(cash, "cfads"), _concept(debt, "debt_service"), _concept(ebitda, "ebitda")],
    )
    got = await _ratios(local_service, ["dscr_min", "dscr_avg", "llcr", "adscr"])
    rows = got["result_data"]["ratios"]
    head = (await local_service._read_head(RVI))[0]
    facts = await local_service._dataset_rows(RVI, head, "fact_observation")
    lowest = next(row for row in rows if row["metric"] == "dscr_min")
    model_min = _first_value(facts, (await _row(local_service, "Minimum Debt Service Coverage Ratio (DSCR)"))["row_key"])
    assert abs(Decimal(lowest["value"]) - model_min) <= Decimal("0.005")
    mean = next(row for row in rows if row["metric"] == "dscr_avg" and row["variant"] == "mean_of_ratios")
    model_avg = _first_value(facts, (await _row(local_service, "Average Debt Service Coverage Ratio (DSCR)"))["row_key"])
    assert abs(Decimal(mean["value"]) - model_avg) <= Decimal("0.005")
    assert any(row["metric"] == "dscr_avg" and row["variant"] == "ratio_of_sums" for row in rows)
    # Годовая книга: ADSCR не отдаётся. LLCR необязателен для project_finance: нет входа — пропуск, без вопроса.
    assert any(item["code"] == "adscr_not_applicable" for item in got["warnings"])
    assert not any(row["metric"] in {"adscr", "llcr"} for row in rows)
    assert got["needs_input"] == []
    skipped = [item for item in got["result_data"]["metrics"] if item["metric"] == "llcr"]
    assert skipped == [{"metric": "llcr", "applicability": "optional", "skipped": "input_absent"}]


async def test_concept_absent_gives_absent_in_book_and_missing_total_row(local_service):
    """`concept.absent` (§5.10.5): FAS не переспрашивает, метрика — missing_input, находка missing_total_row."""

    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    cash = await _row(local_service, "CFADS")
    debt = await _row(local_service, "Total debt service")
    await _set(
        local_service,
        [
            _concept(cash, "cfads"),
            _concept(debt, "debt_service"),
            {"kind": "concept.absent", "target": "book", "value": "debt_outstanding", "expected_seq": None},
        ],
    )
    got = await _ratios(local_service, ["llcr"])
    assert got["needs_input"] == []
    assert got["result_data"]["ratios"] == []
    assert any(item["code"] == "input_absent" and item["params"]["metric"] == "llcr" for item in got["warnings"])
    missing = [item for item in got["result_data"]["findings"] if item["code"] == "missing_total_row"]
    assert [item["params"]["concept"] for item in missing] == ["debt_outstanding"]
    assert "llcr" in missing[0]["params"]["needed_by"]


async def test_required_concept_absent_still_asks(local_service):
    """Обязательный вход DSCR с `concept.absent` остаётся вопросом."""

    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    debt = await _row(local_service, "Total debt service")
    await _set(
        local_service,
        [
            _concept(debt, "debt_service"),
            {"kind": "concept.absent", "target": "book", "value": "cfads", "expected_seq": None},
        ],
    )
    got = await _ratios(local_service, ["dscr"])
    assert {"kind": "concept", "reason": "absent_in_book", "subject": "cfads"} in got["needs_input"]
