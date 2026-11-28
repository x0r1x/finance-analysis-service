"""Группировка фактов в prepare_rows и вынос синхронной привязки из цикла событий."""

import threading
from types import SimpleNamespace

import anyio

from finance_analysis.application import service as service_module
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.project import (
    _sign_map,
    _unit_map,
    derive_rows,
    prepare_rows,
)
from finance_analysis.application.service import FasService
from finance_analysis.domain.semantics import empty_series, exclusion, infer_row

CATALOG = load_catalog()


class _FactList(list):
    """Считает полные проходы по списку фактов. Индекс по строке — один проход."""

    def __init__(self, items):
        super().__init__(items)
        self.scans = 0

    def __iter__(self):
        self.scans += 1
        return super().__iter__()


def _row(key: str, label: str, **extra) -> dict:
    return {
        "model_id": "m",
        "build_key": "b",
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": label,
        "check_row": False,
        "sheet": "CF",
        "unit": "money",
        "row_num": extra.pop("row_num", 1),
        **extra,
    }


def _fact(row_key, status, value="1", period="p1") -> dict:
    return {
        "row_key": row_key,
        "axis_id": "ax",
        "period_id": period,
        "value_status": status,
        "value_dec": value,
        "normalized_value": value,
    }


def _projected(rows: list[dict]) -> dict:
    return {
        "dim_row": rows,
        "dim_period": [
            {
                "model_id": "m",
                "build_key": "b",
                "axis_id": "ax",
                "period_id": "p1",
                "period_index": 0,
                "axis_kind": "timeline",
            }
        ],
    }


def _events() -> list[dict]:
    return [
        {"seq": 1, "type": "sign.set", "target": "valued", "binding_key": "valued", "value": "inflow"},
        {"seq": 2, "type": "unit.set", "target": "valued", "binding_key": "valued", "value": "money"},
    ]


def _book() -> tuple[dict, list[dict]]:
    rows = [
        _row("valued", "Выручка"),
        _row("blank", "Пустая строка"),
        _row("missing", "Нет фактов"),
        _row("mixed", "Смесь"),
        _row("check", "Проверка", check_row=True),
        _row("hidden", "Скрытая", hidden=True),
        _row("outline_blank", "Свёрнутая пустая", hidden=True, hidden_by_outline=True),
        _row("outline_valued", "Свёрнутая", hidden=True, hidden_by_outline=True),
        _row("helper", "Служебная", kind="helper"),
        _row("status_none", "Без статуса"),
        _row("blank_text", "Пустой текст статуса"),
        _row("total", "Итого выручка"),
    ]
    facts = [
        _fact("valued", "empty", None, "p0"),
        _fact("valued", "cached", "10"),
        _fact("blank", "empty", None),
        _fact("blank", "not_applicable", None, "p2"),
        _fact("mixed", "empty", None, "p0"),
        _fact("mixed", "cached", "1"),
        _fact("check", "cached", "5"),
        _fact("hidden", "cached", "5"),
        _fact("outline_blank", None, None),
        _fact("outline_valued", "cached", "3"),
        _fact("helper", "cached", "7"),
        _fact("status_none", None, "0"),
        _fact("blank_text", "", "4"),
        _fact("total", "cached", "20"),
        {"axis_id": "ax", "period_id": "p1", "value_status": "cached", "value_dec": "99", "normalized_value": "99"},
    ]
    return _projected(rows), facts


def _nested_prepare(projected, events, glossary, facts):
    """Прежний проход: empty_series смотрит все факты для каждой строки."""

    signs = _sign_map(events)
    units = _unit_map(events)
    prepared = []
    for row in projected["dim_row"]:
        excluded, reason = exclusion(row, empty_series=empty_series(row["row_key"], facts))
        inferred = infer_row(row, glossary.flows)
        prepared.append(
            {
                **row,
                "excluded": excluded,
                "exclusion_reason": reason,
                "sign": signs.get(row["binding_key"], inferred["sign"]),
                "nature": inferred["nature"],
                "aggregation": inferred["aggregation"],
                "unit_decision": units.get(row["binding_key"]),
            }
        )
    return prepared


def _without_clock(derived: dict) -> dict:
    bindings = []
    for row in derived["bindings"]:
        item = dict(row)
        item.pop("updated_at_utc", None)
        bindings.append(item)
    return {**derived, "bindings": bindings}


