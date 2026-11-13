"""Пакет таксономии и меток (§5.1, §5.2)."""

from __future__ import annotations

import asyncio

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.glossary import (
    GlossaryInvalid,
    build_package,
    normalize_label,
)

_IDS = frozenset(
    {
        "cfads",
        "debt_service",
        "interest",
        "principal",
        "debt_outstanding",
        "ebitda",
        "ebit",
        "capex",
        "discount_rate",
        "dscr_lockup",
        "dscr_default",
        "target_dscr",
        "dscr",
        "icr",
        "cash_taxes",
        "operating_cash_flow",
        "net_debt",
        "dscr_covenant",
        "escrow_balance",
        "escrowed_funds_rate",
        "escrow_inflow",
        "escrow_disclosure",
        "escrow_coverage",
        "effective_rate",
        "grantor_payment",
        "capital_grant",
        "mgd_compensation",
        "project_fcf",
        "npv",
        "irr",
        "payback",
        "sources_and_uses",
        "exit_enterprise_value",
        "moic",
        "lbo_leverage",
        "wacc",
        "terminal_value",
        "enterprise_value",
        "equity_value",
        "noi",
        "cap_rate",
        "vacancy",
        "installed_capacity",
        "energy_generation",
        "capacity_factor",
        "degradation",
        "energy_tariff",
        "forecast_energy_tariff",
        "capacity_tariff",
        "purchase_price_allocation",
        "lease_interest_income",
        "npl_share",
        "provision_coverage",
        "revenue",
        "cogs",
        "gross_profit",
        "selling_expenses",
        "operating_profit",
        "profit_from_sales",
        "ifrs_operating_profit",
        "other_income",
        "other_expense",
        "depreciation_notes",
        "ebitda_ras",
        "ebitda_ifrs",
        "ebt",
        "income_tax",
        "net_income",
        "fixed_assets",
        "intangibles",
        "inventory",
        "receivables",
        "cash",
        "cash_balance",
        "share_capital",
        "retained_earnings",
        "total_assets",
        "deferred_tax_asset",
        "deferred_tax_liability",
        "borrowings_lt",
        "borrowings_st",
        "borrowings_total",
        "lease_liability",
        "finance_lease_liability",
        "operating_lease_liability",
        "accounts_payable",
        "section_lt_total",
        "section_st_total",
    }
)


def _body() -> dict:
    return {"concepts": {"cfads": {"kind": "measure", "unit": "money"}}, "taxonomy": "core-1"}


def _glossary(**extra) -> dict:
    base = {
        "concept": "cfads",
        "pref": {"ru": "Денежный поток", "en": "Cash flow"},
    }
    base.update(extra)
    return {"cfads": base}


def test_package_resolves_display_labels_and_keeps_ranges_as_text():
    package = load_catalog()
    assert package.ids == _IDS
    assert package.concepts["debt_service"].not_all_zero is True
    assert package.concepts["debt_service"].composed_of == ("interest", "principal")
    assert package.concepts["cfads"].related_to == ("dscr",)
    assert package.concepts["cfads"].broader is None
    assert package.concepts["cfads"].broader_than == ()
    assert package.concepts["discount_rate"].validation_range == ("0", "0.30")
    assert package.concepts["ebit"].kind == "measure"
    assert normalize_label("Ёлка") == normalize_label("елка")
    assert package.resolve("ДПОД").concept == "cfads"
    assert package.resolve("CFADS").concept == "cfads"
    # «дпод.» схлопывается с alt «ДПОД»; отдельной hidden-метки больше нет.
    assert package.resolve("дпод.").kind == "alt"
    hidden = package.resolve("ден. поток для обсл. долга")
    assert hidden.concept == "cfads"
    assert hidden.kind == "hidden"
    shown = package.display_label("cfads", "ru")
    assert shown == "Денежный поток для обслуживания долга"
    assert shown != hidden.text
    assert "факт" in package.markers["actual"]
    assert "приток" in package.flows["inflow"]


def test_second_pref_on_one_language_fails():
    with pytest.raises(GlossaryInvalid) as caught:
        build_package(
            _body(),
            _glossary(pref={"ru": ["одна", "вторая"], "en": "Cash flow"}),
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]}},
        )
    assert caught.value.labels == ["одна", "вторая"]


def test_same_label_in_pref_and_alt_fails():
    with pytest.raises(GlossaryInvalid) as caught:
        build_package(
            _body(),
            _glossary(alt={"ru": ["Денежный поток"]}),
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]}},
        )
    assert caught.value.labels == ["Денежный поток", "Денежный поток"]


