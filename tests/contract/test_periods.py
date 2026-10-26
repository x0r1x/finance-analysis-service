"""Первый операционный год на книгах packt и rvi (§5.4, тест 0.23 п. 2)."""

from __future__ import annotations

from finance_analysis.domain.book import Actor
from tests.books import job_id
from tests.conftest import JOB


async def _decide(service, job: str, decisions: list[dict]) -> dict:
    result = await service.submit_decisions(job, {"decisions": decisions}, Actor(), wait_sec=60)
    assert all(item["status"] == "accepted" for item in result["results"]), result
    return result


async def _binding(service, job: str, label: str) -> str:
    head = await service.perform_load(job, actor=Actor(), fence=1)
    rows = await service._dataset_rows(job, head, "dim_row")
    found = next(row for row in rows if row["label"] == label and row["kind"] == "fact")
    return found["binding_key"]


async def test_first_operational_year_on_packt_and_rvi(local_service):
    # «Debt service» — точная pref, привязка ставится без решения человека.
    packt = await local_service.resolve_periods(JOB, {"text": "первый операционный год"}, Actor(), wait_sec=60)
    assert packt["basis"] == "nonzero_debt_service"
    assert packt["needs_input"] == []
    assert packt["periods"][0]["axis_id"] == "TBA!r2"
    assert packt["periods"][0]["period_id"] == "Y5"
    assert packt["periods"][0]["period_key"] == "Y5"

    packt_key = await _binding(local_service, JOB, "Debt service")
    await _decide(
        local_service,
        JOB,
        [{"kind": "concept.set", "target": packt_key, "value": "debt_service", "expected_seq": None}],
    )

    rvi = job_id("rvi")
    unbound = await local_service.resolve_periods(
        rvi,
        {"text": "первый операционный год"},
        Actor(),
        wait_sec=60,
    )
    assert unbound["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}
    ]
    assert all(item["kind"] != "phase" for item in unbound["needs_input"])
    rvi_key = await _binding(local_service, rvi, "Total debt service")
    await _decide(
        local_service,
        rvi,
        [{"kind": "concept.set", "target": rvi_key, "value": "debt_service", "expected_seq": None}],
    )
    resolved = await local_service.resolve_periods(
        rvi,
        {"text": "первый операционный год"},
        Actor(),
        wait_sec=60,
    )
    assert resolved["basis"] == "nonzero_debt_service"
    assert resolved["periods"][0]["period_id"] == "2026"
    assert resolved["periods"][0]["period_key"] == "2026"


async def test_phase_set_is_explicit_and_ordered(local_service):
    unknown = await local_service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "phase.set", "target": "TBA!r2+Y1", "value": "эксплуатация", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert unknown["results"][0]["status"] == "rejected"
    assert unknown["results"][0]["errors"][0]["code"] == "schema_invalid"

    accepted = await local_service.submit_decisions(
        JOB,
        {
            "decisions": [
                {"kind": "phase.set", "target": "TBA!r2+Y2", "value": "operation", "expected_seq": None},
            ]
        },
        Actor(),
        wait_sec=30,
    )
    assert accepted["results"][0]["status"] == "accepted"
    year = await local_service.resolve_periods(JOB, {"text": "первый операционный год"}, Actor(), wait_sec=30)
    assert year["basis"] == "phase_decision"
    assert year["periods"][0]["period_id"] == "Y2"
    assert year["needs_input"] == []

    broken = await local_service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "phase.set", "target": "TBA!r2+Y5", "value": "construction", "expected_seq": None}]},
        Actor(),
        wait_sec=30,
    )
    assert broken["results"][0]["status"] == "rejected"
    assert "порядок" in broken["results"][0]["errors"][0]["message"]

    head = await local_service._read_head(JOB)
    semantics = await local_service._dataset_rows(JOB, head[0], "period_semantics")
    y2 = next(row for row in semantics if row["axis_id"] == "TBA!r2" and row["period_id"] == "Y2")
    assert y2["phase"] == "operation"
    assert y2["source"] == "decision"
    assert y2["phase_year"] == 1
    flags = await local_service._dataset_rows(JOB, head[0], "dim_period")
    copied = [row for row in flags if row["period_id"] == "Y1" and row["axis_kind"] == "time"]
    assert len(copied) == 9
    assert len({row["col"] for row in copied}) > 1
