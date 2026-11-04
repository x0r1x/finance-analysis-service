"""Сводка прогона типа: accuracy, вопросы, ложные срабатывания, разрыв."""

from __future__ import annotations

from finance_analysis.domain.model_type import Inference, Scored
from finance_analysis.domain.model_type_eval import (
    Expectation,
    build_report,
    render_markdown,
)

_TYPES = ("corporate", "investment_project", "other", "project_finance")


def _infer(confident, reason, labels, primary, scores):
    return Inference(confident, reason, labels, primary, (), scores)


def test_false_positive_is_the_confident_label_that_gold_does_not_have():
    report = build_report(
        [
            (
                "toy",
                Expectation("type", "project_finance", ("project_finance",)),
                _infer(True, None, ("corporate",), "corporate", {"corporate": 1.0, "project_finance": 0.0}),
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    summary = report["summary"]
    assert summary["primary_accuracy"] == 0.0
    assert summary["primary_correct"] == 0
    assert summary["typed"] == 1
    assert summary["false_positives"]["corporate"] == {"count": 1, "rate": 1.0}
    assert summary["false_positives"]["project_finance"]["count"] == 0
    assert summary["false_positives"]["other"]["count"] == 0
    row = report["cases"][0]
    assert row["gap"] == 1.0
    assert row["meets_accept"] is True
    assert row["meets_gap"] is True
    assert row["false_positives"] == ["corporate"]


def test_a_question_stays_out_of_primary_accuracy_and_raises_the_question_share():
    scores = {"corporate": 1.0, "project_finance": 1.0}
    report = build_report(
        [
            (
                "ask",
                Expectation("question", reason="ambiguous"),
                _infer(False, "ambiguous", (), "corporate", scores),
            ),
            (
                "typed",
                Expectation("type", "project_finance", ("project_finance",)),
                _infer(True, None, ("project_finance",), "project_finance", {"project_finance": 1.0, "corporate": 0.0}),
            ),
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    summary = report["summary"]
    assert summary["typed"] == 1
    assert summary["primary_correct"] == 1
    assert summary["primary_accuracy"] == 1.0
    assert summary["questions"] == 1
    assert summary["question_rate"] == 0.5
    assert summary["decisions_correct"] == 2
    assert report["cases"][0]["gap"] == 0.0
    assert report["cases"][0]["meets_gap"] is False
    assert report["cases"][0]["false_positives"] == []
    assert all(item["count"] == 0 for item in summary["false_positives"].values())


def test_wrong_question_reason_is_not_a_correct_decision():
    report = build_report(
        [
            (
                "ask",
                Expectation("question", reason="unknown"),
                _infer(False, "ambiguous", (), "corporate", {"corporate": 1.0, "project_finance": 1.0}),
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    assert report["summary"]["decisions_correct"] == 0
    assert report["summary"]["questions"] == 1
    assert report["summary"]["primary_accuracy"] is None


def test_a_lone_leader_meets_the_gap():
    report = build_report(
        [
            (
                "only",
                Expectation("type", "corporate", ("corporate",)),
                _infer(True, None, ("corporate",), "corporate", {"corporate": 1.0}),
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    row = report["cases"][0]
    assert row["gap"] is None
    assert row["top2"] is None
    assert row["meets_gap"] is True
    assert row["primary_hit"] is True


def test_a_below_gap_question_names_a_row_only_when_the_runner_up_also_clears_accept():
    near = build_report(
        [
            (
                "near",
                Expectation("question", reason="ambiguous"),
                _infer(
                    False,
                    "ambiguous",
                    (),
                    "corporate",
                    {"corporate": 0.6, "project_finance": 0.5, "investment_project": 0.0},
                ),
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    pair = build_report(
        [
            (
                "tie",
                Expectation("question", reason="ambiguous"),
                _infer(False, "ambiguous", (), "corporate", {"corporate": 1.0, "project_finance": 0.9}),
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=_TYPES,
    )
    assert "порога: нет." in render_markdown(near)
    assert "порога: tie." in render_markdown(pair)


def test_stand_down_gap_drops_the_yielded_type():
    """investment уступает corporate и в разрыв top1–top2 не входит."""

    from finance_analysis.domain.model_type import decision_ranking

    inference = Inference(
        True,
        None,
        ("corporate",),
        "corporate",
        (Scored("corporate", 1.0, ()),),
        {"investment_project": 1.0, "corporate": 1.0, "project_finance": 0.0},
    )
    ranked = decision_ranking(inference, accept=0.6)
    assert [item.type_id for item in ranked] == ["corporate", "project_finance"]
    assert ranked[0].score - ranked[1].score == 1.0