def test_alt_without_pref_in_that_language_fails():
    with pytest.raises(GlossaryInvalid) as caught:
        build_package(
            _body(),
            _glossary(alt={"de": ["ДПОД"]}),
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]}},
        )
    assert caught.value.labels == ["ДПОД"]


def test_replace_upload_reads_and_profile_list(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        head = await gloss.bootstrap()
        etag = f"h-{head['seq']}"
        document = await gloss.document(head["active"])
        document["glossaries"]["cfads"]["pref"]["en"] = "Replaced flow"
        preview = await gloss.release([], etag, dry_run=True, document=document)
        assert preview["dry_run"] is True
        assert any(item["text"] == "Replaced flow" for item in preview["diff"])
        made = await gloss.release([], etag, document=document)
        events = await gloss.events()
        assert any(item.get("version") == made["version"] for item in events["events"])
        assert "cfads" in (await gloss.concepts())["concepts"]
        diff = await gloss.diff(head["active"], made["version"])
        assert any(item["text"] == "Replaced flow" for item in diff["diff"])
        assert (await gloss.release_view(made["version"]))["release"]["version"] == made["version"]
        saved = await gloss.put_profile(
            "bank",
            {"sign_convention": "outflow_positive", "marker_class": "actual"},
            if_match=None,
            if_none_match="*",
        )
        assert {"id": "bank", "etag": saved["etag"]} in (await gloss.list_profiles())["profiles"]

    asyncio.run(run())


def test_null_clears_actuals_end_and_sheet_class_and_omission_keeps_them(tmp_path):
    """Явный null снимает границу и класс листа. Пропуск поля их не трогает. null у dscr отвергается."""

    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.domain.errors import InvalidArgument

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        saved = await gloss.put_profile(
            "bank",
            {
                "sign_convention": "outflow_negative",
                "actuals_end": "2020Q4",
                "sheet_class": {"Отчёт": "reporting", "Предпосылки": "assumptions"},
            },
            if_match=None,
            if_none_match="*",
        )
        kept = await gloss.put_profile(
            "bank",
            {"sign_convention": "outflow_positive"},
            if_match=saved["etag"],
            if_none_match=None,
        )
        assert kept["body"]["actuals_end"] == "2020Q4"
        assert kept["body"]["sheet_class"] == {"Отчёт": "reporting", "Предпосылки": "assumptions"}
        cleared = await gloss.put_profile(
            "bank",
            {"actuals_end": None, "sheet_class": None},
            if_match=kept["etag"],
            if_none_match=None,
        )
        assert "actuals_end" not in cleared["body"]
        assert "sheet_class" not in cleared["body"]
        restored = await gloss.put_profile(
            "bank",
            {"actuals_end": "2020Q4", "sheet_class": {"Отчёт": "reporting"}},
            if_match=cleared["etag"],
            if_none_match=None,
        )
        with pytest.raises(InvalidArgument):
            await gloss.put_profile(
                "bank",
                {"dscr_definition": None},
                if_match=restored["etag"],
                if_none_match=None,
            )
        body = await gloss.profile_body("bank")
        assert body["actuals_end"] == "2020Q4"
        assert body["sheet_class"] == {"Отчёт": "reporting"}

    asyncio.run(run())


def test_two_decision_kinds_stay_and_a_failed_proposal_stays_open(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.application.journal import Journal
    from finance_analysis.domain.book import Actor
    from finance_analysis.domain.errors import InvalidArgument
    from finance_analysis.domain.mapping import _decisions
    from finance_analysis.domain.state import fold

    async def run():
        store = LocalStore(tmp_path)
        journal = Journal(store)
        actor = Actor(user_id="alex", client_id="desk")
        job = "a" * 64
        await journal.commit(
            job,
            target="row",
            event_type="sign.set",
            value="outflow",
            actor=actor,
            expected_seq=None,
            request_id="sign",
            binding_key="row",
        )
        await journal.commit(
            job,
            target="row",
            event_type="concept.set",
            value="cfads",
            actor=actor,
            expected_seq=None,
            request_id="concept",
            binding_key="row",
        )
        await journal.commit(
            job,
            target="row",
            event_type="unit.set",
            value="money",
            actor=actor,
            expected_seq=None,
            request_id="unit",
            binding_key="row",
        )
        await journal.commit(
            job,
            target="book",
            event_type="concept.absent",
            value="capex",
            actor=actor,
            expected_seq=None,
            request_id="absent",
        )
        await journal.commit(
            job,
            target="book",
            event_type="profile.set",
            value="bank",
            actor=actor,
            expected_seq=None,
            request_id="profile",
        )
        events = await journal.read_all(job)
        kinds = {event["type"] for event in fold(events).values()}
        assert {"sign.set", "concept.set", "unit.set", "concept.absent", "profile.set"} <= kinds
        _human, _ignored, absent, _accepted = _decisions(events)
        assert "capex" in absent

        gloss = GlossaryStore(store)
        head = await gloss.bootstrap()
        proposal = await gloss.add_proposal({"concept": "missing", "kind": "alt", "lang": "en", "text": "nope"})
        try:
            await gloss.decide_proposals([{"id": proposal["id"], "decision": "accept"}])
        except InvalidArgument:
            pass
        else:
            raise AssertionError("чужое понятие должно отказать")
        assert (await gloss.proposal(proposal["id"]))["status"] == "open"
        assert head["active"]

    asyncio.run(run())


_DICTS = {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]}}


