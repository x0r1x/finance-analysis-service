"""Релизы глоссария, профили и предложения. JSON релиза — источник, без parquet терминов."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime

import yaml
from ulid import ULID

from finance_analysis.application.catalog import load_git_document
from finance_analysis.domain.book import canonical_json, sha256_bytes
from finance_analysis.domain.errors import (
    AlreadyExists,
    GlossaryRegression,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    PreconditionRequired,
    ProposalDecided,
    StaleParent,
)
from finance_analysis.domain.glossary import normalize_label
from finance_analysis.domain.glossary_release import (
    apply_ops,
    label_diff,
    package_of,
    version_for,
)
from finance_analysis.domain.ids import profile_id as check_profile
from finance_analysis.domain.mapping import label_id

HEAD = "glossary/_head.json"
PROPOSALS = "glossary/proposals.json"
INDEX = "glossary/_label_index.json"
_PROFILE_FIELDS = frozenset({"sign_convention", "marker_class"})
_SIGNS = frozenset({"outflow_negative", "outflow_positive"})
_MARKERS = frozenset({None, "actual", "plan"})
PROPOSAL_TYPES = frozenset({"synonym_of", "new_concept_under", "not_a_concept", "book_local"})
_ORIGIN = {"git_base": "base_git", "auto": "auto"}


def _dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text.startswith("W/"):
        text = text[2:].strip()
    return text.strip('"') or None


def state_of(head: dict) -> dict:
    return {
        "seq": head["seq"],
        "active": head["active"],
        "previous": head.get("previous"),
        "canary": head.get("canary"),
        "canary_share": head.get("canary_share"),
        "pending": head.get("pending"),
        "base_git_sha": head.get("base_git_sha"),
        "fence": head.get("fence"),
        "etag": f"h-{head['seq']}",
        "history": list(head.get("history") or []),
    }


class GlossaryStore:
    def __init__(self, store, support=None, *, lock_ttl_ms: int = 15_000) -> None:
        self.store = store
        self.support = support
        self.lock_ttl_ms = lock_ttl_ms
        self._lock = asyncio.Lock()
        # Shadow-гейт (§5.11.3): async (version) -> отчёт с passed. Ставит composition root.
        self.gate = None

    async def peek(self) -> dict | None:
        head, _etag = await self._read()
        return head

    async def ensure(self) -> dict:
        async with self._lock:
            head, etag = await self._read()
            if head is not None:
                return head
            return await self._publish_git(etag)

    async def release(
        self,
        ops: list,
        if_match: str | None,
        *,
        dry_run: bool = False,
        source: str = "api",
        document: dict | None = None,
    ) -> dict:
        if document is not None and ops:
            raise InvalidArgument("replace не сочетается с ops")
        if not isinstance(ops, list):
            raise InvalidArgument("ops должен быть списком")
        if document is not None and not isinstance(document, dict):
            raise InvalidArgument("document должен быть объектом")
        async with self._lock:
            head, etag = await self._ensure_locked()
            self._match(head, if_match)
            parent = head["active"]
            current = await self._document(parent)
            if document is not None:
                package_of(document)
                updated = document
            else:
                updated = apply_ops(current, ops) if ops else current
            diff = label_diff(current, updated)
            if dry_run:
                return {"dry_run": True, "diff": diff, "state": state_of(head)}
            return await self._commit(head, etag, updated, ops, parent=parent, source=source, diff=diff, activate=False)

    async def transition(
        self,
        version: str | None,
        status: str,
        if_match: str | None,
        *,
        force: bool = False,
        reason: str | None = None,
    ) -> dict:
        if status != "active":
            raise InvalidArgument("переход только в active")
        if not version:
            raise InvalidArgument("нужна version")
        if force and not (isinstance(reason, str) and reason.strip()):
            raise InvalidArgument("force требует reason")
        async with self._lock:
            head, etag = await self._ensure_locked()
            self._match(head, if_match)
            report = None
            if version != head.get("previous"):
                report = await self._shadow(version)
                if report is not None and not report.get("passed") and not force:
                    raise GlossaryRegression(
                        "доля ложных привязок выросла или покрытие упало",
                        extra={"version": version, "shadow": _shadow_summary(report)},
                    )
            result = await self._activate(head, etag, version, forced={"reason": reason} if force else None)
            if report is not None:
                result["shadow"] = _shadow_summary(report)
            return result

    async def _shadow(self, version: str) -> dict | None:
        if self.gate is None:
            return None
        return await self.gate(version)

    async def shadow_report(self, version: str) -> dict:
        try:
            return json.loads(await self.store.get(f"glossary/releases/{version}/shadow.json"))
        except NotFound:
            raise NotFound("shadow-отчёта нет") from None

    async def rollback(self, if_match: str | None) -> dict:
        async with self._lock:
            head, etag = await self._ensure_locked()
            previous = head.get("previous")
            if not previous:
                raise InvalidArgument("откатывать некуда")
            self._match(head, if_match)
            return await self._activate(head, etag, previous, source="rollback")

    async def releases(self) -> dict:
        head = await self.ensure()
        return {"releases": state_of(head)["history"], "state": state_of(head)}

    async def release_view(self, version: str) -> dict:
        record = await self._release_record(version)
        try:
            shadow = _shadow_summary(await self.shadow_report(version))
        except NotFound:
            shadow = None
        return {"release": record, "shadow": shadow, "state": state_of(await self.ensure())}

    async def events(self) -> dict:
        rows = []
        async for item in self.store.list("glossary/events/"):
            if item.key.endswith(".json"):
                rows.append(json.loads(await self.store.get(item.key)))
        rows.sort(key=lambda row: row["seq"])
        return {"events": rows, "state": state_of(await self.ensure())}

    async def diff(self, source: str | None, target: str | None) -> dict:
        head = await self.ensure()
        left = source or head.get("previous") or head["active"]
        right = target or head["active"]
        changes = label_diff(await self._document(left), await self._document(right))
        return {"from": left, "to": right, "diff": changes, "state": state_of(head)}

    async def concepts(self) -> dict:
        document = await self._active_document()
        names = sorted(str(name) for name in (document.get("concepts") or {}))
        return {"concepts": names, "state": state_of(await self.ensure())}

    async def composition(self, version: str | None) -> dict[str, tuple[str, ...]]:
        """Состав понятий (`composition`, §5.1) релиза, с которым построено состояние книги."""

        try:
            document = await self._document(version) if version else await self._active_document()
        except NotFound:
            document = await self._active_document()
        concepts = package_of(document).concepts
        return {name: concept.composition for name, concept in concepts.items() if concept.composition}

    async def list_profiles(self) -> dict:
        found = []
        async for item in self.store.list("profiles/"):
            if not item.key.endswith("/_head.json"):
                continue
            saved = json.loads(await self.store.get(item.key))
            found.append({"id": saved["id"], "etag": saved["etag"]})
        found.sort(key=lambda row: row["id"])
        return {"profiles": found}

    async def content(self, version: str | None, fmt: str) -> tuple[bytes, str]:
        if fmt not in {"json", "yaml"}:
            from finance_analysis.domain.errors import NotAcceptable

            raise NotAcceptable("формат json или yaml", extra={"formats": ["json", "yaml"]})
        head = await self.ensure()
        chosen = version or head["active"]
        document = await self._document(chosen)
        if fmt == "yaml":
            return yaml.safe_dump(document, allow_unicode=True, sort_keys=True).encode(), "application/yaml"
        return canonical_json(document).encode(), "application/json"

    async def resolve(self, text: str) -> dict:
        package = package_of(await self._active_document())
        hit = package.resolve(text)
        if hit is None:
            return {"match": None}
        return {"match": {"concept": hit.concept, "kind": hit.kind, "text": hit.text}}

    async def labels(self, query: str) -> dict:
        document = await self._active_document()
        provenance = await self._active_provenance()
        needle = normalize_label(query)
        found = []
        for concept, glossary in (document.get("glossaries") or {}).items():
            for kind in ("pref", "alt", "hidden"):
                bucket = glossary.get(kind) or {}
                if not isinstance(bucket, dict):
                    continue
                for lang, value in bucket.items():
                    texts = [value] if isinstance(value, str) else list(value or [])
                    for text in texts:
                        if needle and needle not in normalize_label(str(text)):
                            continue
                        ident = label_id(concept, kind, str(text))
                        found.append(
                            {"concept": concept, "kind": kind, "lang": lang, "text": text, "id": ident, "provenance": provenance.get(ident)}
                        )
        return {"labels": found}

    async def _active_provenance(self) -> dict:
        head, _etag = await self._read()
        if head is None:
            return {}
        try:
            return dict((await self._release_record(head["active"])).get("provenance") or {})
        except NotFound:
            return {}

    async def impact(self) -> dict:
        # shortcut: книги не сканируются, влияние пустое до отдельного индекса читателей
        return {"books": []}

    async def export_patch(self) -> str:
        git = load_git_document()
        head, _etag = await self._read()
        current = git if head is None else await self._document(head["active"])
        return yaml.safe_dump({"changes": label_diff(git, current)}, allow_unicode=True, sort_keys=False)

    async def active_document(self) -> dict:
        return await self._active_document()

    async def document(self, version: str) -> dict:
        return await self._document(version)

    async def put_profile(self, profile: str, body: dict, *, if_match: str | None, if_none_match: str | None) -> dict:
        check_profile(profile)
        if not isinstance(body, dict):
            raise InvalidArgument("тело профиля должно быть объектом")
        extra = set(body) - _PROFILE_FIELDS
        if extra:
            raise InvalidArgument("в профиле только sign_convention и marker_class", extra={"fields": sorted(extra)})
        if "sign_convention" in body and body["sign_convention"] not in _SIGNS:
            raise InvalidArgument("sign_convention: outflow_negative или outflow_positive")
        if "marker_class" in body and body["marker_class"] not in _MARKERS:
            raise InvalidArgument("marker_class: null, actual или plan")
        async with self._lock:
            current, etag = await self._profile(profile)
            if _token(if_none_match) == "*":
                if current is not None:
                    raise PreconditionFailed("профиль уже есть", extra={"etag": f"p-{current['seq']}"})
                saved = {"sign_convention": body.get("sign_convention", "outflow_negative"), "marker_class": body.get("marker_class")}
                return await self._write_profile(profile, 1, saved, etag)
            if current is None or not if_match:
                raise PreconditionRequired("нужен If-Match или If-None-Match: *")
            if _token(if_match) != f"p-{current['seq']}":
                raise PreconditionFailed("If-Match профиля не совпал", extra={"etag": f"p-{current['seq']}", "profile": current})
            saved = {
                "sign_convention": body.get("sign_convention", current["body"]["sign_convention"]),
                "marker_class": body["marker_class"] if "marker_class" in body else current["body"]["marker_class"],
            }
            return await self._write_profile(profile, int(current["seq"]) + 1, saved, etag)

    async def profile_ref(self, profile: str) -> str | None:
        current, _etag = await self._profile(profile)
        if current is None:
            return None
        return f"{profile}@p-{current['seq']}"

    async def profile_body(self, profile: str) -> dict | None:
        current, _etag = await self._profile(profile)
        if current is None:
            return None
        return current["body"]

    async def add_proposal(self, body: dict) -> dict:
        """Предложение в очередь ревью (§5.10.4). Открытое с тем же ключом обновляется, а не дублируется."""

        if not isinstance(body, dict):
            raise InvalidArgument("предложение должно быть объектом")
        kind_of = body.get("type") or "synonym_of"
        if kind_of not in PROPOSAL_TYPES:
            raise InvalidArgument("type: synonym_of, new_concept_under, not_a_concept или book_local")
        concept = body.get("concept")
        kind = body.get("kind") or ("alt" if kind_of == "synonym_of" else None)
        lang = body.get("lang")
        text = body.get("text")
        if kind_of == "synonym_of" and (
            kind not in {"pref", "alt", "hidden"} or not isinstance(concept, str) or not isinstance(lang, str) or not isinstance(text, str)
        ):
            raise InvalidArgument("предложение: concept, kind, lang, text")
        if kind_of != "synonym_of" and not isinstance(text, str):
            raise InvalidArgument("предложение: нужен text")
        dedupe = body.get("cluster_id") or "|".join([kind_of, str(concept), str(kind), str(lang), normalize_label(str(text))])
        async with self._lock:
            items, etag = await self._proposals()
            current = next(
                (item for item in items.values() if item.get("status") == "open" and item.get("dedupe") == dedupe),
                None,
            )
            proposal = {
                "id": current["id"] if current else str(ULID()),
                "status": "open",
                "type": kind_of,
                "concept": concept,
                "kind": kind,
                "lang": lang,
                "text": text,
                "origin": str(body.get("origin") or "api"),
                "dedupe": dedupe,
                "created_at_utc": current["created_at_utc"] if current else _now(),
                "updated_at_utc": _now(),
            }
            for extra in ("cluster_id", "labels", "draft", "clm", "impact", "evidence", "books", "broader", "examples"):
                if extra in body:
                    proposal[extra] = body[extra]
            items[proposal["id"]] = proposal
            await self._write_json(PROPOSALS, {"items": items}, etag)
        return proposal

    async def proposals(self, *, status: str | None = None, order_by: str | None = None) -> dict:
        items, _etag = await self._proposals()
        rows = [item for item in items.values() if status is None or item.get("status") == status]
        if order_by == "impact":
            rows.sort(key=lambda item: (-float(item.get("impact") or 0.0), item["id"]))
        else:
            rows.sort(key=lambda item: item["id"])
        return {"proposals": rows}

    async def proposal(self, proposal_id: str) -> dict:
        items, _etag = await self._proposals()
        found = items.get(proposal_id)
        if found is None:
            raise NotFound("предложение не найдено")
        return found

    async def decide_proposals(self, decisions: list) -> dict:
        if not isinstance(decisions, list):
            raise InvalidArgument("decisions должен быть списком")
        async with self._lock:
            items, etag = await self._proposals()
            accepted_ops = []
            results = []
            chosen = []
            for index, item in enumerate(decisions):
                if not isinstance(item, dict):
                    raise InvalidArgument("элемент решения не объект")
                found = items.get(item.get("id"))
                if found is None:
                    raise NotFound("предложение не найдено")
                if found["status"] != "open":
                    raise ProposalDecided("предложение уже решено", extra={"id": found["id"]})
                choice = item.get("decision")
                if choice not in {"accept", "reject"}:
                    raise InvalidArgument("decision: accept или reject")
                text = item["text"] if isinstance(item.get("text"), str) and item["text"] else found["text"]
                concept = item["concept"] if isinstance(item.get("concept"), str) and item["concept"] else found.get("concept")
                chosen.append((index, found, choice, text))
                if choice == "accept":
                    accepted_ops.append(_proposal_op({**found, "concept": concept}, text))
            release = None
            shadow = None
            if accepted_ops:
                head, head_etag = await self._ensure_locked()
                document = await self._document(head["active"])
                updated = apply_ops(document, accepted_ops)
                diff = label_diff(document, updated)
                origin = "auto" if all(found.get("origin") == "auto" for _i, found, c, _t in chosen if c == "accept") else "review"
                ready = await self._commit(
                    head, head_etag, updated, accepted_ops, parent=head["active"], source="proposal", diff=diff, activate=False,
                    origin=origin, proposals=[found["id"] for _i, found, c, _t in chosen if c == "accept"],
                )
                report = await self._shadow(ready["version"])
                if report is not None:
                    shadow = _shadow_summary(report)
                if report is None or report.get("passed"):
                    fresh, fresh_etag = await self._read()
                    release = await self._activate(fresh, fresh_etag, ready["version"], source="proposal")
                else:
                    release = {**ready, "activated": False}
            blocked = release is not None and release.get("activated") is False
            for index, found, choice, text in chosen:
                if choice == "accept" and blocked:
                    # Гейт не пустил релиз: предложение остаётся открытым, решение можно повторить.
                    found["blocked_release"] = release["version"]
                    results.append({"index": index, "id": found["id"], "status": "open", "blocked": "glossary_regression"})
                    continue
                found["text"] = text
                found["status"] = "accepted" if choice == "accept" else "rejected"
                found["decided_at_utc"] = _now()
                results.append({"index": index, "id": found["id"], "status": found["status"]})
            await self._write_json(PROPOSALS, {"items": items}, etag)
        return {
            "results": results,
            "release": release,
            "shadow": shadow,
            "rejected": [found for _i, found, choice, _t in chosen if choice == "reject"],
        }

    async def note_bindings(self, job_id: str, bindings: list[dict]) -> None:
        async with self._lock:
            try:
                raw = await self.store.get(INDEX)
                index = json.loads(raw)
                etag = (await self.store.stat(INDEX)).etag
            except NotFound:
                index, etag = {"labels": {}}, None
            labels = index.setdefault("labels", {})
            for key, rows in list(labels.items()):
                labels[key] = [row for row in rows if row.get("job_id") != job_id]
                if not labels[key]:
                    del labels[key]
            for row in bindings:
                label = row.get("matched_label_id")
                if not label or row.get("source") == "confirmed":
                    continue
                labels.setdefault(str(label), []).append({"job_id": job_id, "binding_key": row.get("binding_key")})
            await self._write_json(INDEX, index, etag)

    async def jobs(self) -> list[str]:
        found = set()
        try:
            index = json.loads(await self.store.get(INDEX))
        except NotFound:
            index = {}
        for rows in (index.get("labels") or {}).values():
            for row in rows:
                if row.get("job_id"):
                    found.add(row["job_id"])
        async for item in self.store.list("books/"):
            parts = item.key.split("/")
            if len(parts) == 3 and parts[0] == "books" and parts[2] == "_head.json":
                found.add(parts[1])
        return sorted(found)

    async def _active_document(self) -> dict:
        head, _etag = await self._read()
        if head is None:
            return load_git_document()
        return await self._document(head["active"])

    async def _ensure_locked(self) -> tuple[dict, str | None]:
        head, etag = await self._read()
        if head is None:
            await self._publish_git(etag)
            head, etag = await self._read()
        return head, etag

    async def _publish_git(self, etag: str | None) -> dict:
        document = load_git_document()
        digest = sha256_bytes(canonical_json(document).encode())
        version = version_for(1, document)
        release = {
            "version": version,
            "parent_version": None,
            "base_git_sha": digest,
            "ops": [],
            "source": "git_base",
            "status": "active",
            "seq": 1,
            "provenance": provenance_of(
                label_diff({"glossaries": {}}, document), {}, origin="base_git", seq=1, version=version, proposals=None
            ),
        }
        await self._put_release(version, release, document)
        await self._event(1, {"type": "release", "version": version, "source": "git_base"})
        head = {
            "seq": 1,
            "active": version,
            "previous": None,
            "canary": None,
            "canary_share": None,
            "pending": None,
            "base_git_sha": digest,
            "fence": 1,
            "history": [{"version": version, "status": "active", "parent_version": None, "source": "git_base", "seq": 1}],
        }
        await self._write_head(head, etag)
        await self._notify(version)
        return head

    async def _commit(
        self,
        head: dict,
        etag: str | None,
        document: dict,
        ops: list,
        *,
        parent: str,
        source: str,
        diff: list,
        activate: bool,
        origin: str | None = None,
        proposals: list[str] | None = None,
    ) -> dict:
        seq = int(head["seq"]) + 1
        version = version_for(seq, document)
        try:
            inherited = dict((await self._release_record(parent)).get("provenance") or {})
        except NotFound:
            inherited = {}
        release = {
            "version": version,
            "parent_version": parent,
            "base_git_sha": head.get("base_git_sha"),
            "ops": ops,
            "source": source,
            "status": "active" if activate else "ready",
            "seq": seq,
            "provenance": provenance_of(
                diff, inherited, origin=origin or _ORIGIN.get(source, "review"), seq=seq, version=version, proposals=proposals
            ),
        }
        await self._put_release(version, release, document)
        await self._event(seq, {"type": "release", "version": version, "source": source})
        history = list(head.get("history") or [])
        history.append(
            {"version": version, "status": release["status"], "parent_version": parent, "source": source, "seq": seq}
        )
        updated = {
            **head,
            "seq": seq,
            "pending": None if activate else version,
            "fence": int(head.get("fence") or 0) + 1,
            "history": history,
        }
        if activate:
            updated["previous"] = head["active"]
            updated["active"] = version
        await self._write_head(updated, etag)
        if activate:
            await self._notify(version)
        return {"version": version, "status": release["status"], "diff": diff, "state": state_of(updated), "etag": f"h-{seq}"}

    async def _activate(
        self, head: dict, etag: str | None, version: str, *, source: str = "activate", forced: dict | None = None
    ) -> dict:
        record = await self._release_record(version)
        parent = record.get("parent_version")
        rollback = version == head.get("previous")
        if not rollback and parent != head["active"]:
            raise StaleParent("родитель релиза не активен", extra={"parent": parent, "active": head["active"], "state": state_of(head)})
        history = []
        for item in head.get("history") or []:
            row = dict(item)
            if row.get("version") == head["active"] and row.get("status") == "active":
                row["status"] = "retired"
            if row.get("version") == version:
                row["status"] = "active"
            history.append(row)
        seq = int(head["seq"]) + 1
        history.append({"version": version, "status": "active", "parent_version": parent, "source": source, "seq": seq})
        record["status"] = "active"
        await self.store.put(self._release_key(version), _dumps(record))
        updated = {
            **head,
            "seq": seq,
            "active": version,
            "previous": head["active"],
            "pending": None,
            "fence": int(head.get("fence") or 0) + 1,
            "history": history,
        }
        event = {"type": source, "version": version}
        if forced:
            event["force"] = True
            event["reason"] = forced.get("reason")
        await self._event(seq, event)
        await self._write_head(updated, etag)
        await self._notify(version)
        return {"version": version, "status": "active", "state": state_of(updated), "etag": f"h-{seq}"}

    def _match(self, head: dict, if_match: str | None) -> None:
        token = _token(if_match)
        if token is None:
            raise PreconditionRequired("нужен If-Match")
        current = f"h-{head['seq']}"
        if token != current:
            raise PreconditionFailed("If-Match не совпал", extra={"state": state_of(head), "etag": current})

    async def _read(self) -> tuple[dict | None, str | None]:
        try:
            raw = await self.store.get(HEAD)
        except NotFound:
            return None, None
        meta = await self.store.stat(HEAD)
        return json.loads(raw), None if meta is None else meta.etag

    async def _write_head(self, head: dict, etag: str | None) -> None:
        data = _dumps(head)
        try:
            if etag is None:
                await self.store.put_if_absent(HEAD, data)
            else:
                await self.store.put_if_match(HEAD, data, etag)
        except AlreadyExists:
            raise PreconditionFailed("голова глоссария уже создана") from None
        except PreconditionFailed:
            fresh, _token = await self._read()
            extra = {"state": state_of(fresh)} if fresh else {}
            raise PreconditionFailed("голова глоссария изменилась", extra=extra) from None

    async def _document(self, version: str) -> dict:
        try:
            return json.loads(await self.store.get(f"glossary/releases/{version}/glossary.json"))
        except NotFound:
            raise NotFound("релиз не найден") from None

    async def _release_record(self, version: str) -> dict:
        try:
            return json.loads(await self.store.get(self._release_key(version)))
        except NotFound:
            raise NotFound("релиз не найден") from None

    def _release_key(self, version: str) -> str:
        return f"glossary/releases/{version}/release.json"

    async def _put_release(self, version: str, release: dict, document: dict) -> None:
        await self.store.put_if_absent(f"glossary/releases/{version}/glossary.json", canonical_json(document).encode())
        await self.store.put_if_absent(self._release_key(version), _dumps(release))

    async def _event(self, seq: int, payload: dict) -> None:
        body = {"seq": seq, "at_utc": _now(), **payload}
        try:
            await self.store.put_if_absent(f"glossary/events/{seq:020d}.json", _dumps(body))
        except AlreadyExists:
            return

    async def _notify(self, version: str) -> None:
        if self.support is None:
            return
        await self.support.publish("fas:glossary:changed", version)
        await self.support.cache_set("fas:glossary:version", version.encode(), 86_400)

    async def _profile(self, profile: str) -> tuple[dict | None, str | None]:
        key = f"profiles/{profile}/_head.json"
        try:
            raw = await self.store.get(key)
        except NotFound:
            return None, None
        meta = await self.store.stat(key)
        return json.loads(raw), None if meta is None else meta.etag

    async def _write_profile(self, profile: str, seq: int, body: dict, etag: str | None) -> dict:
        text = yaml.safe_dump(body, allow_unicode=True, sort_keys=True).encode()
        await self.store.put(f"profiles/{profile}/v/{seq:06d}.yaml", text)
        saved = {"id": profile, "seq": seq, "etag": f"p-{seq}", "body": body}
        key = f"profiles/{profile}/_head.json"
        data = _dumps(saved)
        if etag is None:
            await self.store.put_if_absent(key, data)
        else:
            await self.store.put_if_match(key, data, etag)
        return saved

    async def _proposals(self) -> tuple[dict, str | None]:
        try:
            raw = await self.store.get(PROPOSALS)
        except NotFound:
            return {}, None
        meta = await self.store.stat(PROPOSALS)
        payload = json.loads(raw)
        return dict(payload.get("items") or {}), None if meta is None else meta.etag

    async def _write_json(self, key: str, payload: dict, etag: str | None) -> None:
        data = _dumps(payload)
        if etag is None:
            try:
                await self.store.put_if_absent(key, data)
            except AlreadyExists:
                meta = await self.store.stat(key)
                await self.store.put_if_match(key, data, meta.etag)
        else:
            await self.store.put_if_match(key, data, etag)


def provenance_of(
    diff: list[dict], inherited: dict, *, origin: str, seq: int, version: str, proposals: list[str] | None
) -> dict:
    """Провенанс меток (§5.11.3): родитель ⊕ diff. Удалённые метки уходят, добавленные получают origin."""

    out = dict(inherited)
    for change in diff:
        ident = label_id(change["concept"], change["kind"], change["text"])
        if change["change"] == "remove":
            out.pop(ident, None)
            continue
        out[ident] = {
            "origin": origin,
            "event_seq": seq,
            "proposal_id": (proposals or [None])[0] if proposals and len(proposals) == 1 else None,
            "proposals": list(proposals or []),
            "promoted_in": version,
        }
    return out


def _proposal_op(found: dict, text: str) -> dict:
    kind_of = found.get("type") or "synonym_of"
    if kind_of == "synonym_of":
        op = "set_pref" if found["kind"] == "pref" else "add_label"
        return {"op": op, "concept": found["concept"], "kind": found["kind"], "lang": found["lang"], "text": text}
    if kind_of == "not_a_concept" and isinstance(found.get("concept"), str):
        return {"op": "add_negative", "concept": found["concept"], "text": text}
    raise InvalidArgument(
        "новое понятие и метки профиля принимаются только релизом администратора",
        extra={"id": found["id"], "type": kind_of},
    )


def _shadow_summary(report: dict) -> dict:
    return {key: report.get(key) for key in ("passed", "reasons", "eval", "books", "path")}


def git_base_sha() -> str:
    return hashlib.sha256(canonical_json(load_git_document()).encode()).hexdigest()
