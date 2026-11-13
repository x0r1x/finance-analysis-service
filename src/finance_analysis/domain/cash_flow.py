"""Чистый денежный поток за период: приток минус отток.

Обе стороны — неотрицательные объёмы. Скобки уже означают минус, поэтому
берётся модуль: второй минус не превращает вычитание в сложение. Строка
книги `ncf` сверяется и в формулу не входит.
"""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.glossary import normalize_label
from finance_analysis.domain.metrics import (
    MONEY,
    _flow_basis,
    _payment,
    _row,
    _scale_policy,
    _sums,
    aligned_keys,
    unconfirmed_scale,
)

_TOL = Decimal("0.01")
_BOUND = frozenset({"bound", "bound_with_warning"})
_HUMAN = frozenset({"confirmed", "profile"})


def _folded(texts: tuple[str, ...]) -> frozenset[str]:
    return frozenset(normalize_label(text) for text in texts)


_COMPANY_IN = _folded(
    ("Приток денежных средств", "Поступление денежных средств за период", "cash inflows")
)
_SECTION_IN = _folded(("Поступления — всего", "Поступления - всего"))
_COMPANY_OUT = _folded(
    ("Отток денежных средств", "Выбытие денежных средств за период", "cash outflows")
)
_SECTION_OUT = _folded(("Платежи — всего", "Платежи - всего"))


def net_cash_flow(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    absent: frozenset[str] = frozenset(),
) -> dict:
    """NCF(t) = |приток| − |отток| на одном периоде. Дыра периода нулём не закрывается."""

    inflow, inflow_error = _side(bindings, "cash_inflow", _COMPANY_IN, _SECTION_IN, absent)
    outflow, outflow_error = _side(bindings, "cash_outflow", _COMPANY_OUT, _SECTION_OUT, absent)
    if inflow_error or outflow_error:
        return _stopped(
            "ncf_ambiguous",
            "Две строки одного уровня в одном разделе. Чистый денежный поток не рассчитан.",
        )
    if not inflow:
        return _missing("cash_inflow", absent)
    if not outflow:
        return _missing("cash_outflow", absent)
    chosen = [*inflow, *outflow]
    if unconfirmed_scale(facts, chosen) or _scale_policy(facts, chosen) == "sheet":
        return _stopped(
            "scale_unconfirmed",
            "Масштаб притока и оттока не подтверждён. Чистый денежный поток не рассчитан.",
        )
    if {_flow_basis(row) for row in chosen} != {"period"}:
        return _stopped(
            "basis_mismatch",
            "Способ показа притока и оттока не один период. Чистый денежный поток не рассчитан.",
        )
    if len(_currencies(facts, chosen)) > 1:
        return _stopped(
            "ncf_currency",
            "Приток и отток в разной валюте. Чистый денежный поток не рассчитан.",
        )
    aligned = aligned_keys(periods)
    left = _volumes(facts, inflow, aligned, periods, sign_convention)
    right = _volumes(facts, outflow, aligned, periods, sign_convention)
    cited = _primary(bindings, "ncf", absent) or _primary(bindings, "cash_net", absent)
    cited_series = _sums(facts, cited, aligned, periods) if cited is not None else {}
    rows = []
    warned = False
    warnings: list[dict] = []
    seen: set[tuple] = set()
    for period in periods:
        own = (period["axis_id"], period["period_id"])
        key = aligned.get(own, own)
        if key in seen or key not in left or key not in right:
            seen.add(key)
            continue
        seen.add(key)
        value = (left[key] - right[key]).quantize(MONEY)
        rows.append(_row("ncf", period, value, "computed", None))
        if warned or key not in cited_series:
            continue
        book = cited_series[key]
        if abs(book - value) > _TOL:
            warned = True
            warnings.append(
                {
                    "code": "ncf_book_mismatch",
                    "params": {
                        "metric": "ncf",
                        "period_id": period["period_id"],
                        "fas": str(value),
                        "model": str(book),
                    },
                }
            )
    if not rows:
        return _stopped(
            "ncf_period_gap",
            "Нет периода, где есть и приток, и отток. Чистый денежный поток не рассчитан.",
        )
    return {"metric": "ncf", "rows": rows, "needs_input": [], "warnings": warnings, "status": "succeeded"}


def _side(
    bindings: list[dict],
    concept: str,
    company: frozenset[str],
    section: frozenset[str],
    absent: frozenset[str],
) -> tuple[list[dict], str | None]:
    """Строки агрегата. Строка на организацию глушит итоги разделов."""

    company_rows: list[dict] = []
    section_rows: list[dict] = []
    unlabeled: list[dict] = []
    for row in bindings:
        if row.get("effective_concept") != concept or row.get("status") not in _BOUND:
            continue
        if concept in absent and row.get("source") not in _HUMAN:
            continue
        key = _label_key(row)
        if key in company:
            company_rows.append(row)
        elif key in section:
            section_rows.append(row)
        elif not key:
            unlabeled.append(row)
    if len(company_rows) > 1:
        return [], "ambiguous"
    if company_rows:
        return company_rows, None
    seen: set[str] = set()
    for row in section_rows:
        parent = _section_key(row)
        if parent in seen:
            return [], "ambiguous"
        seen.add(parent)
    if section_rows:
        return section_rows, None
    if len(unlabeled) > 1:
        return [], "ambiguous"
    return unlabeled, None


def _label_key(row: dict) -> str:
    text = row.get("matched_label_id") or row.get("matched_label") or ""
    if not isinstance(text, str) or not text.strip():
        return ""
    return normalize_label(text)


def _section_key(row: dict) -> str:
    explicit = row.get("section")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    path = row.get("label_path_text")
    if isinstance(path, str) and " › " in path:
        parent, _leaf = path.rsplit(" › ", 1)
        return parent
    return str(row.get("row_key") or "")


def _volumes(
    facts: list[dict],
    rows: list[dict],
    aligned: dict,
    periods: list[dict],
    convention: str,
) -> dict[tuple, Decimal]:
    totals: dict[tuple, Decimal] = {}
    for binding in rows:
        for key, number in _sums(facts, binding, aligned, periods).items():
            totals[key] = totals.get(key, Decimal(0)) + abs(_payment(number, convention))
    return totals


def _currencies(facts: list[dict], rows: list[dict]) -> set[str]:
    keys = {row.get("row_key") for row in rows}
    found: set[str] = set()
    for fact in facts:
        if fact.get("row_key") not in keys:
            continue
        currency = fact.get("currency")
        if currency not in (None, ""):
            found.add(str(currency))
    return found


def _primary(bindings: list[dict], concept: str, absent: frozenset[str]) -> dict | None:
    found = None
    for row in bindings:
        if row.get("effective_concept") != concept or not row.get("is_primary"):
            continue
        if row.get("status") not in _BOUND:
            continue
        if concept in absent and row.get("source") not in _HUMAN:
            continue
        found = row
    return found


def _missing(subject: str, absent: frozenset[str]) -> dict:
    reason = "absent_in_book" if subject in absent else "concept_unknown"
    return {
        "metric": "ncf",
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
        "warnings": [],
        "status": "missing_input",
    }


def _stopped(code: str, message: str) -> dict:
    return {
        "metric": "ncf",
        "rows": [],
        "needs_input": [],
        "warnings": [{"code": code, "params": {"metric": "ncf", "message": message}}],
        "status": "not_computed",
    }