def _measure(**extra) -> dict:
    body = {"kind": "measure", "unit": "money"}
    body.update(extra)
    return body


def _gloss(name: str, **extra) -> dict:
    base = {"concept": name, "pref": {"ru": name, "en": name}}
    base.update(extra)
    return base


def _concepts(bodies: dict[str, dict], glossaries: dict | None = None):
    return build_package(
        {"taxonomy": "core-1", "concepts": bodies},
        glossaries or {name: _gloss(name) for name in bodies},
        _DICTS,
    )


def test_catalog_relations_match_the_identity_file():
    from finance_analysis.application.catalog import load_identities

    package = load_catalog()
    assert load_identities()["debt_service"] == list(package.concepts["debt_service"].composed_of)


def test_legacy_composition_is_read_and_metric_ids_in_related_are_dropped():
    package = _concepts(
        {
            "debt_service": _measure(composition=["interest", "principal"]),
            "interest": _measure(),
            "principal": _measure(),
            "cfads": _measure(related=["dscr", "llcr", "plcr"]),
            "dscr": _measure(),
        }
    )
    assert package.concepts["debt_service"].composed_of == ("interest", "principal")
    assert package.concepts["cfads"].related_to == ("dscr",)
    with pytest.raises(GlossaryInvalid) as caught:
        _concepts(
            {
                "a": _measure(composition=["b"], relations={"composed_of": ["b"]}),
                "b": _measure(),
            }
        )
    assert "legacy:relations" in caught.value.labels


def test_unknown_and_reserved_relation_types_fail():
    bodies = {"a": _measure(relations={"see_also": ["b"]}), "b": _measure()}
    with pytest.raises(GlossaryInvalid) as caught:
        _concepts(bodies)
    assert "unknown:see_also" in caught.value.labels
    reserved = {"a": _measure(relations={"equivalent_to": ["b"]}), "b": _measure()}
    with pytest.raises(GlossaryInvalid) as reserved_caught:
        _concepts(reserved)
    assert "reserved:equivalent_to" in reserved_caught.value.labels
    replaced = {"a": _measure(relations={"replaced_by": ["b"]}), "b": _measure()}
    with pytest.raises(GlossaryInvalid) as replaced_caught:
        _concepts(replaced)
    assert "reserved:replaced_by" in replaced_caught.value.labels


def test_duplicate_missing_and_cyclic_relations_fail():
    with pytest.raises(GlossaryInvalid) as duplicate:
        _concepts({"a": _measure(relations={"related_to": ["b", "b"]}), "b": _measure()})
    assert "duplicate:related_to" in duplicate.value.labels
    with pytest.raises(GlossaryInvalid) as missing:
        _concepts({"a": _measure(relations={"related_to": ["missing"]})})
    assert "missing:missing" in missing.value.labels
    with pytest.raises(GlossaryInvalid) as composed:
        _concepts(
            {
                "a": _measure(relations={"composed_of": ["b"]}),
                "b": _measure(relations={"composed_of": ["a"]}),
            }
        )
    assert "cycle:composed_of" in composed.value.labels
    with pytest.raises(GlossaryInvalid) as hierarchy:
        _concepts(
            {
                "a": _measure(relations={"broader_than": ["b"]}),
                "b": _measure(relations={"broader_than": ["a"]}),
            }
        )
    assert "cycle:broader" in hierarchy.value.labels


