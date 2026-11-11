"""Eval привязки, eval с удалённым понятием и shadow-гейт релизов глоссария (§5.10.6, §5.11.3).

Перепривязка идёт по уже записанной проекции книги и по сохранённым признакам моделей
(evidence_json привязок), поэтому shadow не вызывает серверы моделей и не меняет книги.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from finance_analysis.application.project import derive_rows
from finance_analysis.domain.calibration import bootstrap_delta
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.errors import NotFound
from finance_analysis.domain.evaluation import score_book, summarize, targets_met
from finance_analysis.domain.glossary import with_profile
from finance_analysis.domain.glossary_release import package_of

METRIC_CONCEPTS = frozenset({"cfads", "debt_service", "interest", "principal", "ebitda", "ebit", "debt_outstanding", "discount_rate"})
FOCUS = frozenset({"cfads", "debt_service", "interest"})


def _profile_of(head) -> str | None:
    raw = str((head.versions or {}).get("profile") or "")
    name = raw.split("@", 1)[0]
    if not name or name == "p-0":
        return None
    return name


def evidence_from(bindings: list[dict]) -> dict[str, RowEvidence]:
    out = {}
    for row in bindings:
        raw = json.loads(row.get("evidence_json") or "{}")
        if not raw.get("candidates") or raw.get("label"):
            continue
        out[row["binding_key"]] = RowEvidence(
            candidates=tuple(Candidate.of(item) for item in raw["candidates"]),
            nearest_concept_cos=raw.get("nearest_concept_cos"),
            nearest_example_cos=raw.get("nearest_example_cos"),
            clm_choice=raw.get("clm_choice"),
            clm_none_prob=raw.get("clm_none_prob"),
        )
    return out


def prune(document: dict, concepts: set[str]) -> dict:
    """BLINKout: понятие временно удаляется из таксономии и глоссария."""

    pruned = copy.deepcopy(document)
    for concept in concepts:
        pruned["concepts"].pop(concept, None)
        pruned["glossaries"].pop(concept, None)
    return pruned


def primaries(bindings: list[dict]) -> dict[str, str]:
    """Понятие метрики → binding_key его единственной основной строки."""

    owners: dict[str, list[str]] = {}
    for row in bindings:
        concept = row.get("effective_concept")
        if concept in METRIC_CONCEPTS and row.get("is_primary") and row.get("status") in {"bound", "bound_with_warning"}:
            owners.setdefault(concept, []).append(row["binding_key"])
    return {concept: keys[0] for concept, keys in owners.items() if len(keys) == 1}


def covered(bindings: list[dict]) -> set[str]:
    return set(primaries(bindings))


class Evaluator:
    def __init__(self, service) -> None:
        self.service = service

    async def book(self, job_id: str, package, *, calibrator=None, use_models: bool = True, document=None) -> tuple[list[dict], list[dict]]:
        svc = self.service
        head, _token = await svc._read_head(job_id)
        if head is None:
            raise NotFound(f"книга {job_id} не загружена")
        if document is not None:
            package = with_profile(package, document, _profile_of(head))
        projected = {
            "dim_row": await svc._dataset_rows(job_id, head, "dim_row"),
            "dim_period": await svc._dataset_rows(job_id, head, "dim_period"),
        }
        facts = await svc._dataset_rows(job_id, head, "fact_observation")
        events = await svc.guard.read_all(job_id)
        try:
            current = await svc._dataset_rows(job_id, head, "bindings")
        except (NotFound, StopIteration):
            current = []
        derived = derive_rows(
            projected,
            state_seq=head.state_seq,
            derive="shadow",
            versions=head.versions,
            events=events,
            glossary=package,
            facts=facts,
            evidence=evidence_from(current) if use_models else None,
            calibrator=calibrator,
        )
        return derived["bindings"], projected["dim_row"]

    def eval_dir(self) -> Path:
        return Path(self.service.settings.fas_eval_dir) / "labels"

    def label_dirs(self) -> list[Path]:
        """Committed labels plus optional local overlay (`eval/local/labels`, gitignored)."""

        root = Path(self.service.settings.fas_eval_dir)
        dirs = [root / "labels"]
        local = root / "local" / "labels"
        if local.is_dir():
            dirs.append(local)
        return dirs

    def eval_set(self) -> list[dict]:
        """Load label JSON. Local overlay wins on the same `job_id`; filenames become `id` when missing.

        Final set must have unique non-empty ``id`` values (human keys for ``top1_by_book``).
        """

        by_job: dict[str, dict] = {}
        order: list[str] = []
        for folder in self.label_dirs():
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                item = json.loads(path.read_text(encoding="utf-8"))
                item.setdefault("id", path.stem)
                item["id"] = str(item["id"] or path.stem)
                job_id = item["job_id"]
                if job_id not in by_job:
                    order.append(job_id)
                by_job[job_id] = item
        items = [by_job[job_id] for job_id in order]
        seen_ids: dict[str, str] = {}
        for item in items:
            book_id = item["id"]
            if not book_id:
                raise ValueError("eval label id must be non-empty")
            prior = seen_ids.get(book_id)
            if prior is not None:
                raise ValueError(
                    f"duplicate eval label id {book_id!r}: jobs {prior} and {item['job_id']}"
                )
            seen_ids[book_id] = item["job_id"]
        return items

    @staticmethod
    def labels_of(item: dict, rows: list[dict]) -> tuple[dict[str, str], frozenset[str]]:
        labels = dict(item.get("labels") or {})
        by_path = item.get("by_path") or {}
        for row in rows:
            text = row.get("label_path_text")
            if text in by_path and row["binding_key"] not in labels:
                labels[row["binding_key"]] = by_path[text]
        critical = set(item.get("critical") or [])
        for row in rows:
            if row.get("label_path_text") in set(item.get("critical_paths") or []):
                critical.add(row["binding_key"])
        return labels, frozenset(critical)

    async def run(self, package, *, calibrator=None, items: list[dict] | None = None, document=None) -> dict:
        scores = []
        missing = []
        for item in items if items is not None else self.eval_set():
            try:
                bindings, rows = await self.book(item["job_id"], package, calibrator=calibrator, document=document)
            except NotFound:
                missing.append(item["job_id"])
                continue
            labels, critical = self.labels_of(item, rows)
            scores.append(
                score_book(
                    item["job_id"],
                    bindings,
                    labels,
                    metric_concepts=METRIC_CONCEPTS,
                    critical=critical,
                    book_id=str(item.get("id") or item["job_id"]),
                )
            )
        summary = summarize(scores, focus=FOCUS)
        return {"summary": summary, "targets": targets_met(summary, focus=FOCUS), "missing_books": missing, "scores": scores}

    async def pruned(self, document: dict, concepts: list[str], *, calibrator=None) -> dict:
        """Строки удалённого понятия должны стать unknown/ambiguous, а не уйти в соседнее понятие."""

        out = {}
        for concept in concepts:
            package = package_of(prune(document, {concept}))
            leaked = total = 0
            for item in self.eval_set():
                try:
                    bindings, rows = await self.book(item["job_id"], package, calibrator=calibrator)
                except NotFound:
                    continue
                labels, _critical = self.labels_of(item, rows)
                for row in bindings:
                    if labels.get(row["binding_key"]) != concept:
                        continue
                    total += 1
                    if row.get("status") in {"bound", "bound_with_warning"} and row.get("source") == "inferred":
                        leaked += 1
            out[concept] = {"rows": total, "leaked": leaked, "nil_recall": None if not total else round(1 - leaked / total, 6)}
        return out

    async def shadow(self, version: str) -> dict:
        """Кандидат против active на eval-наборе и последних книгах; отчёт в releases/{version}/shadow.json."""

        svc = self.service
        # Гейт зовут под замком глоссария: только чтения без замка (peek, document, jobs).
        state = await svc.glossary.peek()
        active_version = state["active"]
        active_doc = await svc.glossary.document(active_version)
        candidate_doc = await svc.glossary.document(version)
        active = package_of(active_doc)
        candidate = package_of(candidate_doc)
        calibrator = await svc.calibrators.active()
        reasons: list[str] = []
        eval_items = self.eval_set()
        eval_report: dict = {"books": 0}
        if eval_items:
            before = await self.run(active, calibrator=calibrator, items=eval_items, document=active_doc)
            after = await self.run(candidate, calibrator=calibrator, items=eval_items, document=candidate_doc)
            pairs = list(zip(before["scores"], after["scores"], strict=True))
            slices = {
                "all": [((a.false, a.accepted), (b.false, b.accepted)) for a, b in pairs],
                "metric": [((a.false_metric, a.accepted_metric), (b.false_metric, b.accepted_metric)) for a, b in pairs],
                "critical": [((a.false_critical, a.accepted_critical), (b.false_critical, b.accepted_critical)) for a, b in pairs],
            }
            deltas = {}
            for name, rows in slices.items():
                point, low, high = bootstrap_delta([r[0] for r in rows], [r[1] for r in rows])
                deltas[name] = {"delta": round(point, 6), "ci95": [round(low, 6), round(high, 6)]}
                if low > 0:
                    reasons.append(f"false_binding_up:{name}")
            eval_report = {
                "books": len(pairs),
                "active": before["summary"],
                "candidate": after["summary"],
                "delta": deltas,
                "missing_books": after["missing_books"],
            }
        books = []
        recent = (await svc.glossary.jobs())[-svc.settings.glossary_shadow_recent_books :]
        for job_id in recent:
            try:
                old, rows = await self.book(job_id, active, calibrator=calibrator, document=active_doc)
                new, _rows = await self.book(job_id, candidate, calibrator=calibrator, document=candidate_doc)
            except (NotFound, StopIteration):
                continue
            label = {row["binding_key"]: row.get("label_path_text") for row in rows}
            old_by = {row["binding_key"]: row for row in old}
            changes = []
            for row in new:
                prev = old_by.get(row["binding_key"]) or {}
                if (prev.get("status"), prev.get("effective_concept")) != (row.get("status"), row.get("effective_concept")):
                    changes.append(
                        {
                            "binding_key": row["binding_key"],
                            "path": label.get(row["binding_key"]),
                            "from": {"status": prev.get("status"), "concept": prev.get("effective_concept")},
                            "to": {"status": row.get("status"), "concept": row.get("effective_concept")},
                        }
                    )
            before, after = primaries(old), primaries(new)
            lost = sorted(set(before) - set(after))
            if lost:
                reasons.append(f"coverage_down:{job_id}")
            # Понятие метрики на другой строке меняет входы DSCR/ICR так же, как потеря понятия.
            moved = sorted(concept for concept in set(before) & set(after) if before[concept] != after[concept])
            if moved:
                reasons.append(f"primary_moved:{job_id}")
            bound = lambda items: sum(1 for r in items if r.get("status") in {"bound", "bound_with_warning"})
            books.append(
                {
                    "job_id": job_id,
                    "changes": changes[:200],
                    "changed_rows": len(changes),
                    "delta_bound": bound(new) - bound(old),
                    "new_ambiguous": sum(1 for c in changes if c["to"]["status"] == "ambiguous"),
                    "metric_concepts_lost": lost,
                    "metric_concepts_moved": [
                        {"concept": c, "from": before[c], "to": after[c], "path": label.get(after[c])} for c in moved
                    ],
                }
            )
        report = {
            "version": version,
            "against": active_version,
            "passed": not reasons,
            "reasons": reasons,
            "eval": eval_report,
            "books": books,
            "path": f"glossary/releases/{version}/shadow.json",
        }
        await svc.store.put(report["path"], json.dumps(report, ensure_ascii=False, sort_keys=True, default=str).encode())
        return report
