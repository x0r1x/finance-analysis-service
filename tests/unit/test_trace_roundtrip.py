"""Путь улики до объекта S3 и обратно.

Живой MinIO на порту 9000 не трогаем: фикстура репозитория его пропускает,
тома и стек остаются. Здесь moto с Object Lock, тот же приём, что у замка GOVERNANCE.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
from finance_analysis.application.trace_tail import publish_trace, read_trace_archive
from finance_analysis.domain.calculation_evidence import EvidenceBook
from finance_analysis.domain.errors import NotFound
from finance_analysis.domain.metrics import _sums, quantize_ratio
from tests.unit.test_calculation_outcome import _binding, _call, _fact, _period
from tests.unit.test_trace_tail import NOW, _labeled_facts


class _Meta:
    def __init__(self, key: str) -> None:
        self.key = key


class _MotoStore:
    def __init__(self, client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    async def put_if_absent(self, key: str, body: bytes) -> None:
        from botocore.exceptions import ClientError

        from finance_analysis.domain.errors import AlreadyExists

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body)
            return
        raise AlreadyExists(key)

    async def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise NotFound(key) from exc

    async def stat(self, key: str):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError:
            return None
        return _Meta(key)

    async def delete_prefix(self, prefix: str) -> int:
        return 0

    async def list(self, prefix: str):
        token = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            for item in page.get("Contents") or []:
                yield _Meta(item["Key"])
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")


def _labeled_evidence(alias: str, concept: str):
    facts = _labeled_facts(alias, concept)
    book = EvidenceBook(
        metric="dscr",
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    _sums(facts, {"row_key": facts[0]["row_key"]}, book=book, concept=concept)
    return book.freeze("succeeded", "dscr@1")


@pytest.mark.asyncio
async def test_packt_rvi_and_denominator_cases_roundtrip_through_s3(tmp_path):
    import boto3
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="trace-e2e", ObjectLockEnabledForBucket=True)
        store = _MotoStore(client, "trace-e2e")
        pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
        cases = {
            "ytd": _ytd(),
            "eligibility": _eligibility(),
            "zero": _zero_denominator(),
            "packt-cfads": _labeled_evidence("packt", "cfads"),
            "packt-debt": _labeled_evidence("packt", "debt_service"),
            "rvi-cfads": _labeled_evidence("rvi", "cfads"),
            "rvi-debt": _labeled_evidence("rvi", "debt_service"),
        }
        assert cases["packt-cfads"].sums_additions == 40
        assert cases["packt-debt"].sums_additions == 40
        assert cases["rvi-cfads"].sums_additions == 39
        assert cases["rvi-debt"].sums_additions == 39
        for name, evidence in cases.items():
            await publish_trace(
                store,
                pointer,
                analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                execution_id=name,
                evidence=evidence,
                retention="analysis",
                now=NOW,
            )
        ytd = await read_trace_archive(store, pointer, analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", execution_id="ytd")
        step = next(
            item
            for period in ytd["trace"]["periods"]
            if period["period_id"] == "2026Q2"
            for item in period["steps"]
            if item["operation"] == "period_restatement"
        )
        assert step["parameters"]["current_cells"] == ["Debt!Q2"]
        assert step["parameters"]["previous_cells"] == ["Debt!Q1"]
        assert step["parameters"]["current_raw"] == "250"
        assert step["parameters"]["previous_raw"] == "100"
        assert step["parameters"]["current_effective"] == "250"
        assert step["parameters"]["previous_effective"] == "100"
        assert step["parameters"]["difference"] == "150"
        assert step["parameters"]["year"] == 2026
        division = next(
            item
            for period in ytd["trace"]["periods"]
            if period["period_id"] == "2026Q2"
            for item in period["steps"]
            if item["operation"] == "division"
        )
        assert division["parameters"]["denominator"] == "150"
        eligibility = await read_trace_archive(
            store, pointer, analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", execution_id="eligibility"
        )
        uses = eligibility["trace"]["fact_uses"]
        assert {item["cell_id"] for item in uses} == {"Debt!D"}
        assert {item["operand"] for item in uses} == {"eligibility"}
        zero = await read_trace_archive(store, pointer, analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", execution_id="zero")
        zero_uses = [item for item in zero["trace"]["fact_uses"] if item["result_period_id"] == "2026"]
        assert {item["cell_id"] for item in zero_uses} == {"Debt!2026"}
        assert {item["operand"] for item in zero_uses} == {"denominator"}
        for name, additions in (
            ("packt-cfads", 40),
            ("packt-debt", 40),
            ("rvi-cfads", 39),
            ("rvi-debt", 39),
        ):
            archive = await read_trace_archive(
                store, pointer, analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAV", execution_id=name
            )
            assert archive["trace"]["sums_additions"] == additions
            assert archive["trace"]["observation_count"] == additions
            assert archive["trace"]["observation_status"] == "complete"
            assert archive["trace"]["fact_observations"][0]["raw_value"]
            stored = json.loads(
                client.get_object(Bucket="trace-e2e", Key=f"traces/01ARZ3NDEKTSV4RRFFQ69G5FAV/{name}.json")["Body"].read()
            )
            assert stored["trace"]["observation_count"] == additions


def _ytd():
    periods = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    outcome = _call(
        facts=[
            _fact("c", "2026Q1", "50"),
            _fact("c", "2026Q2", "30"),
            _fact("d", "2026Q1", "100", cell_id="Debt!Q1"),
            _fact("d", "2026Q2", "250", cell_id="Debt!Q2"),
        ],
        bindings=[
            _binding("cfads", "c"),
            _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "header"}),
        ],
        periods=periods,
    )
    assert outcome.result["rows"][1]["value"] == quantize_ratio(Decimal(30) / Decimal(150))
    return outcome.evidence


def _eligibility():
    from tests.unit.test_calculation_outcome import AXIS

    outcome = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!N"),
            _fact("d", "2025", "-4", cell_id="Debt!D"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period("2025", 0)],
        explicit_phases=True,
        period_phase={(AXIS, "2025"): "construction"},
    )
    return outcome.evidence


def _zero_denominator():
    outcome = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!2025"),
            _fact("d", "2025", "-5", cell_id="Debt!2025"),
            _fact("c", "2026", "8", cell_id="CFS!2026"),
            _fact("d", "2026", "0", cell_id="Debt!2026"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period("2025", 0), _period("2026", 1)],
    )
    return outcome.evidence
