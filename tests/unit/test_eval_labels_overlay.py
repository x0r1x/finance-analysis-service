"""eval/local/labels overlay merges into the mapping eval set without committing client books."""

from __future__ import annotations

import json
from types import SimpleNamespace

from finance_analysis.application.evaluation import Evaluator


def test_eval_set_merges_local_labels_and_sets_id(tmp_path):
    committed = tmp_path / "labels"
    local = tmp_path / "local" / "labels"
    committed.mkdir(parents=True)
    local.mkdir(parents=True)
    (committed / "packt.json").write_text(
        json.dumps({"schema_version": "1", "job_id": "job-packt", "by_path": {}}),
        encoding="utf-8",
    )
    (committed / "rvi.json").write_text(
        json.dumps({"schema_version": "1", "id": "rvi", "job_id": "job-rvi", "by_path": {}}),
        encoding="utf-8",
    )
    # Local private book + override of an existing job_id (local wins).
    (local / "private.json").write_text(
        json.dumps({"schema_version": "1", "job_id": "job-private", "by_path": {"A › B": "cfads"}}),
        encoding="utf-8",
    )
    (local / "rvi.json").write_text(
        json.dumps({"schema_version": "1", "id": "rvi-local", "job_id": "job-rvi", "by_path": {"X": "NIL"}}),
        encoding="utf-8",
    )

    service = SimpleNamespace(settings=SimpleNamespace(fas_eval_dir=str(tmp_path)))
    items = Evaluator(service).eval_set()
    by_id = {item["id"]: item for item in items}
    assert set(by_id) == {"packt", "rvi-local", "private"}
    assert by_id["packt"]["job_id"] == "job-packt"
    assert by_id["rvi-local"]["by_path"] == {"X": "NIL"}
    assert by_id["private"]["job_id"] == "job-private"
