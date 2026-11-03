"""Сводка прогона типа модели (§5.10.6). Без ввода-вывода.

Accuracy основного типа считается только по книгам, где ожидается тип.
Доля вопросов — по всем книгам прогона. Ложное срабатывание — уверенная метка,
которой нет в разметке. Разрыв top1–top2 берётся после уступки типа.
"""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.model_type import Inference, decision_ranking


@dataclass(frozen=True)
class Expectation:
    kind: str
    primary: str | None = None
    labels: tuple[str, ...] = ()
    reason: str | None = None


def build_report(
    cases: list[tuple[str, Expectation, Inference]],
    *,
    accept: float,
    gap: float,
    type_ids: tuple[str, ...],
) -> dict:
    rows = [_row(case_id, expected, inference, accept=accept, gap=gap) for case_id, expected, inference in cases]
    return {
        "accept": accept,
        "gap": gap,
        "cases": rows,
        "summary": _summary(rows, type_ids),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Прогон типа модели",
        "",
        f"Пороги: accept {report['accept']}, gap {report['gap']}. Прогон пороги не меняет.",
        "",
        "| книга | ожидание | ответ | top1 | top2 | разрыв | ≥ accept | ≥ gap | ложные |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["cases"]:
        lines.append(
            "| {id} | {expected} | {answer} | {top1} | {top2} | {gap} | {accept} | {gap_ok} | {fp} |".format(
                id=row["id"],
                expected=_expected_cell(row["expected"]),
                answer=_answer_cell(row),
                top1=_score_cell(row["top1"], row["top1_score"]),
                top2=_score_cell(row["top2"], row["top2_score"]),
                gap=_num(row["gap"]),
                accept=_yes(row["meets_accept"]),
                gap_ok=_yes(row["meets_gap"]),
                fp=", ".join(row["false_positives"]) or "—",
            )
        )
    summary = report["summary"]
    lines.extend(
        [
            "",
            "## Сводка",
            "",
            f"- accuracy основного типа: {_ratio(summary['primary_correct'], summary['typed'], summary['primary_accuracy'])}",
            f"- доля вопросов: {_ratio(summary['questions'], summary['n'], summary['question_rate'])}",
            f"- верные решения: {_ratio(summary['decisions_correct'], summary['n'], summary['decision_accuracy'])}",
            "",
            "| тип | ложные | доля |",
            "| --- | --- | --- |",
        ]
    )
    for type_id, item in summary["false_positives"].items():
        lines.append(f"| {type_id} | {item['count']} | {item['rate']:.3f} |")
    lines.extend(["", _threshold_facts(report), ""])
    return "\n".join(lines)


def _row(case_id: str, expected: Expectation, inference: Inference, *, accept: float, gap: float) -> dict:
    ranked = decision_ranking(inference, accept=accept)
    top1 = ranked[0] if ranked else None
    top2 = ranked[1] if len(ranked) > 1 else None
    opened = None if top1 is None or top2 is None else top1.score - top2.score
    gold = set(expected.labels) if expected.kind == "type" else set()
    emitted = set(inference.labels) if inference.confident else set()
    primary_hit = None
    if expected.kind == "type":
        primary_hit = inference.confident and inference.primary == expected.primary and inference.labels == expected.labels
    question_hit = None
    if expected.kind == "question":
        question_hit = (not inference.confident) and inference.reason == expected.reason
    return {
        "id": case_id,
        "expected": {
            "kind": expected.kind,
            "primary": expected.primary,
            "labels": list(expected.labels),
            "reason": expected.reason,
        },
        "confident": inference.confident,
        "reason": inference.reason,
        "primary": inference.primary,
        "labels": list(inference.labels),
        "top1": None if top1 is None else top1.type_id,
        "top1_score": None if top1 is None else top1.score,
        "top2": None if top2 is None else top2.type_id,
        "top2_score": None if top2 is None else top2.score,
        "gap": opened,
        "meets_accept": top1 is not None and top1.score >= accept,
        "meets_gap": top2 is None or opened >= gap,
        "scores": dict(sorted(inference.scores.items())),
        "primary_hit": primary_hit,
        "question_hit": question_hit,
        "false_positives": sorted(emitted - gold),
    }


def _summary(rows: list[dict], type_ids: tuple[str, ...]) -> dict:
    typed = [row for row in rows if row["expected"]["kind"] == "type"]
    primary_correct = sum(row["primary_hit"] is True for row in typed)
    questions = sum(not row["confident"] for row in rows)
    decisions = sum(row["primary_hit"] is True or row["question_hit"] is True for row in rows)
    n = len(rows)
    counts = {type_id: 0 for type_id in sorted(type_ids)}
    for row in rows:
        for type_id in row["false_positives"]:
            counts[type_id] = counts.get(type_id, 0) + 1
    return {
        "n": n,
        "typed": len(typed),
        "primary_correct": primary_correct,
        "primary_accuracy": None if not typed else primary_correct / len(typed),
        "questions": questions,
        "question_rate": None if not n else questions / n,
        "decisions_correct": decisions,
        "decision_accuracy": None if not n else decisions / n,
        "false_positives": {type_id: {"count": count, "rate": 0.0 if not n else count / n} for type_id, count in counts.items()},
    }


def _threshold_facts(report: dict) -> str:
    singles = [
        row
        for row in report["cases"]
        if row["primary_hit"] is True and len(row["expected"]["labels"]) == 1 and row["top1_score"] is not None
    ]
    min_score = min(row["top1_score"] for row in singles) if singles else None
    gaps = [row["gap"] for row in singles if row["gap"] is not None]
    min_gap = min(gaps) if gaps else None
    tight = [row["id"] for row in report["cases"] if row["confident"] and row["meets_gap"] is False]
    floor = report["accept"]
    opened = report["gap"]
    both = [
        row["id"]
        for row in report["cases"]
        if not row["confident"]
        and row["top1_score"] is not None
        and row["top2_score"] is not None
        and row["top1_score"] >= floor
        and row["top2_score"] >= floor
        and row["gap"] is not None
        and row["gap"] < opened
    ]
    return (
        f"Минимальный score верного одиночного типа: {_num(min_score)}. "
        f"Минимальный разрыв верного одиночного типа: {_num(min_gap)}. "
        f"Уверенные ответы с разрывом ниже порога: {_names(tight)}. "
        f"Вопросы, где оба лидера не ниже accept, а разрыв ниже порога: {_names(both)}."
    )


def _expected_cell(expected: dict) -> str:
    if expected["kind"] == "question":
        return f"вопрос: {expected['reason']}"
    labels = expected["labels"]
    if len(labels) > 1:
        return " + ".join(labels)
    return expected["primary"] or "—"


def _answer_cell(row: dict) -> str:
    if not row["confident"]:
        return f"вопрос: {row['reason']}"
    if len(row["labels"]) > 1:
        return " + ".join(row["labels"])
    return row["primary"] or "—"


def _score_cell(type_id: str | None, score: float | None) -> str:
    if type_id is None:
        return "—"
    return f"{type_id} {_num(score)}"


def _ratio(hit: int, total: int, rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{hit}/{total} = {rate:.3f}"


def _num(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}"


def _yes(flag: bool) -> str:
    return "да" if flag else "нет"


def _names(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "нет"
