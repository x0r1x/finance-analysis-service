"""Отчёт из сохранённого AnalysisResult. md — шаблон, не контракт (§6.6, решение 27)."""

from __future__ import annotations

import json

from finance_analysis.domain.errors import NotAcceptable

REPORT_FORMATS = ("json", "md")
MODEL_FORMATS = ("json", "yaml", "md")


def choose_format(fmt: str | None, accept: str | None, allowed: tuple[str, ...]) -> str:
    """`format=` важнее Accept. Пустой format и */*|json — json."""

    if fmt:
        if fmt not in allowed:
            raise NotAcceptable("формат не поддерживается", extra={"formats": list(allowed)})
        return fmt
    header = (accept or "*/*").lower()
    if "text/markdown" in header and "md" in allowed:
        return "md"
    if ("application/yaml" in header or "text/yaml" in header) and "yaml" in allowed:
        return "yaml"
    if "application/json" in header or "*/*" in header or "application/problem+json" in header:
        return "json"
    raise NotAcceptable("формат не поддерживается", extra={"formats": list(allowed)})


def _show(value) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return "" if value is None else str(value)


def _lines(title: str, payload: dict) -> list[str]:
    rows = [f"## {title}"]
    for key in sorted(payload):
        rows.append(f"- {key}: {_show(payload[key])}")
    return rows


def render_markdown(result: dict) -> str:
    """Один и тот же result даёт одни и те же байты. Полей вне result нет."""

    lines = [f"# {result.get('analysis_id')}", "", f"status: {result.get('status')}", ""]
    lines.extend(_lines("builder_ref", result.get("builder_ref") or {}))
    lines.append("")
    lines.extend(_lines("versions", result.get("versions") or {}))
    text = (result.get("summary") or {}).get("text")
    if text:
        lines.extend(["", "## summary", str(text)])
    data = result.get("result_data") or {}
    ratios = data.get("ratios") or []
    if ratios:
        lines.extend(["", "## ratios", "| metric | period_id | value | status |", "| --- | --- | --- | --- |"])
        for row in ratios:
            lines.append(
                f"| {_show(row.get('metric'))} | {_show(row.get('period_id'))} | {_show(row.get('value'))} | {_show(row.get('status'))} |"
            )
    findings = data.get("findings") or []
    if findings:
        lines.extend(["", "## findings"])
        for item in findings:
            note = item.get("explanation")
            note_text = note if isinstance(note, str) else ""
            lines.append(f"- {_show(item.get('code'))} {_show(item.get('fingerprint'))} {note_text}".rstrip())
    impact = data.get("impact")
    if isinstance(impact, dict):
        lines.extend(["", *_lines("impact", impact)])
    return "\n".join(lines) + "\n"


def render_json(result: dict) -> bytes:
    return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode()
