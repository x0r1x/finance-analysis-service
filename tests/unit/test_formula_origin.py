"""Наследование пометок: отчёт короткий, цепь в ответе полная."""

from finance_analysis.application.model_types import load_metric_catalog
from finance_analysis.application.report import render_markdown
from finance_analysis.application.rule_engine import load_rules, run_rules, select_rules
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.model_type import MetricExpression
from tests.unit.rule_inputs import PERIODS, fact, link, row


def _expressions():
    _inputs, _variants, _composed, _bases, _rates, expressions = load_metric_catalog()
    return expressions


def _orders():
    return {
        "icr": ("interest", "interest_paid"),
        "icr_ebit": ("interest", "interest_paid"),
        "corporate_covenant": ("interest", "interest_paid"),
        "ocf_covenant": ("interest", "interest_paid"),
        "pf": ("interest_paid", "interest"),
    }


def _marked(number: int, concept: str, **binding):
    key = f"S|{number}|S!r2"
    cells = [f"S!C{number}", f"S!D{number}", f"S!E{number}"]
    periods = ("2024", "2025", "2026@план")
    formulas = (f"C{number}+1", f"D{number}+2", f"E{number}+3")
    facts = [fact(key, cell, period, "1") for cell, period in zip(cells, periods, strict=True)]
    links = []
    for cell, formula, period in zip(cells, formulas, periods, strict=True):
        links += link(cell, formula, key, period)
    bound = {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": key,
        "binding_key": f"bk-{concept}-{number}",
        **binding,
    }
    return key, row(key, label=concept), facts, links, bound


def _book():
    dscr, cfads, mid, driver, other = (
        "S|34|S!r2",
        "S|14|S!r2",
        "S|9|S!r2",
        "S|8|S!r2",
        "S|99|S!r2",
    )
    rows = [
        row(dscr, label="DSCR"),
        row(cfads, label="CFADS"),
        row(mid, label="середина"),
        row(driver, label="драйвер"),
        row(other, label="чужой"),
    ]
    facts = [
        fact(dscr, "S!D34", "2025", "1"),
        fact(cfads, "S!C14", "2024", "1"),
        fact(cfads, "S!D14", "2025", "1"),
        fact(cfads, "S!E14", "2026@план", "1"),
        fact(driver, "S!D8", "2025", "1"),
        fact(other, "S!C99", "2024", "1"),
        fact(other, "S!D99", "2025", "1"),
        fact(other, "S!E99", "2026@план", "1"),
    ]
    links = (
        link("S!D34", "D14", dscr, "2025", refs=("S!D14",))
        + link("S!C14", "C9+1", cfads, "2024", refs=("S!C9",))
        + link("S!D14", "D9+2", cfads, "2025", refs=("S!D9",))
        + link("S!E14", "E9+3", cfads, "2026@план", refs=("S!E9",))
        + link("S!C9", "C8", mid, "2024", refs=("S!C8",))
        + link("S!D9", "D8", mid, "2025", refs=("S!D8",))
        + link("S!E9", "E8", mid, "2026@план", refs=("S!E8",))
        + link("S!D8", "D7*1.5", driver, "2025", refs=("S!D7",))
        + link("S!C99", "C98+1", other, "2024")
        + link("S!D99", "D98+4", other, "2025")
        + link("S!E99", "E98+7", other, "2026@план")
    )
    data = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=links,
        bindings=[
            {"status": "bound", "is_primary": True, "effective_concept": "dscr", "row_key": dscr},
            {"status": "bound", "is_primary": True, "effective_concept": "cfads", "row_key": cfads},
        ],
        applicable_metrics=frozenset({"dscr"}),
    )
    return data, driver


