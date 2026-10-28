"""Кандидаты понятий для строки после стадий 1–8 (§5.5) и их признаки (§5.6)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

FEATURES = (
    "rerank_inv_rank",
    "rerank_gap",
    "recall_cos",
    "knn_cos",
    "lexical",
    "structure_pass",
    "clm_prob",
    "has_clm",
)


@dataclass(frozen=True)
class Candidate:
    concept: str
    recall_cos: float | None = None
    rerank_rank: int | None = None
    rerank_gap: float | None = None
    knn_cos: float | None = None
    clm_prob: float | None = None
    lexical: bool = False
    structure_pass: bool = True
    reasons: tuple[str, ...] = ()

    def features(self) -> list[float]:
        return [
            0.0 if not self.rerank_rank else 1.0 / self.rerank_rank,
            float(self.rerank_gap or 0.0),
            float(self.recall_cos or 0.0),
            float(self.knn_cos or 0.0),
            1.0 if self.lexical else 0.0,
            1.0 if self.structure_pass else 0.0,
            float(self.clm_prob or 0.0),
            0.0 if self.clm_prob is None else 1.0,
        ]

    def as_dict(self) -> dict:
        return {
            "concept": self.concept,
            "recall_cos": _round(self.recall_cos),
            "rerank_rank": self.rerank_rank,
            "rerank_gap": _round(self.rerank_gap),
            "knn_cos": _round(self.knn_cos),
            "clm_prob": _round(self.clm_prob),
            "lexical": self.lexical,
            "structure_pass": self.structure_pass,
            "reasons": list(self.reasons),
        }

    @classmethod
    def of(cls, raw: dict) -> Candidate:
        return cls(
            concept=str(raw["concept"]),
            recall_cos=raw.get("recall_cos"),
            rerank_rank=raw.get("rerank_rank"),
            rerank_gap=raw.get("rerank_gap"),
            knn_cos=raw.get("knn_cos"),
            clm_prob=raw.get("clm_prob"),
            lexical=bool(raw.get("lexical")),
            structure_pass=bool(raw.get("structure_pass", True)),
            reasons=tuple(raw.get("reasons") or ()),
        )

    def with_reason(self, reason: str) -> Candidate:
        if reason in self.reasons:
            return self
        return replace(self, reasons=(*self.reasons, reason))


@dataclass(frozen=True)
class RowEvidence:
    """Что конвейер узнал о строке. Модели меняют только ранжирование и признаки."""

    candidates: tuple[Candidate, ...] = ()
    nearest_concept_cos: float | None = None
    nearest_example_cos: float | None = None
    clm_choice: str | None = None
    clm_none_prob: float | None = None
    embedding: tuple[float, ...] | None = field(default=None, compare=False, repr=False)
    degraded: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "candidates": [item.as_dict() for item in self.candidates],
            "nearest_concept_cos": _round(self.nearest_concept_cos),
            "nearest_example_cos": _round(self.nearest_example_cos),
            "clm_choice": self.clm_choice,
            "clm_none_prob": _round(self.clm_none_prob),
            "degraded": list(self.degraded),
        }


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
