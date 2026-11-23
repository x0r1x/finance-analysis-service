"""PR B2: execute_rules, источник прогона и служебное подтверждение.

Отпечаток находки снят до перевода вызывающих. След пишется объектом,
не полем result_data. compare следы не публикует.
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import anyio
import pytest

import tests.unit.test_calculation_outcome as calc
import tests.unit.test_ratio_math as ratio
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
from finance_analysis.application.analyses import Analyses, Target
from finance_analysis.application.compare import Comparisons
from finance_analysis.application.journal import Journal
from finance_analysis.application.rule_engine import execute_rules
from finance_analysis.domain.actor import classify_actor
from finance_analysis.domain.audit import AuditInput, Rule, RuleRunResult
from finance_analysis.domain.book import Actor, Head
from finance_analysis.domain.calculation_evidence import EvidenceBook
from finance_analysis.domain.mapping import _HUMAN, _decisions, _one
from finance_analysis.domain.metrics import HUMAN_SOURCES
from finance_analysis.domain.semantic_input import _visible
from finance_analysis.plugins.rules.coverage import (
    PERIOD_GRAIN_MISMATCH,
    SCULPTING_DEVIATION,
)
from finance_analysis.plugins.rules.ratios import (
    ICR_REFERENCE,
    RATIO_MISMATCH,
    STATEMENT_REFERENCE,
)
from finance_analysis.settings import Settings

BEFORE_STATEMENT = "4e29b030a6d9948cc8bf7e1525c4fafc87ba44f6"
BEFORE_RATIO = "54f693a5058fd05e2920e38faa86a3b5d1a2ad74"
_ACTOR_KEYS = ("actor_type", "actor_id", "confirmation_kind", "binding_key", "state_seq")


def _echo(code: str = "echo") -> Rule:
    class _Echo(Rule):
        def check(self, data: AuditInput) -> list:
            return [self.finding(data, subject="book", params={"n": 1})]

    return _Echo(code, "1", "qualitative", "low", ("test",), "echo", frozenset())


def _dscr_book() -> AuditInput:
    facts = [
        calc._fact("c", "2025", "10", cell_id="CFS!N"),
        calc._fact("d", "2025", "-1", cell_id="Debt!A"),
        calc._fact("d", "2025", "-2", cell_id="Debt!B"),
        calc._fact("m", "2025", "9", cell_id="Model!D"),
    ]
    bindings = [calc._binding("cfads", "c"), calc._binding("debt_service", "d"), calc._binding("dscr", "m")]
    return AuditInput(
        facts=facts,
        bindings=bindings,
        periods=[calc._period("2025", 0)],
        rows=[{"row_key": key, "binding_key": key} for key in ("c", "d", "m")],
        plans={"icr": object()},
    )


def _evidence(metric: str, implementation: str, additions: int) -> object:
    book = EvidenceBook(
        metric=metric,
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    book.sums_additions = additions
    return book.freeze("succeeded", implementation)


def test_execute_rules_returns_findings_and_is_not_a_list():
    data = AuditInput()
    result = execute_rules([_echo()], data)
    assert isinstance(result, RuleRunResult)
    assert isinstance(result.findings, tuple)
    assert result.findings[0].params == {"n": 1}
    assert next(iter(result.findings)).fingerprint == result.findings[0].fingerprint
    with pytest.raises(TypeError):
        iter(result)
    with pytest.raises(TypeError):
        list(result)


def test_run_rules_is_gone():
    import finance_analysis.application.rule_engine as engine

    assert not hasattr(engine, "run_rules")


def test_statement_fingerprint_matches_the_run_before_the_move():
    rows = [
        {"row_key": "model", "binding_key": "model", "scale_factor": "тыс."},
        {"row_key": "form", "binding_key": "form"},
    ]
    bindings = [
        ratio._binding("revenue", "model"),
        ratio._binding("revenue", "form", is_primary=False, evidence={"role": "reference"}),
    ]
    data = AuditInput(
        rows=rows,
        periods=[ratio._quarter("q1", 1)],
        facts=[{**ratio._fact("model", "100", "q1"), "scale_factor": "1 000"}, ratio._fact("form", "110", "q1")],
        bindings=bindings,
        actuals_end="q1",
        plans={"dscr": object()},
    )
    result = execute_rules([STATEMENT_REFERENCE], data)
    assert result.calculation_evidence == ()
    assert result.sources == ()
    assert result.findings[0].fingerprint == BEFORE_STATEMENT
    assert result.findings[0].params["model"] == "100"
    assert result.findings[0].params["reported"] == "110"
    assert "evidence" not in result.findings[0].params


def test_ratio_mismatch_keeps_the_finding_and_keeps_the_evidence():
    data = _dscr_book()
    result = execute_rules([RATIO_MISMATCH], data)
    assert len(result.findings) == 1
    assert result.findings[0].fingerprint == BEFORE_RATIO
    assert result.findings[0].params == {"metric": "dscr", "fas": "3.3333333333", "model": "9"}
    assert result.sources == ("rule:ratio_mismatch",)
    assert result.calculation_evidence[0].metric == "dscr"
    assert result.calculation_evidence[0].implementation == "dscr@1"


def test_a_plan_alone_does_not_make_rule_evidence():
    data = AuditInput(plans={"dscr": SimpleNamespace(inputs=()), "icr": SimpleNamespace(inputs=())})
    result = execute_rules([RATIO_MISMATCH, ICR_REFERENCE, SCULPTING_DEVIATION, PERIOD_GRAIN_MISMATCH], data)
    assert result.findings == ()
    assert result.calculation_evidence == ()


def test_icr_and_sculpting_and_period_grain_record_their_own_runs():
    facts = [
        calc._fact("e", "2025", "10", cell_id="E!1"),
        calc._fact("i", "2025", "-2", cell_id="I!1"),
        calc._fact("c", "2025", "10", cell_id="CFS!N"),
        calc._fact("d", "2025", "-1", cell_id="Debt!A"),
        calc._fact("d", "2025", "-2", cell_id="Debt!B"),
    ]
    bindings = [
        calc._binding("ebitda", "e"),
        calc._binding("interest", "i"),
        calc._binding("cfads", "c"),
        calc._binding("debt_service", "d"),
    ]
    data = AuditInput(
        facts=facts,
        bindings=bindings,
        periods=[calc._period("2025", 0)],
        rows=[{"row_key": key, "binding_key": key} for key in ("e", "i", "c", "d")],
    )
    icr = execute_rules([ICR_REFERENCE], data)
    sculpt = execute_rules([SCULPTING_DEVIATION], data)
    grain = execute_rules([PERIOD_GRAIN_MISMATCH], data)
    assert icr.sources == ("rule:icr_reference",)
    assert icr.calculation_evidence[0].metric == "icr"
    assert sculpt.sources == ("rule:sculpting_deviation",)
    assert sculpt.calculation_evidence[0].metric == "dscr"
    assert grain.sources == ("rule:period_grain_mismatch",)
    assert grain.calculation_evidence[0].metric == "dscr"
    assert sculpt.findings == ()
    assert grain.findings == ()


def test_four_call_sites_read_the_findings_field():
    from finance_analysis.application import analyses, compare

    pairs = (
        (analyses.Analyses._execute, "audit"),
        (analyses.Analyses._execute_full, "full"),
        (analyses.Analyses._metric_findings, "ratios"),
        (compare.Comparisons._finding_deltas, "compare"),
    )
    for method, _name in pairs:
        text = inspect.getsource(method)
        assert "execute_rules" in text
        assert ".findings" in text
        assert "run_rules" not in text
    compare_text = inspect.getsource(compare.Comparisons._finding_deltas)
    assert "_publish_traces" not in compare_text
    assert "publish_trace" not in compare_text
    assert "calculation_traces" not in compare_text


def _target() -> Target:
    head = Head(build_key="build", state_seq=7, derive_key="derive", versions={})
    return Target(head=head, build="build", manifest={}, fresh=False)


def _analyses(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    service = SimpleNamespace(
        store=store,
        trace_pointer=pointer,
        trace_retainer=None,
        settings=Settings(_env_file=None),
        model_types=SimpleNamespace(metric_expressions={}, interest_order={}, row_fallbacks={}, version="e5e47aa50edf3a3e"),
        financial_catalog=SimpleNamespace(version="e5e47aa50edf3a3e"),
        _cpu=anyio.CapacityLimiter(2),
    )
    analyses = Analyses(service)
    return analyses, store, pointer


def _actor_fields(trace: dict) -> dict:
    return {key: trace[key] for key in _ACTOR_KEYS}


def _nested_actor(trace: dict) -> list[str]:
    found = []

    def walk(node, place: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _ACTOR_KEYS or key == "user_id":
                    found.append(f"{place}.{key}")
                walk(value, f"{place}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{place}[{index}]")

    for pocket in ("periods", "fact_uses", "fact_observations"):
        walk(trace.get(pocket), pocket)
    return found


async def test_audit_writes_execution_source_and_not_a_plan(tmp_path, monkeypatch):
    analyses, _store, pointer = _analyses(tmp_path)
    monkeypatch.setattr("finance_analysis.application.analyses.plans_for", lambda *args, **kwargs: {"dscr": object()})

    async def _input(job_id, target, needed):
        return AuditInput(bindings=[{"binding_key": "row", "source": "confirmed", "effective_concept": "cfads"}])

    async def _quiet(envelope):
        return None

    saved = {}

    async def _save(*args):
        saved["envelope"] = args[5]

    analyses._input = _input
    analyses._annotate = _quiet
    analyses._save = _save
    analyses._formula_origin = lambda data, findings: {}
    rule = _echo("formula_pattern_break")
    await analyses._execute("job", _target(), "01ARZ3NDEKTSV4RRFFQ69G5FAV", [rule], {}, [], Actor(user_id="ada", client_id="desk"))
    assert pointer.list_all() == []
    assert "calculation_traces" not in saved["envelope"]["result_data"]
    assert saved["envelope"]["result_data"]["findings"][0]["fingerprint"] == rule.check(AuditInput())[0].fingerprint

    evidence = _evidence("dscr", "dscr@1", 4)

    class _Calc(Rule):
        def check(self, data: AuditInput) -> list:
            return [self.finding(data, subject="cache", params={"metric": "dscr"})]

        def run(self, data: AuditInput) -> RuleRunResult:
            return RuleRunResult(tuple(self.check(data)), (evidence,))

    calc_rule = _Calc("ratio_mismatch", "1", "quantitative", "high", ("test",), "calc", frozenset())
    await analyses._execute("job", _target(), "01ARZ3NDEKTSV4RRFFQ69G5FAW", [calc_rule], {}, [], Actor(user_id="ada", client_id="desk"))
    rows = pointer.list_analysis("01ARZ3NDEKTSV4RRFFQ69G5FAW")
    assert len(rows) == 1
    payload = json.loads(await analyses.store.get(rows[0]["object_key"]))
    trace = payload["trace"]
    assert trace["execution_source"] == "rule:ratio_mismatch"
    assert rows[0]["execution_id"] == "rule:ratio_mismatch:dscr-0"
    assert trace["sums_additions"] == 4
    assert _actor_fields(trace) == {
        "actor_type": "human",
        "actor_id": "ada",
        "confirmation_kind": "human_confirmed",
        "binding_key": "row",
        "state_seq": 7,
    }
    assert "user_id" not in trace
    assert _nested_actor(trace) == []
    assert "calculation_traces" not in saved["envelope"]["result_data"]


async def test_full_keeps_two_dscr_runs_apart(tmp_path, monkeypatch):
    analyses, _store, pointer = _analyses(tmp_path)
    metric = _evidence("dscr", "dscr@1", 7)
    ruled = _evidence("dscr", "dscr@1", 11)

    class _Calc(Rule):
        def check(self, data: AuditInput) -> list:
            return []

        def run(self, data: AuditInput) -> RuleRunResult:
            return RuleRunResult((), (ruled,))

    calc_rule = _Calc("ratio_mismatch", "1", "quantitative", "high", ("test",), "calc", frozenset())

    async def _input(job_id, target, needed):
        return AuditInput()

    async def _metrics(job_id, target, metrics):
        return {
            "rows": [],
            "needs_input": [],
            "warnings": [],
            "bindings": [{"binding_key": "auto", "source": "auto_confirmed"}],
            "facts": [],
            "periods": [],
            "absent": frozenset(),
            "evidences": [metric],
            "applicability": [],
            "plans": {},
            "model_type": "project_finance",
        }

    async def _quiet(*args, **kwargs):
        return None

    analyses._input = _input
    analyses.compute_metrics = _metrics
    analyses._trace_plans = lambda data, metrics: None
    analyses._formula_origin = lambda data, findings: {}
    analyses._annotate = _quiet
    analyses._save_tables = _quiet
    monkeypatch.setattr(
        "finance_analysis.application.analyses.select_rules",
        lambda registry, codes: [calc_rule],
    )
    await analyses._execute_full(
        "job",
        _target(),
        "01ARZ3NDEKTSV4RRFFQ69G5FAX",
        ["dscr"],
        None,
        {},
        Actor(user_id="system", client_id="fas"),
        "",
    )
    rows = {row["execution_id"]: row for row in pointer.list_analysis("01ARZ3NDEKTSV4RRFFQ69G5FAX")}
    assert set(rows) == {"dscr-0", "rule:ratio_mismatch:dscr-0"}
    full = json.loads(await analyses.store.get(rows["dscr-0"]["object_key"]))["trace"]
    rule = json.loads(await analyses.store.get(rows["rule:ratio_mismatch:dscr-0"]["object_key"]))["trace"]
    assert full["execution_source"] == "full"
    assert rule["execution_source"] == "rule:ratio_mismatch"
    assert full["sums_additions"] == 7
    assert rule["sums_additions"] == 11
    assert full["actor_type"] == "service"
    assert full["actor_id"] == "fas"
    assert full["confirmation_kind"] == "auto_confirmed"
    assert full["state_seq"] == 7
    assert "user_id" not in full
    assert _nested_actor(full) == []
    assert _nested_actor(rule) == []


async def test_compare_reads_findings_and_does_not_publish(tmp_path):
    analyses, _store, pointer = _analyses(tmp_path)

    async def _input(job_id, target, needed):
        return AuditInput()

    analyses._input = _input
    compared = Comparisons(analyses)
    rule = _echo()
    delta = await compared._finding_deltas("a" * 64, "b" * 64, _target(), _target(), [rule])
    assert delta["unchanged"] == 1
    assert delta["added"] == []
    assert delta["removed"] == []
    assert pointer.list_all() == []


async def test_ratios_publishes_the_period_grain_run(tmp_path):
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.model_type import Effective

    analyses, _store, pointer = _analyses(tmp_path)
    analyses.service.model_types = load_model_types()
    verdict = Effective(
        labels=("project_finance",),
        primary="project_finance",
        source="confirmed",
        reason=None,
        seq=1,
        profile_version=None,
        score=1.0,
        scores={"project_finance": 1.0},
        candidates=(),
    )

    async def _resolve(job_id, head):
        return verdict

    async def _rows(job_id, head, name):
        return [{"row_key": key, "binding_key": key} for key in ("c", "d")]

    async def _composed(version):
        return {}

    analyses.service.resolve_model_type = _resolve
    analyses.service._dataset_rows = _rows
    analyses.service.glossary = SimpleNamespace(composed_of=_composed)
    facts = [
        calc._fact("c", "2025", "10", cell_id="CFS!N"),
        calc._fact("d", "2025", "-1", cell_id="Debt!A"),
        calc._fact("d", "2025", "-2", cell_id="Debt!B"),
    ]
    bindings = [calc._binding("cfads", "c"), calc._binding("debt_service", "d")]
    await analyses._metric_findings(
        "job",
        _target(),
        ["dscr"],
        bindings,
        facts,
        [calc._period("2025", 0)],
        {},
        {},
        frozenset(),
        None,
        analysis_id="01ARZ3NDEKTSV4RRFFQ69G5FAY",
        actor=Actor(user_id="ada", client_id="desk"),
    )
    rows = pointer.list_analysis("01ARZ3NDEKTSV4RRFFQ69G5FAY")
    sources = []
    for row in rows:
        trace = json.loads(await analyses.store.get(row["object_key"]))["trace"]
        sources.append(trace["execution_source"])
        assert trace["actor_id"] == "ada"
        assert "user_id" not in trace
    assert sources == ["rule:period_grain_mismatch"]


def test_service_actor_is_not_promoted_by_the_request():
    human = classify_actor(Actor(user_id="ada", client_id="desk"))
    assert (human.actor_type, human.actor_id, human.claimed_diverged) == ("human", "ada", False)
    anonymous = classify_actor(Actor())
    assert anonymous.actor_type == "service"
    assert anonymous.actor_id == "anonymous"
    system = classify_actor(Actor(user_id="system", client_id="fas"), claimed_type="human")
    assert system.actor_type == "service"
    assert system.actor_id == "fas"
    assert system.claimed_diverged is True
    named = classify_actor(Actor(user_id="batch", client_id="fas"), service_subjects=frozenset({"batch"}))
    assert named.actor_type == "service"
    assert named.actor_id == "fas"


def test_auto_confirmed_is_outside_the_human_sources():
    assert "auto_confirmed" not in _HUMAN
    assert "auto_confirmed" not in HUMAN_SOURCES
    assert "concept.set" in _HUMAN
    assert "concept.confirmed" in _HUMAN


def test_service_confirmation_does_not_override_a_human_or_clear_absent():
    human_event = {
        "seq": 1,
        "type": "concept.confirmed",
        "target": "row",
        "binding_key": "row",
        "value": "ebitda",
        "actor_type": "human",
    }
    service_event = {
        "seq": 2,
        "type": "concept.confirmed",
        "target": "row",
        "binding_key": "row",
        "value": "interest",
        "source": "auto_confirmed",
        "actor_type": "service",
    }
    absent_event = {
        "seq": 3,
        "type": "concept.absent",
        "target": "book",
        "binding_key": "book",
        "value": "ebitda",
    }
    human, _ignored, absent, _accepted, _marks, automatic = _decisions([human_event, service_event, absent_event])
    assert human["row"] == "ebitda"
    assert "row" not in automatic
    assert absent == frozenset({"ebitda"})
    kept = _visible(
        [{"binding_key": "row", "source": "confirmed", "effective_concept": "ebitda"}],
        absent,
    )
    dropped = _visible(
        [{"binding_key": "row", "source": "auto_confirmed", "effective_concept": "ebitda"}],
        absent,
    )
    assert len(kept) == 1
    assert dropped == []
    assigned = _one(
        {"binding_key": "other"},
        {},
        set(),
        frozenset(),
        None,
        {},
        automatic={"other": "interest"},
    )
    assert assigned.source == "auto_confirmed"
    assert assigned.concept == "interest"
    assert assigned.is_primary is True


async def test_journal_records_actor_type_and_does_not_let_the_body_promote(tmp_path):
    store = LocalStore(tmp_path)
    journal = Journal(store)
    job = "c" * 64
    service, duplicate = await journal.commit(
        job,
        target="row",
        event_type="concept.confirmed",
        value="interest",
        actor=Actor(user_id="system", client_id="fas"),
        expected_seq=None,
        request_id="svc",
        binding_key="row",
        claimed_type="human",
    )
    assert duplicate is False
    assert service["actor"] == {"user_id": "system", "client_id": "fas"}
    assert service["actor_type"] == "service"
    assert service["actor_id"] == "fas"
    assert service["source"] == "auto_confirmed"
    assert service["actor_claim"] == "diverged"
    human, duplicate = await journal.commit(
        job,
        target="row",
        event_type="concept.confirmed",
        value="ebitda",
        actor=Actor(user_id="ada", client_id="desk"),
        expected_seq=service["seq"],
        request_id="human",
        binding_key="row",
        claimed_type="service",
    )
    assert duplicate is False
    assert human["actor_type"] == "human"
    assert human["actor_id"] == "ada"
    assert human["actor"] == {"user_id": "ada", "client_id": "desk"}
    assert human["actor_claim"] == "diverged"
    assert "source" not in human
    human_map, _ignored, _absent, _accepted, _marks, automatic = _decisions(await journal.read_all(job))
    assert human_map["row"] == "ebitda"
    assert "row" not in automatic
