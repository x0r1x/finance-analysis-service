"""Метрики score_book / NIL recall & precision (§5.10.6)."""

from finance_analysis.domain.evaluation import NIL, score_book, summarize

FOCUS = frozenset({"cfads", "debt_service", "interest"})
METRICS = frozenset({"cfads", "debt_service", "interest"})


def _row(key: str, *, status: str, concept: str | None = None) -> dict:
    return {
        "binding_key": key,
        "status": status,
        "effective_concept": concept,
        "concept": concept,
    }


def test_summarize_includes_per_book_top1():
    packt = score_book(
        "job-packt",
        [
            _row("c1", status="bound", concept="cfads"),
            _row("i1", status="bound", concept="interest"),
            _row("i2", status="bound", concept="interest"),
            _row("i3", status="bound", concept="interest"),
        ],
        {"c1": "cfads", "i1": "interest", "i2": "interest", "i3": "interest"},
        metric_concepts=METRICS,
        book_id="packt",
    )
    rvi = score_book(
        "job-rvi",
        [
            _row("c1", status="bound", concept="cfads"),
            _row("i1", status="ambiguous", concept="interest"),
            _row("i2", status="ambiguous", concept="interest"),
            _row("i3", status="ambiguous", concept="interest"),
        ],
        {"c1": "cfads", "i1": "interest", "i2": "interest", "i3": "interest"},
        metric_concepts=METRICS,
        book_id="rvi",
    )
    summary = summarize([packt, rvi], focus=FOCUS)
    assert summary["top1"]["cfads"] == 1.0
    assert summary["top1"]["interest"] == 0.5
    assert summary["top1_by_book"]["packt"]["cfads"] == {"rate": 1.0, "correct": 1, "total": 1}
    assert summary["top1_by_book"]["packt"]["interest"] == {"rate": 1.0, "correct": 3, "total": 3}
    assert summary["top1_by_book"]["rvi"]["interest"] == {"rate": 0.0, "correct": 0, "total": 3}


def test_nil_recall_counts_unknown_and_ambiguous_only():
    labels = {
        "u": NIL,
        "a": NIL,
        "na": NIL,
        "ig": NIL,
        "bound_wrong": NIL,
    }
    bindings = [
        _row("u", status="unknown"),
        _row("a", status="ambiguous", concept="cfads"),
        _row("na", status="not_applicable"),
        _row("ig", status="ignored"),
        _row("bound_wrong", status="bound", concept="cfads"),
    ]
    score = score_book("j", bindings, labels, metric_concepts=METRICS, critical=frozenset(labels))
    assert score.nil_total == 5
    assert score.nil_hit == 2  # unknown + ambiguous
    assert score.nil_hit_critical == 2
    assert score.nil_total_critical == 5


def test_nil_precision_treats_ambiguous_as_predicted_nil():
    labels = {
        "nil_unknown": NIL,
        "nil_ambiguous": NIL,
        "concept_ambiguous": "interest",
        "concept_unknown": "cfads",
        "na": NIL,
    }
    bindings = [
        _row("nil_unknown", status="unknown"),
        _row("nil_ambiguous", status="ambiguous", concept="interest"),
        _row("concept_ambiguous", status="ambiguous", concept="interest"),
        _row("concept_unknown", status="unknown"),
        _row("na", status="not_applicable"),
    ]
    score = score_book("j", bindings, labels, metric_concepts=METRICS)
    # predicted NIL = unknown|ambiguous → four rows; two are true NIL
    assert score.nil_predicted == 4
    assert score.nil_predicted_true == 2
    summary = summarize([score], focus=FOCUS)
    assert summary["nil_precision"] == 0.5
    assert summary["nil_recall"] == 0.666667


def test_not_applicable_and_ignored_are_not_nil_predictions():
    labels = {"na": "cfads", "ig": NIL}
    bindings = [
        _row("na", status="not_applicable"),
        _row("ig", status="ignored"),
    ]
    score = score_book("j", bindings, labels, metric_concepts=METRICS)
    assert score.nil_predicted == 0
    assert score.nil_predicted_true == 0
    assert score.nil_total == 1
    assert score.nil_hit == 0