def test_published_broader_stays_and_must_agree_with_broader_than():
    agreed = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(),
        },
        {
            "parent": _gloss("parent"),
            "child": _gloss("child", broader="parent"),
        },
    )
    assert agreed.concepts["child"].broader == "parent"
    assert agreed.concepts["parent"].broader_than == ("child",)
    only_edge = _concepts(
        {"parent": _measure(relations={"broader_than": ["child"]}), "child": _measure()}
    )
    assert only_edge.concepts["child"].broader is None
    with pytest.raises(GlossaryInvalid) as conflict:
        _concepts(
            {
                "parent": _measure(relations={"broader_than": ["child"]}),
                "other": _measure(),
                "child": _measure(),
            },
            {
                "parent": _gloss("parent"),
                "other": _gloss("other"),
                "child": _gloss("child", broader="other"),
            },
        )
    assert "child" in conflict.value.labels
    with pytest.raises(GlossaryInvalid) as cycle:
        _concepts(
            {"a": _measure(), "b": _measure()},
            {"a": _gloss("a", broader="b"), "b": _gloss("b", broader="a")},
        )
    assert "cycle:broader" in cycle.value.labels


def test_mixed_broader_stores_share_one_parent_to_child_graph():
    with pytest.raises(GlossaryInvalid) as around:
        _concepts(
            {
                "a": _measure(relations={"broader_than": ["c"]}),
                "b": _measure(),
                "c": _measure(relations={"broader_than": ["b"]}),
            },
            {
                "a": _gloss("a", broader="b"),
                "b": _gloss("b"),
                "c": _gloss("c"),
            },
        )
    assert "cycle:broader" in around.value.labels
    with pytest.raises(GlossaryInvalid) as direct:
        _concepts(
            {"a": _measure(relations={"broader_than": ["b"]}), "b": _measure()},
            {"a": _gloss("a", broader="b"), "b": _gloss("b")},
        )
    assert "cycle:broader" in direct.value.labels


def test_catch_glossary_remaps_a_newer_version_once():
    from finance_analysis.application.service import FasService

    class Stub:
        glossary_seen = ""
        calls = 0
        catch_glossary = FasService.catch_glossary

        async def remap_glossary(self):
            self.calls += 1

    async def run():
        stub = Stub()
        assert await stub.catch_glossary("g-0001:aaa")
        assert not await stub.catch_glossary("g-0001:aaa")
        assert await stub.catch_glossary("g-0002:ccc")
        assert stub.calls == 2

    asyncio.run(run())


def test_ensure_does_not_publish_bootstrap_and_impact_is_501(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.domain.errors import NotFound, NotImplementedYet

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        assert await gloss.peek() is None
        with pytest.raises(NotFound):
            await gloss.ensure()
        assert await gloss.peek() is None

        for method in (
            gloss.releases,
            gloss.events,
            gloss.concepts,
            lambda: gloss.content(None, "json"),
            lambda: gloss.diff(None, None),
        ):
            with pytest.raises(NotFound):
                await method()
            assert await gloss.peek() is None

        with pytest.raises(NotImplementedYet) as impact:
            await gloss.impact()
        assert impact.value.status == 501
        assert await gloss.peek() is None

        head = await gloss.bootstrap()
        assert head["seq"] == 1
        assert (await gloss.ensure())["active"] == head["active"]
        again = await gloss.bootstrap()
        assert again["seq"] == 1
        assert again["active"] == head["active"]

    asyncio.run(run())


def test_bootstrap_recovers_orphan_release_and_converges(tmp_path):
    from finance_analysis.adapters.queue.learning_tasks import _active
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import HEAD, GlossaryStore
    from finance_analysis.domain.errors import NotFound

    async def run():
        store = LocalStore(tmp_path / "main")
        gloss = GlossaryStore(store)
        first = await gloss.bootstrap()
        removed = await store.delete_prefix(HEAD)
        assert removed >= 1
        assert await gloss.peek() is None

        recovered = await gloss.bootstrap()
        assert recovered["active"] == first["active"]
        assert recovered["seq"] == 1
        assert (await gloss.peek())["active"] == first["active"]

        left = GlossaryStore(store)
        right = GlossaryStore(store)
        concurrent = await asyncio.gather(left.bootstrap(), right.bootstrap())
        assert {item["active"] for item in concurrent} == {first["active"]}

        empty = GlossaryStore(LocalStore(tmp_path / "empty"))
        with pytest.raises(NotFound):
            await _active(empty)
        assert await empty.peek() is None

        package, document = await _active(gloss)
        assert document
        assert package is not None

    asyncio.run(run())
