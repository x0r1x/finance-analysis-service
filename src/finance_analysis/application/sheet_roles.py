"""Роли листа: формы из corporate.yaml, итоги и допущения из configs/sheet_roles.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from finance_analysis.application.catalog import catalog_file
from finance_analysis.domain.mapping import SheetRoles


def load_sheet_roles(path: Path | None = None) -> SheetRoles:
    folder = catalog_file().parent.parent
    corporate = yaml.safe_load((folder / "model_types" / "corporate.yaml").read_text(encoding="utf-8")) or {}
    statement: list[str] = []
    for signal in corporate.get("signals") or []:
        if not isinstance(signal, dict) or signal.get("kind") != "sheets_any":
            continue
        for group in signal.get("groups") or []:
            statement.extend(str(name) for name in group)
    body = yaml.safe_load((path or folder / "sheet_roles.yaml").read_text(encoding="utf-8")) or {}
    return SheetRoles(
        statement=tuple(statement),
        outputs=tuple(str(name) for name in body.get("outputs") or ()),
        assumptions=tuple(str(name) for name in body.get("assumptions") or ()),
    )