def test_prepare_rows_matches_nested_empty_series():
    projected, facts = _book()
    events = _events()
    indexed = prepare_rows(projected, events, CATALOG, facts)
    nested = _nested_prepare(projected, events, CATALOG, facts)
    assert indexed == nested
    reasons = {row["row_key"]: row["exclusion_reason"] for row in indexed}
    assert reasons == {
        "valued": None,
        "blank": "empty_series",
        "missing": "empty_series",
        "mixed": None,
        "check": "check_row",
        "hidden": "hidden",
        "outline_blank": "empty_series",
        "outline_valued": None,
        "helper": "helper",
        "status_none": "empty_series",
        "blank_text": None,
        "total": None,
    }
    valued = next(row for row in indexed if row["row_key"] == "valued")
    assert valued["sign"] == "inflow"
    assert valued["unit_decision"] == "money"
    assert next(row for row in indexed if row["row_key"] == "total")["aggregation"] == "aggregate"

    shared = {
        "state_seq": 1,
        "derive": "d",
        "versions": {"glossary": "none"},
        "events": events,
        "glossary": CATALOG,
        "facts": facts,
    }
    left = derive_rows(projected, prepared=indexed, **shared)
    right = derive_rows(projected, prepared=nested, **shared)
    assert _without_clock(left) == _without_clock(right)
    excluded = {row["row_key"]: row["exclusion_reason"] for row in left["row_semantics"]}
    assert excluded["blank"] == "empty_series"
    assert excluded["valued"] is None
    assert {row["row_key"] for row in left["bindings"]} == {
        row["row_key"] for row in projected["dim_row"] if row["kind"] == "fact"
    }


def test_missing_facts_do_not_mark_an_empty_series():
    projected = _projected([_row("valued", "Выручка")])
    indexed = prepare_rows(projected, [], CATALOG, None)
    assert indexed == _nested_prepare(projected, [], CATALOG, None)
    assert indexed[0]["excluded"] is False
    assert indexed[0]["exclusion_reason"] is None


def test_prepare_rows_scans_facts_once():
    rows = 400
    periods = 11
    body = []
    for index in range(rows):
        key = f"r{index:04d}"
        status = "empty" if index % 5 == 0 else "cached"
        for period in range(periods):
            body.append(
                {
                    "row_key": key,
                    "axis_id": "ax",
                    "period_id": f"p{period}",
                    "value_status": status,
                    "normalized_value": "0" if status == "empty" else "1",
                }
            )
    facts = _FactList(body)
    projected = _projected([_row(f"r{index:04d}", "Выручка", row_num=index) for index in range(rows)])
    prepared = prepare_rows(projected, [], CATALOG, facts)
    assert facts.scans == 1
    by_key = {row["row_key"]: row for row in prepared}
    assert by_key["r0000"]["exclusion_reason"] == "empty_series"
    assert by_key["r0001"]["excluded"] is False
    assert by_key["r0001"]["exclusion_reason"] is None


async def test_derive_runs_sync_binding_off_the_event_loop(monkeypatch):
    main = threading.get_ident()
    seen = {"prepare": [], "derive": []}
    real_prepare = service_module.prepare_rows
    real_derive = service_module.derive_rows

    def prepare(*args, **kwargs):
        seen["prepare"].append(threading.get_ident())
        return real_prepare(*args, **kwargs)

    def derive(*args, **kwargs):
        seen["derive"].append(threading.get_ident())
        return real_derive(*args, **kwargs)

    monkeypatch.setattr(service_module, "prepare_rows", prepare)
    monkeypatch.setattr(service_module, "derive_rows", derive)

    service = FasService.__new__(FasService)
    service._cpu = anyio.CapacityLimiter(2)

    async def package(_version, _events):
        return CATALOG

    class _Calibrators:
        async def active(self):
            return None

    service._book_package = package
    service.calibrators = _Calibrators()
    service.pipeline = SimpleNamespace(enabled=False)

    projected, facts = _book()
    events = _events()
    derived = await service._derive(
        "job",
        projected,
        state_seq=1,
        derive="d",
        versions={"glossary": "none"},
        events=events,
        facts=facts,
        links=[],
        learn=False,
    )
    assert seen["prepare"] == [seen["prepare"][0]]
    assert seen["derive"] == [seen["derive"][0]]
    assert seen["prepare"][0] != main
    assert seen["derive"][0] != main
    direct = real_derive(
        projected,
        state_seq=1,
        derive="d",
        versions={"glossary": "none"},
        events=events,
        glossary=CATALOG,
        facts=facts,
        prepared=real_prepare(projected, events, CATALOG, facts),
    )
    assert _without_clock(derived) == _without_clock(direct)
