"""Калибраторы `calibrators/` (§5.6): обучение на examples/, версии, активный калибратор.

Обучение офлайн (CLI или задача `batch`), активация — явным шагом после метрик на отложенных книгах.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from finance_analysis.domain.calibration import (
    Calibrator,
    TrainingPair,
    nil_features,
    train,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.errors import AlreadyExists, InvalidArgument, NotFound

HEAD = "calibrators/_head.json"


def training_pairs(examples: list[dict]) -> tuple[list[TrainingPair], list[TrainingPair], tuple[list, list]]:
    """Пары (строка, понятие, признаки, метка) из решений людей: confirmed/set → +, rejected → −.

    NIL-пары: concept.ignored и подтверждённый unknown — класс NIL, подтверждённые понятия — не NIL.
    """

    pairs: list[TrainingPair] = []
    nil: list[TrainingPair] = []
    clm_probs: list[dict] = []
    clm_labels: list[str] = []
    for row in examples:
        raw = json.loads(row.get("candidates_json") or "{}")
        candidates = [Candidate.of(item) for item in raw.get("candidates") or []]
        group = str(row["job_id"])
        kind = row.get("kind")
        target = row.get("concept")
        if kind in {"confirmed", "set"} and target:
            for candidate in candidates:
                pairs.append(TrainingPair(group, tuple(candidate.features()), int(candidate.concept == target)))
            clm = raw.get("clm_probabilities")
            if isinstance(clm, dict) and clm:
                clm_probs.append({str(k): float(v) for k, v in clm.items()})
                clm_labels.append(target if target in clm else "none")
        elif kind == "rejected" and target:
            for candidate in candidates:
                if candidate.concept == target:
                    pairs.append(TrainingPair(group, tuple(candidate.features()), 0))
        if kind in {"confirmed", "set", "ignored", "absent"} and candidates:
            evidence = RowEvidence(
                candidates=tuple(candidates),
                nearest_concept_cos=raw.get("nearest_concept_cos"),
                nearest_example_cos=raw.get("nearest_example_cos"),
                clm_none_prob=raw.get("clm_none_prob"),
            )
            top = max((item.get("p") or 0.0) for item in raw.get("candidates") or [{}])
            label = 1 if kind in {"ignored", "absent"} else 0
            nil.append(TrainingPair(group, tuple(nil_features(evidence, float(top))), label))
    return pairs, nil, (clm_probs, clm_labels)


class CalibratorStore:
    def __init__(self, store, *, refresh_sec: float = 30) -> None:
        self.store = store
        self._refresh_sec = refresh_sec
        self._cached: Calibrator | None = None
        self._version = "none"
        self._at = 0.0

    @property
    def version(self) -> str:
        return self._version

    async def head(self) -> dict:
        try:
            return json.loads(await self.store.get(HEAD))
        except NotFound:
            return {"seq": 0, "active": None, "history": []}

    async def active(self) -> Calibrator | None:
        if time.monotonic() - self._at < self._refresh_sec:
            return self._cached
        head = await self.head()
        version = head.get("active")
        if not version:
            self._cached, self._version = None, "none"
        elif version != self._version:
            self._cached = Calibrator.of(await self.load(version))
            self._version = version
        self._at = time.monotonic()
        return self._cached

    async def load(self, version: str) -> dict:
        try:
            return json.loads(await self.store.get(_key(version)))
        except NotFound:
            raise NotFound("калибратор не найден") from None

    async def train(self, examples: list[dict], *, max_risk: float) -> dict:
        pairs, nil, clm = training_pairs(examples)
        head = await self.head()
        try:
            calibrator = train(pairs, seq=int(head.get("seq") or 0) + 1, max_risk=max_risk, nil_pairs=nil, clm=clm)
        except ValueError as exc:
            raise InvalidArgument(str(exc), extra={"pairs": len(pairs)}) from None
        body = calibrator.as_dict()
        body["trained_at_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            await self.store.put_if_absent(_key(calibrator.version), json.dumps(body, sort_keys=True).encode())
        except AlreadyExists:
            pass
        await self._write_head({**head, "seq": int(head.get("seq") or 0) + 1, "history": [*head.get("history", []), {"version": calibrator.version, "status": "ready", "metrics": calibrator.metrics}]})
        return body

    async def activate(self, version: str | None) -> dict:
        head = await self.head()
        if version is not None:
            await self.load(version)
        history = [
            {**item, "status": "active" if item.get("version") == version else ("retired" if item.get("status") == "active" else item.get("status"))}
            for item in head.get("history", [])
        ]
        updated = {**head, "seq": int(head.get("seq") or 0) + 1, "active": version, "previous": head.get("active"), "history": history}
        await self._write_head(updated)
        self._at = 0.0
        return updated

    async def note_progress(self, signal_count: int) -> None:
        head = await self.head()
        await self._write_head({**head, "signal_count": int(signal_count)})

    async def _write_head(self, body: dict) -> None:
        data = json.dumps(body, sort_keys=True).encode()
        meta = await self.store.stat(HEAD)
        if meta is None:
            await self.store.put_if_absent(HEAD, data)
        else:
            await self.store.put_if_match(HEAD, data, meta.etag)


def _key(version: str) -> str:
    return f"calibrators/{version.replace(':', '_')}.json"