def test_direct_inputs_stay_short_and_the_chain_is_complete():
    data, driver = _book()
    findings = run_rules(select_rules(load_rules(), ["formula_pattern_break", "literal_in_formula"]), data)
    view = origin_view(
        data,
        findings,
        {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
    )
    [metric] = view["metrics"]
    assert metric["metric"] == "dscr"
    labels = [item["label"] for item in metric["direct"]]
    assert labels == ["CFADS"]
    driver_marks = {item.fingerprint for item in findings if any(loc.row_key == driver for loc in item.locations)}
    inherited = [item for item in view["chain"] if item["fingerprint"] in driver_marks]
    assert [item["depth"] for item in inherited] == [2]
    assert all(item["metric"] == "dscr" for item in view["chain"])
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "Происхождение формул" in text
    assert "CFADS" in text
    assert "драйвер" not in text
    assert "чужой" not in text
    assert view["book"]["literal_in_formula"]["low"] == 2
    assert view["book"]["formula_pattern_break"]["high"] == 2
    assert view["metrics"][0]["inputs"][0]["source"] == "formula"
    assert view["physical_lineage_complete"] is True
    assert view["truncated_links"] == 0
    assert view["note"] is None


def test_truncated_ref_range_does_not_make_the_chain_complete():
    key = "S|10|S!r2"
    data = AuditInput(
        rows=[row(key, label="сумма")],
        periods=PERIODS,
        facts=[fact(key, "S!C10", "2024", "1")],
        links=[
            {
                "cell": "S!C10",
                "formula": "SUM(A10:A100)",
                "formula_class": "same_period",
                "ref_cell": "S!A10",
                "row_key": key,
                "period_id": "2024",
                "truncated": True,
            }
        ],
        bindings=[{"status": "bound", "is_primary": True, "effective_concept": "cfads", "row_key": key}],
        applicable_metrics=frozenset({"dscr"}),
    )
    assert data.link_cells["S!C10"].truncated is True
    assert data.link_cells["S!C10"].refs == ("S!A10",)
    _findings, view = _view(
        data,
        {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
    )
    assert view["chain"] == []
    assert view["physical_lineage_complete"] is False
    assert view["truncated_links"] == 1
    assert view["note"] == "цепь может быть неполной: обрезано ссылок 1"
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "цепь может быть неполной: обрезано ссылок 1" in text


def test_missing_graph_links_is_not_a_complete_chain():
    data = AuditInput(links=[], graph_links_available=False)
    view = origin_view(data, [], {})
    assert view["physical_lineage_complete"] is False
    assert view["truncated_links"] == 0
    assert view["note"] == "физическая трассировка недоступна: graph_links не загружен"
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "физическая трассировка недоступна: graph_links не загружен" in text


def test_loaded_empty_graph_links_stays_complete():
    data = AuditInput(links=[], graph_links_available=True)
    view = origin_view(data, [], {})
    assert view["physical_lineage_complete"] is True
    assert view["truncated_links"] == 0
    assert view["note"] is None
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "недоступна" not in text


def _view(data, expressions):
    findings = run_rules(select_rules(load_rules(), ["formula_pattern_break"]), data)
    view = origin_view(data, findings, expressions, interest_order=_orders())
    return findings, view


def test_icr_with_both_numerators_does_not_inherit_ebit():
    expressions = _expressions()
    assert expressions["icr"].one_of == frozenset({"ebitda", "ebit"})
    parts = [_marked(10, "ebitda"), _marked(11, "ebit"), _marked(12, "interest")]
    data = AuditInput(
        rows=[item[1] for item in parts],
        periods=PERIODS,
        facts=[fact for item in parts for fact in item[2]],
        links=[link for item in parts for link in item[3]],
        bindings=[item[4] for item in parts],
        applicable_metrics=frozenset({"icr"}),
    )
    findings, view = _view(data, expressions)
    [metric] = view["metrics"]
    sources = {item["concept"]: item["source"] for item in metric["inputs"]}
    assert sources["ebitda"] == "one_of"
    assert "ebit" not in sources
    assert sources["interest"] == "formula"
    ebit_key = parts[1][0]
    ebit_marks = {item.fingerprint for item in findings if any(loc.row_key == ebit_key for loc in item.locations)}
    assert ebit_marks
    assert not any(item["fingerprint"] in ebit_marks for item in view["chain"])
    assert any(item["input"] == "ebitda" and item["source"] == "one_of" for item in view["chain"])
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "вход ebitda: one_of" in text
    assert "вход ebit:" not in text


def test_stale_or_non_primary_binding_is_not_a_seed():
    fresh = _marked(20, "cfads")
    secondary = _marked(21, "cfads", is_primary=False, binding_key="bk-secondary")
    stale = _marked(22, "cfads", stale=True, binding_key="bk-stale")
    parts = [fresh, secondary, stale]
    data = AuditInput(
        rows=[item[1] for item in parts],
        periods=PERIODS,
        facts=[fact for item in parts for fact in item[2]],
        links=[link for item in parts for link in item[3]],
        bindings=[item[4] for item in parts],
        applicable_metrics=frozenset({"dscr"}),
    )
    findings, view = _view(data, {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))})
    [metric] = view["metrics"]
    assert [item["row_key"] for item in metric["inputs"]] == [fresh[0]]
    marks = {
        item[0]: {found.fingerprint for found in findings if any(loc.row_key == item[0] for loc in found.locations)}
        for item in parts
    }
    inherited = {item["fingerprint"] for item in view["chain"]}
    assert marks[fresh[0]] <= inherited
    assert not marks[secondary[0]] & inherited
    assert not marks[stale[0]] & inherited


