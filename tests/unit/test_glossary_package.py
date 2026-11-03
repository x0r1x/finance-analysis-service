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
        "net_debt",
        "dscr_covenant",
        "escrow_balance",
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
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}},
        )
    assert caught.value.labels == ["одна", "вторая"]


def test_same_label_in_pref_and_alt_fails():
    with pytest.raises(GlossaryInvalid) as caught:
        build_package(
            _body(),
            _glossary(alt={"ru": ["Денежный поток"]}),
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}},
        )
    assert caught.value.labels == ["Денежный поток", "Денежный поток"]


def test_alt_without_pref_in_that_language_fails():
    with pytest.raises(GlossaryInvalid) as caught:
        build_package(
            _body(),
            _glossary(alt={"de": ["ДПОД"]}),
            {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}},
        )
    assert caught.value.labels == ["ДПОД"]


def test_replace_upload_reads_and_profile_list(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        head = await gloss.ensure()
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
        _human, _ignored, absent = _decisions(events)
        assert "capex" in absent

        gloss = GlossaryStore(store)
        head = await gloss.ensure()
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
