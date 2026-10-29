"""Фаза 3b: профиль, canary, few-shot (§5.11.2–5.11.4)."""

from datetime import UTC, datetime, timedelta

from finance_analysis.adapters.ml.cluster import HdbscanCluster
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.application.catalog import load_catalog, load_git_document
from finance_analysis.application.examples import ExampleStore
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.application.learning import Learning
from finance_analysis.application.mapping_pipeline import few_shot_state
from finance_analysis.application.ports import Models
from finance_analysis.domain.glossary import with_profile
from finance_analysis.domain.glossary_release import (
    canary_verdict,
    glossary_for_job,
    package_of,
)
from finance_analysis.settings import Settings

CATALOG = load_catalog()


def test_profile_overlay_beats_global_for_that_profile_only():
    document = load_git_document()
    document["glossaries"]["debt_service"].setdefault("scoped", {})["acme"] = {"hidden": {"en": ["CFADS"]}}
    package = package_of(document)
    assert package.resolve("CFADS").concept == "cfads"
    assert with_profile(package, document, "acme").resolve("CFADS").concept == "debt_service"
    assert with_profile(package, document, "other").resolve("CFADS").concept == "cfads"
    assert with_profile(package, document, None).resolve("CFADS").concept == "cfads"


def test_canary_verdict_waits_without_volume_or_time():
    since = datetime(2026, 1, 1, tzinfo=UTC)
    kwargs = {"hours": 48, "min_books": 10, "min_rows": 200, "max_hours": 168}
    assert canary_verdict(since, 10, 200, since + timedelta(hours=48), **kwargs) == "promote"
    assert canary_verdict(since, 9, 200, since + timedelta(hours=49), **kwargs) == "wait"
    assert canary_verdict(since, 10, 200, since + timedelta(hours=47), **kwargs) == "wait"
    assert canary_verdict(since, 1, 1, since + timedelta(hours=200), **kwargs) == "wait"


def test_canary_bucket_is_stable_and_share_zero_stays_active():
    head = {"active": "g-a", "canary": "g-c", "canary_share": 100}
    assert glossary_for_job(head, "job-1") == "g-c"
    assert glossary_for_job(head, "job-1") == glossary_for_job(head, "job-1")
    assert glossary_for_job({**head, "canary_share": 0}, "job-1") == "g-a"


def test_few_shot_appends_path_text_only():
    assert few_shot_state("row", [(0.9, {"concept": "cfads"})]) == "row"
    state = few_shot_state("row", [(0.9, {"path_text": "CF › CFADS", "concept": "cfads"})])
    assert state.startswith("row\nПримеры:\n")
    assert "CF › CFADS → cfads" in state


def _learning(tmp_path, **settings):
    store = LocalStore(tmp_path)
    glossary = GlossaryStore(store)
    learning = Learning(
        store,
        PyarrowParquet(),
        glossary,
        ExampleStore(store, PyarrowParquet(), NumpyIndex(), model=""),
        Models(),
        HdbscanCluster(),
        Settings(FAS_REDIS_URL="redis://unused", **settings),
    )
    return learning, glossary


async def _confirm(learning, job: str, actor: str, profile: str):
    rows = {"k": {"binding_key": "k", "row_key": "k", "label": "Lender cash", "label_path_text": "Lender cash"}}
    record = {"seq": 1, "type": "concept.confirmed", "binding_key": "k", "value": "cfads", "actor": {"user_id": actor}}
    await learning.record_decisions(
        job, [record], rows=rows, bindings={}, events=[record], profile=profile, glossary_version="g", package=CATALOG
    )


async def test_auto_promote_stops_at_profile_canary(tmp_path):
    learning, glossary = _learning(tmp_path, GLOSSARY_AUTO_PROMOTE=True)
    await glossary.ensure()
    for job, actor in (("a", "u1"), ("b", "u2"), ("c", "u3")):
        await _confirm(learning, job, actor, "acme")
    result = await learning.mine(CATALOG, load_git_document())
    assert result["mode"] == "canary"
    head = await glossary.ensure()
    assert head["canary"] and head["canary"] != head["active"]
    document = await glossary.document(head["canary"])
    scoped = document["glossaries"]["cfads"]["scoped"]["acme"]["alt"]["en"]
    assert "Lender cash" in scoped
    assert "Lender cash" not in list((document["glossaries"]["cfads"].get("alt") or {}).get("en") or [])
    again = await learning.mine(CATALOG, load_git_document())
    assert again["mode"] == "proposals" and again["candidates"] == 0
    assert (await glossary.ensure())["canary"] == head["canary"]


async def test_shadow_failure_keeps_auto_proposal(tmp_path):
    learning, glossary = _learning(tmp_path, GLOSSARY_AUTO_PROMOTE=True)

    async def deny(_version):
        return {"passed": False, "reasons": ["test"]}

    glossary.gate = deny
    await glossary.ensure()
    for job, actor in (("a", "u1"), ("b", "u2"), ("c", "u3")):
        await _confirm(learning, job, actor, "acme")
    result = await learning.mine(CATALOG, load_git_document())
    assert result["mode"] == "proposals"
    head = await glossary.ensure()
    assert head.get("canary") is None
    opened = [item for item in (await glossary.proposals())["proposals"] if item["origin"] == "auto"]
    assert opened and opened[0]["status"] == "open" and opened[0]["text"] == "Lender cash"