def test_dscr_and_adscr_variants_seed_only_that_variant():
    expressions = _expressions()
    names = ("cfads", "debt_service", "ebitda", "cash_taxes", "capex", "interest", "principal")
    housing = ("cfo_statement", "cfi_statement", "financing_inflows", "senior_principal", "senior_interest_paid")
    parts = [_marked(30 + index, name) for index, name in enumerate((*names, *housing))]
    rows = [item[1] for item in parts]
    facts = [fact for item in parts for fact in item[2]]
    links = [link for item in parts for link in item[3]]
    bindings = [item[4] for item in parts]

    corporate = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=links,
        bindings=bindings,
        applicable_metrics=frozenset({"dscr"}),
        dscr_variant="corporate_covenant",
    )
    _findings, view = _view(corporate, expressions)
    [metric] = view["metrics"]
    sources = {item["concept"]: item["source"] for item in metric["inputs"]}
    assert set(sources) == {"ebitda", "cash_taxes", "capex", "interest", "principal"}
    assert set(sources.values()) == {"variant:corporate_covenant"}
    assert all(item["source"] == "variant:corporate_covenant" for item in view["chain"])

    housed = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=links,
        bindings=bindings,
        applicable_metrics=frozenset({"adscr"}),
        dscr_variant="housing",
    )
    _findings, housed_view = _view(housed, expressions)
    [adscr] = housed_view["metrics"]
    assert {item["concept"] for item in adscr["inputs"]} == set(housing)
    assert {item["source"] for item in adscr["inputs"]} == {"variant:housing"}

    base = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=links,
        bindings=bindings,
        applicable_metrics=frozenset({"adscr"}),
        dscr_variant="corporate_covenant",
    )
    _findings, base_view = _view(base, expressions)
    [kept] = base_view["metrics"]
    assert {item["concept"]: item["source"] for item in kept["inputs"]} == {
        "cfads": "base:dscr",
        "debt_service": "base:dscr",
    }


def test_dscr_fallback_seeds_only_the_chosen_parts():
    expressions = _expressions()
    parts = [_marked(40, "cfads"), _marked(41, "interest_paid"), _marked(42, "principal"), _marked(43, "ebitda")]
    data = AuditInput(
        rows=[item[1] for item in parts],
        periods=PERIODS,
        facts=[fact for item in parts for fact in item[2]],
        links=[link for item in parts for link in item[3]],
        bindings=[item[4] for item in parts],
        applicable_metrics=frozenset({"dscr"}),
        dscr_variant="pf",
    )
    _findings, view = _view(data, expressions)
    [metric] = view["metrics"]
    sources = {item["concept"]: item["source"] for item in metric["inputs"]}
    assert sources == {"cfads": "variant:pf", "interest_paid": "fallback", "principal": "fallback"}
    assert any(item["input"] == "interest_paid" and item["source"] == "fallback" for item in view["chain"])
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "вход interest_paid: fallback" in text


