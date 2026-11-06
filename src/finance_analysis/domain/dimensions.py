"""Размерность понятия. Конкретная единица (RUB, MWh) и масштаб живут в книге.

`kind` и прежний `unit` читаются как устаревшие алиасы. `ratio` в `kind` —
математическая форма, не роль. Знак `stock` — не знак, а временная природа.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

ROLES = frozenset({"measure", "assumption", "parameter"})
TEMPORAL = frozenset({"stock", "flow", "rate", "point_in_time"})
SIGNS = frozenset({"inflow", "outflow"})
AGGREGATIONS = frozenset({"sum", "last", "average", "none"})
PRICING_BASES = frozenset({"energy", "capacity"})
BILLING_PERIODS = frozenset({"year", "quarter", "month", "day"})
OBJECT_AGGREGATIONS = frozenset({"weighted_average"})
# Вес — экстенсивная величина, согласованная с тем, что усредняют.
# Ставка взвешивается остатком, объёмом или числом. Тариф энергии — только энергией,
# тариф мощности — только мощностью. Совпадение показателей само по себе пару не разрешает.
_WEIGHT_DIMENSIONS = {
    "ratio": frozenset({"money", "energy", "power", "count", "area", "duration"}),
    "currency_per_energy": frozenset({"energy"}),
    "currency_per_power_time": frozenset({"power"}),
}
_AGGREGATION = {"flow": "sum", "stock": "last", "rate": "none", "point_in_time": "last"}
_KIND_ROLE = {"measure": "measure", "parameter": "parameter", "assumption": "assumption", "ratio": "measure"}
_UNIT_DIMENSION = {"money": "money", "ratio": "ratio", "percent": "ratio", "count": "count"}
_COARSE_UNIT = {"money": "money", "ratio": "ratio", "count": "count"}
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class DimensionCatalog:
    """Показатели степеней базовых величин и какие единицы к какой размерности относятся."""

    exponents: Mapping[str, Mapping[str, int]]
    units: Mapping[str, str]
    pricing_basis: Mapping[str, str] = field(default_factory=dict)
    unit_currency: Mapping[str, str] = field(default_factory=dict)
    unit_billing_period: Mapping[str, str] = field(default_factory=dict)

    def same(self, left: str, right: str) -> bool:
        one, other = self.exponents.get(left), self.exponents.get(right)
        return one is not None and dict(one) == dict(other)

    def combine(self, op: str, left: str, right: str) -> Mapping[str, int] | None:
        """Сложение требует равные показатели. Частное и произведение их вычитают или складывают."""

        one, other = self.exponents.get(left), self.exponents.get(right)
        if one is None or other is None or op not in {"add", "ratio", "product"}:
            return None
        if op == "add":
            return dict(one) if dict(one) == dict(other) else None
        sign = -1 if op == "ratio" else 1
        found: dict[str, int] = {}
        for key in set(one) | set(other):
            power = one.get(key, 0) + sign * other.get(key, 0)
            if power:
                found[key] = power
        return found

    def matches(self, name: str, exponents: Mapping[str, int]) -> bool:
        current = self.exponents.get(name)
        return current is not None and dict(current) == dict(exponents)


def parse_catalog(document: dict) -> DimensionCatalog:
    raw = document.get("dimensions") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ValueError("dimensions")
    exponents: dict[str, dict[str, int]] = {}
    units: dict[str, str] = {}
    pricing: dict[str, str] = {}
    currencies: dict[str, str] = {}
    billing: dict[str, str] = {}
    compounds: list[tuple[str, dict]] = []
    for key, body in raw.items():
        name = str(key)
        if not _NAME.fullmatch(name) or not isinstance(body, dict):
            raise ValueError(name)
        basis = body.get("pricing_basis")
        if basis is not None and (not isinstance(basis, str) or basis not in PRICING_BASES):
            raise ValueError(name)
        if isinstance(basis, str):
            pricing[name] = basis
        for unit, currency, period in _unit_facts(body.get("units"), name):
            if unit in units:
                raise ValueError(unit)
            units[unit] = name
            if currency is not None:
                currencies[unit] = currency
            if period is not None:
                billing[unit] = period
        if body.get("dimensionless") is True or name == "ratio":
            exponents[name] = {}
            continue
        if body.get("base") is True:
            exponents[name] = {name: 1}
            continue
        compounds.append((name, body))
    for name, body in compounds:
        powers = body.get("exponents")
        if not isinstance(powers, dict) or not powers:
            raise ValueError(name)
        cleaned: dict[str, int] = {}
        for base, power in powers.items():
            if base not in exponents or exponents[base] != {base: 1}:
                raise ValueError(f"{name}:{base}")
            if isinstance(power, bool) or not isinstance(power, int) or power == 0:
                raise ValueError(name)
            cleaned[str(base)] = power
        exponents[name] = cleaned
    return DimensionCatalog(exponents, units, pricing, currencies, billing)


def default_aggregation(temporal: str) -> str:
    """Свёртка по времени. Ставка и коэффициент не усредняются, пока это не написано явно."""

    return _AGGREGATION[temporal]


def _unit_facts(raw: object, name: str) -> list[tuple[str, str | None, str | None]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError(name)
    found: list[tuple[str, str | None, str | None]] = []
    for item in raw:
        if isinstance(item, str) and item:
            found.append((item, None, None))
            continue
        if not isinstance(item, dict):
            raise TypeError(name)
        unit = item.get("unit")
        currency = item.get("currency")
        period = item.get("billing_period")
        if not isinstance(unit, str) or not unit:
            raise ValueError(name)
        if currency is not None and not isinstance(currency, str):
            raise ValueError(name)
        if period is not None and (not isinstance(period, str) or period not in BILLING_PERIODS):
            raise ValueError(name)
        found.append((unit, currency, period))
    return found


def weight_fits(concept_dimension: str, weight_dimension: str) -> bool:
    """Вес подходит усредняемому понятию. Одинаковые физические показатели этого не доказывают."""

    allowed = _WEIGHT_DIMENSIONS.get(concept_dimension)
    return allowed is not None and weight_dimension in allowed


def coarse_kind(role: str, dimension: str) -> str:
    """Прежний `kind`: parameter покрывает и assumption, ratio — безразмерную меру."""

    if role in {"parameter", "assumption"}:
        return "parameter"
    if dimension == "ratio":
        return "ratio"
    return "measure"


def coarse_unit(dimension: str) -> str:
    """Прежний грубый `unit`. Новая размерность оставляет своё имя: старого слова у неё нет."""

    return _COARSE_UNIT.get(dimension, dimension)


def resolve_axes(body: dict) -> dict[str, str | None]:
    """Новые оси или устаревшие `kind`/`unit`. Пустая строка в значении — ошибка вызывающего.

    Роль берётся только из записи понятия. То, что ячейка — ввод, роль не задаёт.
    `aggregation` — свёртка по времени. Её нет в записи: действует правило по временной природе,
    и это никогда не среднее. `object_aggregation` по времени не выводится.
    """

    if not isinstance(body, dict):
        raise TypeError("concept")
    role = body.get("semantic_role")
    dimension = body.get("dimension")
    temporal = body.get("temporal_nature")
    sign = body.get("expected_sign")
    aggregation = body.get("aggregation")
    kind = body.get("kind")
    unit = body.get("unit")
    if role is None and isinstance(kind, str):
        role = _KIND_ROLE.get(kind)
    if dimension is None and isinstance(unit, str):
        dimension = _UNIT_DIMENSION.get(unit)
    if not isinstance(role, str) or role not in ROLES:
        raise ValueError("semantic_role")
    if not isinstance(dimension, str) or not _NAME.fullmatch(dimension):
        raise ValueError("dimension")
    if isinstance(kind, str):
        mapped = _KIND_ROLE.get(kind)
        if mapped is None or (mapped != role and not (kind == "parameter" and role == "assumption")):
            raise ValueError("kind")
        if kind == "ratio" and role != "measure":
            raise ValueError("kind")
    if isinstance(unit, str):
        mapped_unit = _UNIT_DIMENSION.get(unit)
        if mapped_unit is None or mapped_unit != dimension:
            raise ValueError("unit")
    if sign == "stock":
        if temporal is None:
            temporal = "stock"
        elif temporal != "stock":
            raise ValueError("expected_sign")
        sign = None
    if temporal is None:
        temporal = "rate" if role != "measure" or dimension == "ratio" else "flow"
    if not isinstance(temporal, str) or temporal not in TEMPORAL:
        raise ValueError("temporal_nature")
    if sign is not None and (not isinstance(sign, str) or sign not in SIGNS):
        raise ValueError("expected_sign")
    if temporal == "stock" and sign is not None:
        raise ValueError("expected_sign")
    if aggregation is not None and (not isinstance(aggregation, str) or aggregation not in AGGREGATIONS):
        raise ValueError("aggregation")
    pricing = body.get("pricing_basis")
    billing = body.get("billing_period")
    across = body.get("object_aggregation")
    weight = body.get("weight")
    if pricing is not None and (not isinstance(pricing, str) or pricing not in PRICING_BASES):
        raise ValueError("pricing_basis")
    if pricing == "capacity" and (not isinstance(billing, str) or billing not in BILLING_PERIODS):
        raise ValueError("billing_period")
    if billing is not None and pricing != "capacity":
        raise ValueError("billing_period")
    if across is not None and (not isinstance(across, str) or across not in OBJECT_AGGREGATIONS):
        raise ValueError("object_aggregation")
    if across == "weighted_average":
        if not isinstance(weight, str) or not _NAME.fullmatch(weight):
            raise ValueError("weight")
    elif weight is not None:
        raise ValueError("weight")
    return {
        "semantic_role": role,
        "dimension": dimension,
        "temporal_nature": temporal,
        "expected_sign": sign,
        "aggregation": aggregation,
        "pricing_basis": pricing if isinstance(pricing, str) else None,
        "billing_period": billing if isinstance(billing, str) else None,
        "object_aggregation": across if isinstance(across, str) else None,
        "weight": weight if isinstance(weight, str) else None,
    }
