"""Релизы глоссария: 428, 412, dry_run, откат, stale_parent (§12 п. 4–5)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService

pytestmark = pytest.mark.asyncio

HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
_PREF = {"op": "set_pref", "concept": "cfads", "kind": "pref", "lang": "en", "text": "Flow for debt"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def _state(client: AsyncClient) -> tuple[dict, str]:
    response = await client.get("/v1/glossary", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json(), response.headers["etag"]


async def _transition(client: AsyncClient, service, headers: dict, body: dict) -> dict:
    response = await client.post("/v1/glossary/transitions", headers=headers, json=body)
    assert response.status_code == 202, response.text
    operation = response.json()
    assert operation["kind"] == "glossary.validate"
    assert operation["payload"]["queue"] == "fas:glossary"
    assert operation["payload"]["stage"] == "glossary.transition"
    assert response.headers["operation-location"] == f"/v1/operations/{operation['id']}"
    done = await service.wait_op(operation["id"], 120_000)
    assert done["status"] == "succeeded", done
    return done["result"]


async def test_preconditions_dry_run_rollback_and_export(app, local_service, task_workers):
    async with _client(app) as client:
        missing = await client.post("/v1/glossary/releases", headers=HEADERS, json={"ops": []})
        assert missing.status_code == 428
        assert missing.headers["cache-control"] == "no-store"

        _body, etag = await _state(client)
        stale = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": "h-999"},
            json={"ops": []},
        )
        assert stale.status_code == 412
        assert stale.json()["state"]["etag"] == etag

        dry = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF], "dry_run": True},
        )
        assert dry.status_code == 200, dry.text
        assert dry.json()["dry_run"] is True
        assert any(item["change"] == "add" for item in dry.json()["diff"])
        again, etag = await _state(client)
        assert again["seq"] == 1

        odd = await client.get("/v1/glossary/content", headers=HEADERS, params={"format": "md"})
        assert odd.status_code == 406
        assert odd.json()["formats"] == ["json", "yaml"]
        impact = await client.get("/v1/glossary/impact", headers=HEADERS)
        assert impact.json()["books"] == []

        made = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF]},
        )
        assert made.status_code == 200, made.text
        version = made.json()["version"]
        activated = await _transition(
            client,
            local_service,
            {**HEADERS, "If-Match": made.headers["etag"]},
            {"version": version, "status": "active"},
        )
        changed = await client.get("/v1/glossary/content", headers=HEADERS)
        assert changed.json()["glossaries"]["cfads"]["pref"]["en"] == "Flow for debt"

        rolled = await client.post(
            "/v1/glossary:rollback",
            headers={**HEADERS, "If-Match": activated["etag"]},
            json={},
        )
        assert rolled.status_code == 200, rolled.text
        assert rolled.json()["state"]["active"] == again["active"]
        history = (await client.get("/v1/glossary/releases", headers=HEADERS)).json()["releases"]
        assert any(item["version"] == again["active"] and item["status"] == "active" for item in history)
        assert any(item["version"] == version and item["status"] == "retired" for item in history)
        restored = await client.get("/v1/glossary/content", headers=HEADERS)
        assert restored.json()["glossaries"]["cfads"]["pref"]["en"] == "Cash flow available for debt service"
        patch = await local_service.glossary.export_patch()
        assert "changes: []" in patch or patch.strip().endswith("[]")


async def test_stale_parent_and_idempotent_release(app, local_service, task_workers):
    async with _client(app) as client:
        _body, etag = await _state(client)
        first = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag, "Idempotency-Key": "rel-1"},
            json={"ops": [{"op": "add_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "alpha"}]},
        )
        assert first.status_code == 200, first.text
        replay = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag, "Idempotency-Key": "rel-1"},
            json={"ops": [{"op": "add_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "alpha"}]},
        )
        assert replay.status_code == 200
        assert replay.json()["version"] == first.json()["version"]
        state, etag = await _state(client)
        assert state["seq"] == 2

        second = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [{"op": "add_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "beta"}]},
        )
        assert second.status_code == 200, second.text
        activated = await _transition(
            client,
            local_service,
            {**HEADERS, "If-Match": second.headers["etag"]},
            {"version": first.json()["version"], "status": "active"},
        )
        conflict = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": activated["etag"]},
            json={"version": second.json()["version"], "status": "active"},
        )
        assert conflict.status_code == 202, conflict.text
        failed = await local_service.wait_op(conflict.json()["id"], 120_000)
        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "stale_parent"


async def test_admin_token_when_configured(app, settings):
    settings.fas_admin_token = "secret"
    async with _client(app) as client:
        _body, etag = await _state(client)
        denied = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [], "dry_run": True},
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "admin_token_required"
        allowed = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag, "X-Admin-Token": "secret"},
            json={"ops": [], "dry_run": True},
        )
        assert allowed.status_code == 200, allowed.text


async def test_replace_upload_and_read_routes(app):
    async with _client(app) as client:
        body, etag = await _state(client)
        current = await client.get("/v1/glossary/content", headers=HEADERS)
        assert current.status_code == 200, current.text
        document = current.json()
        document["glossaries"]["cfads"]["pref"]["en"] = "Replaced flow"
        preview = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"mode": "replace", "document": document, "dry_run": True},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["dry_run"] is True
        assert any(item["text"] == "Replaced flow" for item in preview.json()["diff"])
        made = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"mode": "replace", "document": document},
        )
        assert made.status_code == 200, made.text
        version = made.json()["version"]
        events = await client.get("/v1/glossary/events", headers=HEADERS)
        assert any(item.get("version") == version for item in events.json()["events"])
        concepts = await client.get("/v1/glossary/concepts", headers=HEADERS)
        assert "cfads" in concepts.json()["concepts"]
        diff = await client.get(
            "/v1/glossary/diff",
            headers=HEADERS,
            params={"from": body["active"], "to": version},
        )
        assert diff.status_code == 200, diff.text
        assert any(item["text"] == "Replaced flow" for item in diff.json()["diff"])
        one = await client.get(f"/v1/glossary/releases/{version}", headers=HEADERS)
        assert one.status_code == 200, one.text
        assert one.json()["release"]["version"] == version


async def test_transition_is_async_and_etag_conflict_stays_on_the_request(app, local_service, task_workers):
    async with _client(app) as client:
        _body, etag = await _state(client)
        made = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF]},
        )
        assert made.status_code == 200, made.text
        version = made.json()["version"]
        missing = await client.post(
            "/v1/glossary/transitions",
            headers=HEADERS,
            json={"version": version, "status": "active"},
        )
        assert missing.status_code == 428
        stale = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": "h-999"},
            json={"version": version, "status": "active"},
        )
        assert stale.status_code == 412
        assert stale.json()["code"] == "precondition_failed"
        listed = await client.get("/v1/operations", headers=HEADERS, params={"kind": "glossary.validate"})
        assert listed.json()["operations"] == []
        canary = await _transition(
            client,
            local_service,
            {**HEADERS, "If-Match": made.headers["etag"]},
            {"version": version, "status": "canary"},
        )
        assert canary["status"] == "canary"
        assert canary["state"]["canary"] == version


async def test_glossary_activation_on_s3_lists_books(s3_store, settings, redis_runtime, builder):
    service = FasService(settings, s3_store, PyarrowParquet(), builder, WrenQuery(settings), redis_runtime)
    app = create_app(settings, service=service, support=redis_runtime)
    async with _client(app) as client:
        _body, etag = await _state(client)
        made = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF]},
        )
        assert made.status_code == 200, made.text
        activated = await service.perform_glossary_transition(
            made.json()["version"],
            "active",
            made.headers["etag"],
            force=False,
            reason=None,
        )
        version = made.json()["version"]
        assert activated["state"]["active"] == version
        content = await client.get("/v1/glossary/content", headers=HEADERS)
        assert content.json()["glossaries"]["cfads"]["pref"]["en"] == "Flow for debt"
        events = await client.get("/v1/glossary/events", headers=HEADERS)
        assert events.status_code == 200, events.text
        assert any(item.get("version") == version for item in events.json()["events"])


async def test_release_dry_run_query_agrees_with_body(app):
    async with _client(app) as client:
        _body, etag = await _state(client)
        headers = {**HEADERS, "If-Match": etag}
        preview = await client.post(
            "/v1/glossary/releases",
            headers=headers,
            params={"dry_run": "true"},
            json={"ops": [_PREF]},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["dry_run"] is True
        state, etag = await _state(client)
        assert state["seq"] == 1

        same = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            params={"dry_run": "TRUE"},
            json={"ops": [_PREF], "dry_run": True},
        )
        assert same.status_code == 200, same.text
        assert same.json()["dry_run"] is True
        state, etag = await _state(client)
        assert state["seq"] == 1

        clash = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            params={"dry_run": "false"},
            json={"ops": [_PREF], "dry_run": True},
        )
        assert clash.status_code == 400, clash.text
        assert clash.json()["code"] == "invalid_argument"
        assert clash.json()["detail"] == (
            "Параметр dry_run в строке запроса и в теле запроса имеет разные значения. "
            "Укажите его в одном месте или задайте одинаковые значения."
        )
        other = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            params={"dry_run": "true"},
            json={"ops": [_PREF], "dry_run": False},
        )
        assert other.status_code == 400, other.text
        assert other.json()["code"] == "invalid_argument"
        odd = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            params={"dry_run": "yes"},
            json={"ops": [_PREF]},
        )
        assert odd.status_code == 400, odd.text
        assert odd.json()["code"] == "invalid_argument"
        assert odd.json()["detail"] == "Параметр dry_run в строке запроса должен иметь значение true или false."
        text = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF], "dry_run": "false"},
        )
        assert text.status_code == 400, text.text
        assert text.json()["code"] == "invalid_argument"
        assert text.json()["detail"] == "Поле dry_run в теле запроса должно быть логическим значением true или false."
        quoted = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            json={"ops": [_PREF], "dry_run": "true"},
        )
        assert quoted.status_code == 400, quoted.text
        assert quoted.json()["code"] == "invalid_argument"
        assert quoted.json()["detail"] == "Поле dry_run в теле запроса должно быть логическим значением true или false."
        broken = await client.post("/v1/glossary/releases", headers=HEADERS, content=b"{")
        assert broken.status_code == 400, broken.text
        assert broken.json()["detail"] == "Тело запроса не является корректным JSON."
        array = await client.post("/v1/glossary/releases", headers=HEADERS, content=b"[]")
        assert array.status_code == 400, array.text
        assert array.json()["detail"] == "Тело запроса должно быть JSON-объектом."
        state, etag = await _state(client)
        assert state["seq"] == 1

        made = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": etag},
            params={"dry_run": "false"},
            json={"ops": [_PREF]},
        )
        assert made.status_code == 200, made.text
        assert made.json()["version"]
        state, _etag = await _state(client)
        assert state["seq"] == 2


async def test_dry_run_query_changes_the_idempotency_key(app):
    async with _client(app) as client:
        _body, etag = await _state(client)
        headers = {**HEADERS, "If-Match": etag, "Idempotency-Key": "dry-1"}
        preview = await client.post(
            "/v1/glossary/releases",
            headers=headers,
            params={"dry_run": "true"},
            json={"ops": [_PREF]},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["dry_run"] is True
        replay = await client.post(
            "/v1/glossary/releases",
            headers=headers,
            params={"dry_run": "true"},
            json={"ops": [_PREF]},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == preview.json()
        state, etag = await _state(client)
        assert state["seq"] == 1

        clash = await client.post(
            "/v1/glossary/releases",
            headers=headers,
            params={"dry_run": "false"},
            json={"ops": [_PREF]},
        )
        assert clash.status_code == 422, clash.text
        assert clash.json()["code"] == "idempotency_key_reused"
        denied = await client.post(
            "/v1/glossary/releases",
            headers=headers,
            params={"dry_run": "false"},
            json={"ops": [_PREF], "dry_run": True},
        )
        assert denied.status_code == 400, denied.text
        assert denied.json()["code"] == "invalid_argument"
        state, _etag = await _state(client)
        assert state["seq"] == 1