async def test_formula_origin_is_absent_on_ratios_and_present_on_audit_and_full():
    import anyio

    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.domain.book import Actor, Head

    catalog = type("Catalog", (), {})()
    catalog.version = "test"
    catalog.metric_expressions = {}
    catalog.interest_order = {}
    catalog.row_fallbacks = {}

    class Svc:
        model_types = catalog
        _cpu = anyio.CapacityLimiter(1)

    analyses = Analyses(Svc())

    async def metrics(*_args, **_kwargs):
        return {
            "rows": [],
            "needs_input": [],
            "warnings": [],
            "bindings": [],
            "facts": [],
            "periods": [],
            "phase_of": {},
            "profile": {},
            "absent": frozenset(),
            "applicability": {},
            "model_type": {},
            "dscr_variant": None,
            "book_rows": [],
        }

    async def no_findings(*_args, **_kwargs):
        return []

    async def noop(*_args, **_kwargs):
        return None

    saved: dict = {}

    async def save_tables(*args, **_kwargs):
        saved["envelope"] = args[5]

    analyses.compute_metrics = metrics
    analyses._metric_findings = no_findings
    analyses._annotate = noop
    analyses._save_tables = save_tables
    analyses._input = lambda *_args, **_kwargs: _empty_input()
    head = Head(build_key="b", state_seq=1, derive_key="d", versions={})
    target = Target(head, "b", {"builder_ref": {}}, False, "d")
    ratios = await analyses._execute_ratios("job", target, "ratios", ["dscr"], {}, Actor())
    assert "formula_origin" not in ratios["result_data"]
    audit = analyses._envelope("job", target, "audit", [], AuditInput(), [], [])
    assert "formula_origin" in audit["result_data"]
    await analyses._execute_full("job", target, "full", ["dscr"], None, {"rules": []}, Actor(), "")
    assert "formula_origin" in saved["envelope"]["result_data"]


async def _empty_input():
    return AuditInput()


async def test_audit_input_threads_graph_links_availability():
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    class Store:
        async def get(self, _key):
            return b"empty"

    class Parquet:
        async def read(self, _raw):
            return []

    class Glossary:
        async def concept_price_facts(self, _version):
            return {}, {}

        async def composed_of(self, _version):
            return {}

        async def concept_dimensions(self, _version):
            return {}

        async def profile_body(self, _profile_id):
            return {}

    class Guard:
        async def read_all(self, _job_id):
            return []

    class Svc:
        store = Store()
        parquet = Parquet()
        glossary = Glossary()
        guard = Guard()
        model_types = load_model_types()

        async def _dataset_rows(self, *_args, **_kwargs):
            raise NotFound("нет датасета")

        async def resolve_model_type(self, _job_id, _head):
            return Effective(
                labels=(),
                primary=None,
                source="unresolved",
                reason=None,
                seq=None,
                profile_version=None,
                score=None,
                scores={},
                candidates=(),
            )

    analyses = Analyses(Svc())
    head = Head(build_key="b", state_seq=1, derive_key="d", versions={})
    missing = Target(head, "b", {"files": {"a/1/projection/dim_row.parquet": {}}}, False, "d")
    empty = Target(
        head,
        "b",
        {"files": {"a/1/projection/graph_links.parquet": {}}},
        False,
        "d",
    )
    absent = await analyses._input("job", missing, frozenset({"links"}))
    loaded = await analyses._input("job", empty, frozenset({"links"}))
    assert absent.links == [] and absent.graph_links_available is False
    assert loaded.links == [] and loaded.graph_links_available is True
    absent_view = origin_view(absent, [], {})
    loaded_view = origin_view(loaded, [], {})
    assert absent_view["physical_lineage_complete"] is False
    assert loaded_view["physical_lineage_complete"] is True
