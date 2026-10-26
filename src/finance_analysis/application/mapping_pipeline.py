"""Конвейер привязки со стадиями моделей (§5.5): GlossaryExpand → Recall → kNN → Rerank → Adjudicate.

Модели меняют только ранжирование и признаки; статус решают domain.mapping.decide и калибратор.
Любой отказ модели — деградация стадии с `degraded: {stage, reason}` в evidence, а не ошибка.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field, replace

import numpy as np

from finance_analysis.application.ports import Models
from finance_analysis.domain.calibration import (
    Calibrator,
    apply_temperature,
    heuristic_probability,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.errors import ModelDegraded
from finance_analysis.domain.glossary import GlossaryPackage
from finance_analysis.domain.mapping import lexical_hit

EMBED_BATCH = 64
CLM_GAP = 0.1
CLM_MAX_CRITERIA = 8
CLM_BUDGET_TTL = 86_400


@dataclass
class PipelineResult:
    evidence: dict[str, RowEvidence] = field(default_factory=dict)
    degraded: list[dict] = field(default_factory=list)
    clm_calls: int = 0
    embeddings: dict[str, list[float]] = field(default_factory=dict)


def concept_document(package: GlossaryPackage, concept_id: str) -> str:
    concept = package.concepts[concept_id]
    parts = [concept.pref.get("ru", ""), concept.pref.get("en", "")]
    parts.extend(concept.definition.values())
    return " · ".join(part for part in parts if part)


def expand(text: str, package: GlossaryPackage) -> str:
    """Стадия 1: аббревиатуры понятий раскрываются рядом с исходным текстом."""

    extra = []
    for concept in package.concepts.values():
        for short, full in concept.expand.items():
            if re.search(rf"(?<!\w){re.escape(short)}(?!\w)", text, flags=re.IGNORECASE):
                extra.append(full)
    if not extra:
        return text
    return f"{text} ({'; '.join(sorted(set(extra)))})"


def row_text(row: dict) -> str:
    sheet = str(row.get("sheet") or "")
    path = str(row.get("label_path_text") or row.get("label") or "")
    unit = str(row.get("unit") or "")
    text = f"{sheet} › {path}" if sheet else path
    return f"{text} ({unit})" if unit else text


def _cosines(rows: np.ndarray, concepts: np.ndarray) -> np.ndarray:
    def norm(matrix: np.ndarray) -> np.ndarray:
        lengths = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(lengths == 0, 1.0, lengths)

    return norm(rows) @ norm(concepts).T


class MappingPipeline:
    def __init__(self, models: Models, examples=None, budget=None, *, settings) -> None:
        self.models = models
        self.examples = examples
        self.budget = budget
        self.settings = settings
        self._concept_vectors: dict[tuple[str, str], tuple[list[str], np.ndarray]] = {}

    @property
    def enabled(self) -> bool:
        return self.models.embed is not None or self.models.rerank is not None

    async def score(
        self,
        job_id: str,
        run_id: str,
        rows: list[dict],
        package: GlossaryPackage,
        *,
        glossary_version: str,
        deadline: Deadline,
        skip: frozenset[str] = frozenset(),
        calibrator: Calibrator | None = None,
    ) -> PipelineResult:
        result = PipelineResult()
        targets = [
            row
            for row in rows
            if row.get("kind") == "fact"
            and not row.get("excluded")
            and row["binding_key"] not in skip
            and lexical_hit(row, package) is None
        ]
        if not targets or not self.enabled:
            return result
        texts = [expand(row_text(row), package) for row in targets]
        concept_ids = sorted(package.concepts)
        recall: list[list[Candidate]] = [[] for _ in targets]
        nearest_concept: list[float | None] = [None for _ in targets]
        nearest_example: list[float | None] = [None for _ in targets]
        if self.models.embed is not None:
            try:
                vectors = await self._embed(texts, deadline)
                names, matrix = await self._concepts(package, glossary_version, concept_ids, deadline)
                cos = _cosines(np.asarray(vectors, dtype=float), matrix)
                top_k = min(self.settings.recall_top_k, len(names))
                for index, row in enumerate(targets):
                    result.embeddings[row["binding_key"]] = vectors[index]
                    order = np.argsort(-cos[index])[:top_k]
                    nearest_concept[index] = float(cos[index][order[0]]) if len(order) else None
                    recall[index] = [Candidate(names[j], recall_cos=float(cos[index][j])) for j in order]
                await self._knn(targets, vectors, recall, nearest_example, job_id)
            except ModelDegraded as exc:
                result.degraded.append(exc.as_dict())
        if not any(recall):
            # Без embed кандидаты для rerank — все понятия каталога.
            recall = [[Candidate(name) for name in concept_ids] for _ in targets]
        reranked = await self._rerank(texts, recall, package, deadline, result)
        evidence = {
            row["binding_key"]: RowEvidence(
                candidates=tuple(reranked[index]),
                nearest_concept_cos=nearest_concept[index],
                nearest_example_cos=nearest_example[index],
                degraded=tuple(result.degraded),
            )
            for index, row in enumerate(targets)
        }
        await self._adjudicate(job_id, run_id, targets, texts, evidence, package, deadline, result, calibrator)
        result.evidence = evidence
        return result

    async def _embed(self, texts: list[str], deadline: Deadline) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            out.extend(await self.models.embed.embed(texts[start : start + EMBED_BATCH], deadline=deadline))
        return out

    async def _concepts(self, package, version: str, names: list[str], deadline: Deadline):
        key = (version, self.models.embed.model)
        cached = self._concept_vectors.get(key)
        if cached and cached[0] == names:
            return cached
        docs = [concept_document(package, name) for name in names]
        matrix = np.asarray(await self._embed(docs, deadline), dtype=float)
        self._concept_vectors = {key: (names, matrix)}
        return names, matrix

    async def _knn(self, targets, vectors, recall, nearest_example, job_id: str) -> None:
        if self.examples is None:
            return
        hits = await self.examples.search(vectors, self.settings.knn_k)
        for index, row in enumerate(targets):
            found = [(cos, item) for cos, item in hits[index] if not (item["job_id"] == job_id and item["binding_key"] == row["binding_key"])]
            if not found:
                continue
            nearest_example[index] = max(cos for cos, _item in found)
            best: dict[str, float] = {}
            for cos, item in found:
                best[item["concept"]] = max(best.get(item["concept"], -1.0), cos)
            known = {candidate.concept for candidate in recall[index]}
            updated = []
            for candidate in recall[index]:
                if candidate.concept in best:
                    candidate = replace(candidate, knn_cos=best[candidate.concept]).with_reason("cross_book_example")
                updated.append(candidate)
            for concept, cos in sorted(best.items(), key=lambda pair: -pair[1]):
                if concept not in known:
                    updated.append(Candidate(concept, knn_cos=cos, reasons=("cross_book_example",)))
            recall[index] = updated

    async def _rerank(self, texts, recall, package, deadline: Deadline, result: PipelineResult) -> list[list[Candidate]]:
        top_n = self.settings.rerank_top_k
        if self.models.rerank is None:
            return [sorted(items, key=lambda c: -(c.recall_cos or 0.0))[: max(top_n, 1) * 2] for items in recall]
        failures: list[dict] = []

        async def one(index: int) -> list[Candidate]:
            items = [item for item in recall[index] if item.concept in package.concepts]
            if not items:
                return []
            docs = [concept_document(package, item.concept) for item in items]
            try:
                ranked = await self.models.rerank.rerank(texts[index], docs, deadline=deadline, top_n=top_n)
            except ModelDegraded as exc:
                failures.append(exc.as_dict())
                return sorted(items, key=lambda c: -(c.recall_cos or 0.0))[: top_n * 2]
            out = []
            scores = [score for _idx, score in ranked]
            for rank, (doc_index, score) in enumerate(ranked, start=1):
                gap = score - scores[1] if rank == 1 and len(scores) > 1 else score - scores[0]
                out.append(replace(items[doc_index], rerank_rank=rank, rerank_gap=gap))
            # Кандидат из примеров других книг остаётся признаком, даже если не попал в top-n rerank.
            kept = {item.concept for item in out}
            out.extend(item for item in items if item.knn_cos is not None and item.concept not in kept)
            return out

        ranked = await asyncio.gather(*(one(index) for index in range(len(texts))))
        if failures:
            result.degraded.append(failures[0])
        return list(ranked)

    async def _adjudicate(self, job_id, run_id, targets, texts, evidence, package, deadline, result, calibrator) -> None:
        """Стадия 8: только неоднозначные строки, бюджет CLM_MAX_CALLS_PER_BOOK атомарно в Redis."""

        if self.models.clm is None or self.settings.clm_max_calls_per_book <= 0:
            return
        temperature = calibrator.temperature if calibrator else 1.0

        def prob(candidate: Candidate) -> float:
            return calibrator.probability(candidate) if calibrator else heuristic_probability(candidate)

        jobs = []
        for index, row in enumerate(targets):
            found = evidence[row["binding_key"]]
            ranked = sorted(found.candidates, key=lambda c: -prob(c))
            if len(ranked) < 2 or prob(ranked[0]) - prob(ranked[1]) >= CLM_GAP:
                continue
            jobs.append((index, row, ranked[:CLM_MAX_CRITERIA]))
        failures: list[dict] = []

        async def one(index, row, ranked) -> None:
            if self.budget is not None:
                allowed = await self.budget.take(f"fas:clm:{job_id}:{run_id}", self.settings.clm_max_calls_per_book, CLM_BUDGET_TTL)
                if not allowed:
                    failures.append({"stage": "clm", "reason": "budget"})
                    return
            criteria = {item.concept: concept_document(package, item.concept) for item in ranked}
            criteria["none"] = "Ни одно из перечисленных"
            question = {"concept": {"type": "choice", "instructions": "Какому понятию соответствует строка?", "criteria": criteria}}
            try:
                answer = (await self.models.clm.choose(texts[index], question, deadline=deadline))["concept"]
            except ModelDegraded as exc:
                failures.append(exc.as_dict())
                return
            result.clm_calls += 1
            probabilities = apply_temperature(answer["probabilities"], temperature)
            found = evidence[row["binding_key"]]
            candidates = tuple(
                replace(item, clm_prob=probabilities.get(item.concept, 0.0)).with_reason("clm")
                if item.concept in criteria
                else item
                for item in found.candidates
            )
            evidence[row["binding_key"]] = replace(
                found,
                candidates=candidates,
                clm_choice=answer["choice"],
                clm_none_prob=probabilities.get("none"),
            )

        await asyncio.gather(*(one(*job) for job in jobs))
        if failures:
            result.degraded.append(failures[0])
            for key, found in list(evidence.items()):
                evidence[key] = replace(found, degraded=tuple(result.degraded))
