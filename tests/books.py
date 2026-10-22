"""Алиасы книг builder, закоммиченных в репозиторий.

Каталог на диске назван реальным job_id. Тесты и k6 обращаются к книгам по алиасу.
"""

from __future__ import annotations

from pathlib import Path

BUILDER_ROOT = Path(__file__).resolve().parent / "fixtures" / "builder"

ALIASES = {
    "packt": "2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e",
    "rvi": "2f180b3eec3b8557908beafa659af75dd7c2e93dab02b176f3cab1d625ee7bac",
}

# Ячейки книги packt, ось Operation!r2, период Y5 (колонка I).
PACKT_AXIS = "Operation!r2"
PACKT_PERIOD = "Y5"
PACKT_REVENUE_ROW = "Operation|10|Operation!r2"
PACKT_REVENUE_CELL = "Operation!I10"
PACKT_REVENUE_VALUE = "11125"
PACKT_TRAFFIC_PC_ROW = "Operation|7|Operation!r2"
PACKT_TRAFFIC_HV_ROW = "Operation|8|Operation!r2"
PACKT_TRAFFIC_DIFF = "325000"
PACKT_PHASE_AXIS = "TBA!r2"


def job_id(alias: str) -> str:
    try:
        return ALIASES[alias]
    except KeyError as exc:
        raise KeyError(f"неизвестный алиас книги: {alias}") from exc
