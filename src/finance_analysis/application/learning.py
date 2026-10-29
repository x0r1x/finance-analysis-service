"""Рост глоссария из потока книг (§5.10.4, §5.11): сигналы, unmapped/, кластеры, предложения, glossary_mine.

По умолчанию glossary_mine только пишет предложения. При GLOSSARY_AUTO_PROMOTE=true метка профиля
или глобальный alt без конфликта идёт в один релиз и останавливается на canary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from ulid import ULID

from finance_analysis.application import keys
from finance_analysis.application.examples import (
    AppendOnlyParquet,
    pack_vector,
    unpack_vector,
)
from finance_analysis.application.mapping_pipeline import few_shot_state
from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.errors import (
    GlossaryRegression,
    InvalidArgument,
    ModelDegraded,
    NotFound,
    PreconditionFailed,
    StaleParent,
)
from finance_analysis.domain.glossary import normalize_label
from finance_analysis.domain.glossary_release import canary_verdict, label_diff
from finance_analysis.domain.signals import (
    STRONG_AGAINST,
    WEIGHTS,
    LabelingInput,
    MineThresholds,
    lf_accuracy,
    mine,
)
from finance_analysis.plugins.labeling import run_all

IMPORTANCE_WEIGHT = {"critical": 4.0, "component": 2.0, "material": 1.5, "peripheral": 1.0, "normal": 1.0}
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_HUMAN_KINDS = {"concept.confirmed": "confirmed", "concept.set": "set", "concept.rejected": "rejected", "concept.ignored": "ignored", "concept.absent": "absent"}


def lang_of(text: str) -> str:
    return "ru" if _CYRILLIC.search(text or "") else "en"


def _signal(job_id: str, profile: str | None, key: str | None, label: str, concept: str | None, polarity: str, kind: str, **extra) -> dict:
    return {
        "signal_id": str(ULID()),
        "job_id": job_id,
        "profile_id": profile,
        "binding_key": key,
        "label_norm": normalize_label(label).strip(),
        "label_text": label,
        "lang": lang_of(label),
        "concept": concept,
        "polarity": polarity,
        "kind": kind,
        "weight": WEIGHTS[kind],
        "at_utc": datetime.now(UTC),
        **extra,
    }


class Learning:
    def __init__(self, store, parquet, glossary, examples, models, cluster, settings) -> None:
        self.store = store
        self.parquet = parquet
        self.glossary = glossary
        self.examples = examples
        self.models = models
        self.cluster = cluster
        self.settings = settings
        model = getattr(models.embed, "model", "") or "none"
        self.signals = AppendOnlyParquet(store, parquet, dataset="signals", prefix="glossary/signals/", sort_key="signal_id")
        self.unmapped = AppendOnlyParquet(store, parquet, dataset="unmapped", prefix=f"unmapped/{model}/", sort_key="unmapped_id")
        self.embed_model = model

    # --- сигналы людей и examples/ -------------------------------------------------------

    async def record_decisions(
        self,
        job_id: str,
        records: list[dict],
        *,
        rows: dict[str, dict],
        bindings: dict[str, dict],
        events: list[dict],
        profile: str | None,
        glossary_version: str,
        package,
    ) -> dict:
        """Принятые guard решения → сигналы S и примеры (§4.5, §5.11.1). Решения по книге целиком пропускаются."""

        signals: list[dict] = []
        examples: list[dict] = []
        by_seq = {int(event["seq"]): event for event in events if isinstance(event.get("seq"), int)}
        texts: list[str] = []
        for record in records:
            kind = record.get("type")
            key = record.get("binding_key")
            if kind not in _HUMAN_KINDS or not key or key == "book" or key not in rows:
                continue
            row = rows[key]
            label = str(row.get("label") or "")
            concept = record.get("value") if isinstance(record.get("value"), str) else None
            actor = (record.get("actor") or {}).get("user_id")
            ref = f"{job_id}:{record.get('seq')}"
            current = bindings.get(key) or {}
            before = current.get("effective_concept")
            common = {"actor": actor, "evidence_ref": ref, "glossary_version": glossary_version}
            if kind == "concept.confirmed" and concept:
                signals.append(_signal(job_id, profile, key, label, concept, "+", "human.confirmed", **common))
            elif kind == "concept.set" and concept:
                corrected = before and before != concept
                signals.append(_signal(job_id, profile, key, label, concept, "+", "human.corrected" if corrected else "human.confirmed", **common))
                if corrected:
                    signals.append(_signal(job_id, profile, key, label, before, "-", "human.rejected", **common))
            elif kind == "concept.rejected" and concept:
                signals.append(_signal(job_id, profile, key, label, concept, "-", "human.rejected", **common))
            elif kind == "concept.ignored":
                signals.append(_signal(job_id, profile, key, label, before, "-", "concept.ignored", **common))
            evidence = json.loads(current.get("evidence_json") or "{}")
            examples.append(
                {
                    "job_id": job_id,
                    "binding_key": key,
                    "seq": int(record.get("seq") or 0),
                    "kind": _HUMAN_KINDS[kind],
                    "concept": concept or before,
                    "path_text": str(row.get("label_path_text") or label),
                    "label_norm": normalize_label(label).strip(),
                    "candidates_json": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    "profile_id": profile,
                    "glossary_version": glossary_version,
                }
            )
            texts.append(str(row.get("label_path_text") or label))
            superseded = (record.get("supersedes") or {}).get("seq") if isinstance(record.get("supersedes"), dict) else record.get("supersedes_seq")
            old = by_seq.get(int(superseded)) if isinstance(superseded, int) else None
            if old and old.get("binding_key") and old.get("binding_key") != key:
                examples.append(
                    {
                        "job_id": job_id,
                        "binding_key": old["binding_key"],
                        "seq": int(record.get("seq") or 0),
                        "kind": "superseded",
                        "concept": old.get("value") if isinstance(old.get("value"), str) else None,
                        "path_text": str((rows.get(old["binding_key"]) or {}).get("label_path_text") or ""),
                        "label_norm": "",
                        "candidates_json": "{}",
                        "profile_id": profile,
                        "glossary_version": glossary_version,
                    }
                )
                texts.append("")
            if kind in {"concept.confirmed", "concept.set"} and concept and package.resolve(label) is None and label.strip():
                # Метки нет в глоссарии → предложение synonym_of с готовой меткой, без LLM (§5.10.4 п. 7).
                known = [package.concepts[concept].pref.get(lang, "") for lang in ("ru", "en")] if concept in package.concepts else []
                from finance_analysis.domain.signals import lexical_relation

                await self.glossary.add_proposal(
                    {
                        "type": "synonym_of",
                        "concept": concept,
                        "kind": lexical_relation(label, known),
                        "lang": lang_of(label),
                        "text": label,
                        "origin": "decision",
                        "books": 1,
                        "evidence": {"job_id": job_id, "binding_key": key, "seq": record.get("seq")},
                    }
                )
        vectors = await self._embed_or_none(texts)
        for example, vector in zip(examples, vectors, strict=True):
            example["embedding"] = vector
        if examples:
            await self.examples.append(examples)
        await self._signals(signals)
        return {"signals": len(signals), "examples": len(examples)}

    async def proposals_rejected(self, rejected: list[dict]) -> None:
        """reject → сигнал proposal.rejected: метка уходит в обучающий набор NIL (§5.10.4 п. 6)."""

        rows = []
        for item in rejected:
            text = str(item.get("text") or "")
            if not text:
                continue
            rows.append(
                _signal(
                    "glossary", None, None, text, item.get("concept"), "-", "proposal.rejected", actor=None, evidence_ref=f"proposal:{item.get('id')}", glossary_version=None
                )
            )
        await self._signals(rows)

    async def _signals(self, rows: list[dict]) -> None:
        if rows:
            await self.signals.append(rows, sub=datetime.now(UTC).strftime("%Y-%m-%d/"))

    async def _embed_or_none(self, texts: list[str]) -> list[list[float] | None]:
        if self.models.embed is None or not any(texts):
            return [None for _ in texts]
        try:
            vectors = await self.models.embed.embed([text or "-" for text in texts], deadline=Deadline.after_ms(self.settings.embed_timeout_sec * 1000 * 2))
        except ModelDegraded:
            return [None for _ in texts]
        return [vector if text else None for vector, text in zip(vectors, texts, strict=True)]

    # --- после привязки: LF и unmapped/ ---------------------------------------------------

    async def after_derive(
        self,
        job_id: str,
        *,
        prepared: list[dict],
        bindings: list[dict],
        facts: list[dict],
        links: list[dict],
        embeddings: dict[str, list[float]],
        nearest: dict[str, str | None],
        package,
        glossary_version: str,
        profile: str | None,
        identities: dict[str, list[str]],
    ) -> dict:
        data = labeling_input(prepared, bindings, facts, links, package, identities)
        votes = run_all(data)
        rows = {row["binding_key"]: row for row in prepared}
        signals = [
            _signal(
                job_id, profile, vote.binding_key, str(rows[vote.binding_key].get("label") or ""), vote.concept, vote.polarity, vote.kind,
                actor="system:lf", evidence_ref=f"{job_id}:lf", glossary_version=glossary_version,
            )
            for vote in votes
            if vote.binding_key in rows and str(rows[vote.binding_key].get("label") or "").strip()
        ]
        await self._signals(signals)
        totals = _abs_by_row(facts)
        grand = sum(totals.values()) or Decimal(0)
        unknown = []
        now = datetime.now(UTC)
        for binding in bindings:
            if binding.get("status") != "unknown" or binding.get("source") != "inferred":
                continue
            row = rows.get(binding["binding_key"]) or {}
            label = str(row.get("label") or "")
            if not label.strip():
                continue
            share = float(totals.get(row.get("row_key"), Decimal(0)) / grand) if grand else None
            unknown.append(
                {
                    "unmapped_id": str(ULID()),
                    "job_id": job_id,
                    "binding_key": binding["binding_key"],
                    "path_text": str(row.get("label_path_text") or label),
                    "label_norm": normalize_label(label).strip(),
                    "unit": row.get("unit"),
                    "importance": binding.get("importance") or "peripheral",
                    "value_share": share,
                    "nearest_concept": nearest.get(binding["binding_key"]),
                    "embed_model": self.embed_model,
                    "embedding_f32": pack_vector(embeddings.get(binding["binding_key"])),
                    "glossary_version": glossary_version,
                    "at_utc": now,
                }
            )
        await self.unmapped.append(unknown)
        return {"signals": len(signals), "unmapped": len(unknown)}

    # --- cluster_unmapped (Taskiq, раз в сутки) ------------------------------------------

    async def cluster_unmapped(self, package) -> dict:
        latest: dict[tuple[str, str], dict] = {}
        for row in await self.unmapped.rows():
            key = (row["job_id"], row["binding_key"])
            if key not in latest or row["unmapped_id"] > latest[key]["unmapped_id"]:
                latest[key] = row
        rows = [row for row in latest.values() if package.resolve(row["label_norm"]) is None]
        with_vectors = [row for row in rows if row.get("embedding_f32")]
        groups: dict[str, list[dict]] = defaultdict(list)
        if with_vectors and self.cluster is not None:
            labels = await self.cluster.cluster(
                [unpack_vector(row["embedding_f32"]) for row in with_vectors],
                min_cluster_size=self.settings.unmapped_min_cluster,
            )
            noise = []
            for row, label in zip(with_vectors, labels, strict=True):
                if label >= 0:
                    groups[f"c{label}"].append(row)
                else:
                    noise.append(row)
            # Шум HDBSCAN не навязывается в кластер; одинаковая метка из разных книг — уже группа.
            rest = [row for row in rows if not row.get("embedding_f32")] + noise
        else:
            rest = rows
        for row in rest:
            # Без эмбеддингов кластер — одинаковая нормализованная метка.
            groups[f"l:{row['label_norm']}"].append(row)
        created = []
        for name, members in sorted(groups.items()):
            books = {row["job_id"] for row in members}
            critical = any(row.get("importance") == "critical" for row in members)
            if len(books) < self.settings.propose_min_books and not critical:
                continue
            created.append(await self._propose_cluster(members, package))
        return {"rows": len(rows), "clusters": len(groups), "proposals": len(created)}

    async def _propose_cluster(self, members: list[dict], package) -> dict:
        texts = Counter(row["path_text"].split(" › ")[-1] for row in members)
        top_label = texts.most_common(1)[0][0]
        nearest = Counter(row["nearest_concept"] for row in members if row.get("nearest_concept")).most_common(1)
        concept = nearest[0][0] if nearest else None
        units = Counter(row.get("unit") for row in members if row.get("unit")).most_common(1)
        cluster_id = "u-" + hashlib.sha1("|".join(sorted(f"{r['job_id']}:{r['binding_key']}" for r in members)).encode()).hexdigest()[:10]
        impact = sum(IMPORTANCE_WEIGHT.get(row.get("importance") or "peripheral", 1.0) * float(row.get("value_share") or 0.0) for row in members)
        impact *= len({row["job_id"] for row in members})
        draft = await self._draft(texts, concept, package)
        choice = await self._choose_type(top_label, texts, concept, package)
        kind_of, target = choice["type"], choice.get("concept") or concept
        body = {
            "type": kind_of,
            "concept": target,
            "kind": "alt" if kind_of == "synonym_of" else None,
            "lang": lang_of(top_label),
            "text": top_label,
            "origin": "cluster",
            "cluster_id": cluster_id,
            "labels": [{"text": text, "count": count} for text, count in texts.most_common(20)],
            "books": len({row["job_id"] for row in members}),
            "impact": round(impact, 6),
            "draft": draft,
            "clm": choice.get("clm"),
            "broader": choice.get("broader"),
            "evidence": {"unit": units[0][0] if units else None, "importance": sorted({row.get("importance") for row in members})},
        }
        if kind_of == "synonym_of" and not target:
            body["type"] = "new_concept_under"
        return await self.glossary.add_proposal(body)

    async def _draft(self, texts: Counter, concept: str | None, package) -> dict | None:
        """Черновик LLM: prefLabel ru/en, definition, broader, unit, expected_sign. Только текст."""

        if self.models.llm is None:
            return None
        prompt = (
            "Метки строк финансовых моделей одного кластера: "
            + "; ".join(text for text, _count in texts.most_common(10))
            + (f". Ближайшее понятие таксономии: {concept}." if concept else ".")
            + ' Ответь JSON: {"pref": {"ru": "", "en": ""}, "definition": "", "broader": "", "unit": "", "expected_sign": ""}.'
        )
        try:
            text = await self.models.llm.complete(
                [{"role": "system", "content": "Ты методолог финансовых моделей. Пиши кратко."}, {"role": "user", "content": prompt}],
                deadline=Deadline.after_ms(self.settings.llm_timeout_sec * 1000),
            )
        except ModelDegraded as exc:
            return {"degraded": exc.as_dict()}
        start, end = text.find("{"), text.rfind("}")
        try:
            draft = json.loads(text[start : end + 1]) if start >= 0 else None
        except ValueError:
            draft = None
        return draft if isinstance(draft, dict) else {"text": text[:2000]}

    async def _choose_type(self, label: str, texts: Counter, concept: str | None, package) -> dict:
        """Тип предложения — выбор CLM (§5.10.4 п. 4): сначала синоним, новое понятие — при существенном отличии."""

        broader = None
        if concept and concept in package.concepts:
            broader = package.concepts[concept].broader or concept
        default = {"type": "synonym_of" if concept else "new_concept_under", "concept": concept, "broader": broader}
        if self.models.clm is None:
            return default
        criteria = {
            "not_a_concept": "Служебная строка, флаг или проверка, а не финансовое понятие",
            "book_local": "Понятие только этой модели",
        }
        if concept:
            criteria[f"synonym_of:{concept}"] = f"Синоним понятия {concept}"
        if broader:
            criteria[f"new_concept_under:{broader}"] = f"Новое понятие внутри {broader}"
        question = {"type": {"type": "choice", "instructions": "Что это за метка?", "criteria": criteria}}
        state = f"Метки кластера: {'; '.join(text for text, _c in texts.most_common(8))}"
        state = await self._with_shots(label, state)
        try:
            answer = (await self.models.clm.choose(state, question, deadline=Deadline.after_ms(self.settings.clm_timeout_sec * 1000)))["type"]
        except ModelDegraded:
            return default
        kind_of, _sep, target = answer["choice"].partition(":")
        out = {"type": kind_of, "concept": concept, "broader": broader, "clm": answer}
        if kind_of == "new_concept_under":
            out["broader"] = target or broader
        return out

    # --- glossary_mine (Taskiq, ночью, только режим предложений) -------------------------

    async def mine(self, package, document: dict) -> dict:
        head = await self.glossary.ensure()
        documents = [document]
        if head.get("canary"):
            try:
                documents.append(await self.glossary.document(head["canary"]))
            except NotFound:
                pass
        owned, negatives, known = _glossary_labels(package, documents)
        signals = await self.signals.rows()
        accuracy = lf_accuracy(signals)
        thresholds = MineThresholds(
            min_books=self.settings.glossary_auto_min_books,
            min_confirmations=self.settings.glossary_auto_min_confirmations,
        )
        rows = mine(signals, owned=owned, negatives=negatives, known_labels=known, lf_accuracy=accuracy, thresholds=thresholds)
        auto_rows: list[dict] = []
        propose_rows: list[dict] = []
        allow_auto = bool(self.settings.glossary_auto_promote) and not head.get("canary")
        for row in rows:
            row["applied"] = "none"
            scope = auto_scope(row) if allow_auto and row["decision"] == "auto" else None
            if scope and row.get("label_text"):
                row["_scope"] = scope
                auto_rows.append(row)
            elif row["decision"] in {"auto", "review"} and row.get("label_text"):
                propose_rows.append(row)
        promoted = False
        if auto_rows:
            ops = []
            for row in auto_rows:
                op = {
                    "op": "add_label",
                    "concept": row["concept"],
                    "kind": row["label_kind"],
                    "lang": row.get("lang") or lang_of(row["label_text"]),
                    "text": row["label_text"],
                }
                if row["_scope"] != "global":
                    op["scope"] = row["_scope"]
                ops.append(op)
            try:
                ready = await self.glossary.release(ops, f"h-{head['seq']}", source="auto")
                await self.glossary.transition(ready["version"], "canary", ready["etag"])
                promoted = True
                for row in auto_rows:
                    row["applied"] = "release"
            except (GlossaryRegression, StaleParent, PreconditionFailed):
                propose_rows.extend(auto_rows)
        proposals = 0
        for row in propose_rows:
            await self._propose(row)
            row["applied"] = "proposal"
            proposals += 1
        for row in rows:
            row.pop("_scope", None)
            row["conflicts_json"] = json.dumps(row.pop("conflicts"), ensure_ascii=False)
        run = str(ULID())
        if rows:
            payload, _count = await self.parquet.write("candidates", rows, build_key="")
            await self.store.put_if_absent(f"glossary/candidates/{run}.parquet", payload)
        canary = await self._advance_canary()
        recal = await self._recalibrate_if_due()
        hook = getattr(self, "on_release", None)
        if hook and (promoted or canary.get("canary") in {"promote", "reject"}):
            await hook()
        return {
            "run": run,
            "candidates": len(rows),
            "proposals": proposals,
            "lf_accuracy": accuracy,
            "mode": "canary" if promoted else "proposals",
            "canary": canary.get("canary"),
            "recalibrate": recal.get("recalibrate"),
        }

    async def _propose(self, row: dict) -> None:
        await self.glossary.add_proposal(
            {
                "type": "synonym_of",
                "concept": row["concept"],
                "kind": row["label_kind"],
                "lang": row.get("lang") or lang_of(row["label_text"]),
                "text": row["label_text"],
                "origin": "auto" if row["decision"] == "auto" else "mine",
                "books": row["books"],
                "impact": float(row["books"]) * float(row.get("p_weak") or 0.0),
                "evidence": {key: row[key] for key in ("books", "profiles", "confirmations", "lf_for", "lf_against", "p_weak", "conflicts", "scope")},
            }
        )

    async def _with_shots(self, label: str, state: str) -> str:
        embed = self.models.embed
        if embed is None:
            return state
        try:
            vectors = await embed.embed([label], deadline=Deadline.after_ms(self.settings.clm_timeout_sec * 1000))
            found = await self.examples.search(vectors, self.settings.knn_k)
        except ModelDegraded:
            return state
        hits = found[0] if found else []
        return few_shot_state(state, hits, self.settings.knn_k)

    async def _advance_canary(self) -> dict:
        head = await self.glossary.peek()
        if not head or not head.get("canary") or not head.get("canary_since"):
            return {}
        since = datetime.strptime(head["canary_since"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        books, rows = await self._canary_volume(head["canary"])
        etag = f"h-{head['seq']}"
        try:
            if books > 0 and await self._canary_rejected(head, since):
                await self.glossary.transition(head["canary"], "rejected", etag, reason="canary_regression")
                return {"canary": "reject"}
            verdict = canary_verdict(
                since,
                books,
                rows,
                datetime.now(UTC),
                hours=self.settings.glossary_canary_hours,
                min_books=self.settings.glossary_canary_min_books,
                min_rows=self.settings.glossary_canary_min_rows,
                max_hours=self.settings.glossary_canary_max_hours,
            )
            if verdict == "promote":
                await self.glossary.transition(head["canary"], "active", etag)
                return {"canary": "promote"}
        except (GlossaryRegression, StaleParent, PreconditionFailed):
            return {"canary": "wait"}
        return {"canary": "wait"}

    async def _canary_rejected(self, head: dict, since: datetime) -> bool:
        added = set()
        for change in label_diff(await self.glossary.document(head["active"]), await self.glossary.document(head["canary"])):
            if change.get("change") == "add" and change.get("text"):
                added.add(normalize_label(change["text"]).strip())
        if not added:
            return False
        for row in await self.signals.rows():
            if row.get("kind") not in STRONG_AGAINST or row.get("polarity") != "-":
                continue
            label = normalize_label(row.get("label_text") or row.get("label_norm") or "").strip()
            if label not in added or row.get("at_utc") is None:
                continue
            if _stamp(row["at_utc"]) >= since:
                return True
        return False

    async def _canary_volume(self, version: str) -> tuple[int, int]:
        # shortcut: все строки книг на canary, не только задетые новой меткой
        books = rows = 0
        async for item in self.store.list("books/"):
            parts = item.key.split("/")
            if len(parts) != 3 or parts[2] != "_head.json":
                continue
            body = json.loads(await self.store.get(item.key))
            if (body.get("versions") or {}).get("glossary") != version:
                continue
            books += 1
            rows += await self._coverage_rows(parts[1], body)
        return books, rows

    async def _coverage_rows(self, job_id: str, head: dict) -> int:
        build, derive = head.get("build_key"), head.get("derive_key")
        if not build or not derive:
            return 0
        try:
            done = json.loads(await self.store.get(keys.derived_done(job_id, build, derive)))
        except NotFound:
            return 0
        files = done.get("files") or {}
        names = list(files)
        rel = next((name for name in names if str(name).endswith("coverage.parquet")), None)
        if rel is None:
            return 0
        total = 0
        for row in await self.parquet.read(await self.store.get(f"books/{job_id}/{build}/{rel}")):
            total += int(row.get("rows") or 0)
        return total

    async def _recalibrate_if_due(self) -> dict:
        calibrators = getattr(self, "calibrators", None)
        if calibrators is None:
            return {}
        count = sum(
            1
            for row in await self.signals.rows()
            if row.get("kind") in {"human.confirmed", "human.corrected"} and row.get("polarity") == "+"
        )
        stored = await calibrators.head()
        if count - int(stored.get("signal_count") or 0) < self.settings.recalibrate_every:
            return {"recalibrate": "wait"}
        try:
            body = await calibrators.train(await self.examples.all_rows(), max_risk=self.settings.calibrator_max_risk)
        except InvalidArgument:
            await calibrators.note_progress(count)
            return {"recalibrate": "skipped"}
        gate = getattr(self, "recal_gate", None)
        activated = False
        if gate is None:
            # shortcut: без гейта на eval-наборе кандидат не активируется
            activated = False
        elif await gate(body):
            await calibrators.activate(body["version"])
            activated = True
        await calibrators.note_progress(count)
        return {"recalibrate": "active" if activated else "candidate", "version": body.get("version")}

    async def compact(self) -> dict:
        return {
            "examples": await self.examples.merge(),
            "unmapped": await self.unmapped.merge(),
            "signals": await self.signals.merge(),
        }


def _abs_by_row(facts: list[dict]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for fact in facts or []:
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None or not fact.get("row_key"):
            continue
        totals[fact["row_key"]] = totals.get(fact["row_key"], Decimal(0)) + abs(Decimal(str(number)))
    return totals


def auto_scope(row: dict) -> str | None:
    """Куда класть авто-метку. Без профиля alt не публикуется: он остаётся предложением."""

    scope = str(row.get("scope") or "")
    kind = row.get("label_kind")
    if kind == "hidden":
        return scope if scope.startswith("profile:") else None
    if kind != "alt":
        return None
    if int(row.get("profiles") or 0) >= 2 and not row.get("conflicts") and scope == "global":
        return "global"
    return scope if scope.startswith("profile:") else None


def _glossary_labels(package, documents: list[dict]) -> tuple[dict[str, str], dict[str, set[str]], dict[str, list[str]]]:
    owned: dict[str, str] = {}
    negatives: dict[str, set[str]] = {}
    known: dict[str, list[str]] = {}
    for concept_id, concept in package.concepts.items():
        negatives[concept_id] = set(concept.negative)
        texts = list(concept.pref.values())
        for document in documents:
            glossary = (document.get("glossaries") or {}).get(concept_id) or {}
            for kind in ("alt", "hidden"):
                for values in (glossary.get(kind) or {}).values():
                    texts.extend([values] if isinstance(values, str) else list(values or []))
            for block in (glossary.get("scoped") or {}).values():
                if not isinstance(block, dict):
                    continue
                for kind in ("alt", "hidden"):
                    bucket = block.get(kind) or {}
                    if not isinstance(bucket, dict):
                        continue
                    for values in bucket.values():
                        texts.extend([values] if isinstance(values, str) else list(values or []))
        known[concept_id] = [text for text in texts if isinstance(text, str)]
        for text in known[concept_id]:
            owned[normalize_label(text).strip()] = concept_id
    return owned, negatives, known


def _stamp(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)


def labeling_input(prepared, bindings, facts, links, package, identities) -> LabelingInput:
    values: dict[str, dict[tuple[str, str], Decimal]] = defaultdict(dict)
    cell_row: dict[str, str] = {}
    order: dict[tuple[str, str], int] = {}
    for fact in facts or []:
        # Проекция пишет факты строки по index периода оси: первый порядок появления и есть порядок оси.
        order.setdefault((fact["axis_id"], fact["period_id"]), len(order))
        if fact.get("cell_id"):
            cell_row[fact["cell_id"]] = fact["row_key"]
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is not None and fact.get("row_key"):
            values[fact["row_key"]][(fact["axis_id"], fact["period_id"])] = Decimal(str(number))
    precedents: dict[str, set[str]] = defaultdict(set)
    for link in links or []:
        parent = link.get("row_key")
        child = cell_row.get(link.get("ref_cell"))
        if parent and child:
            precedents[parent].add(child)
    return LabelingInput(
        rows=list(prepared),
        values=dict(values),
        precedents=dict(precedents),
        bindings={row["binding_key"]: row for row in bindings},
        concepts=dict(package.concepts),
        identities=identities,
        order=order,
    )
