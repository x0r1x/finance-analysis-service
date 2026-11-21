"""Реестр реализаций формул. Лестница расчёта его не читает."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


class DuplicateImplementation(ValueError):
    """Повтор ключа (metric_id, formula_id)."""


class ImplementationContractError(ValueError):
    """Формула каталога не сходится с реестром."""


class UndeclaredInput(KeyError):
    """Имя не входит в объявленные входы формулы."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"вход не объявлен: {self.name}"


class BoundInputs:
    """Чтение входов формулы. Имя вне объявленного набора — ошибка."""

    __slots__ = ("_declared", "_values")

    def __init__(self, declared: tuple[str, ...], values: Mapping[str, object]) -> None:
        self._declared = frozenset(declared)
        self._values = values

    def get(self, name: str, default: object = None) -> object:
        self._require(name)
        return self._values.get(name, default)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        self._require(name)
        return name in self._values

    def __getitem__(self, name: str) -> object:
        self._require(name)
        return self._values[name]

    def _require(self, name: str) -> None:
        if name not in self._declared:
            raise UndeclaredInput(name)


@dataclass(frozen=True, slots=True)
class Implementation:
    metric_id: str
    formula_id: str
    version: str
    function: Callable[..., object]
    inputs: tuple[str, ...]


REGISTRY: dict[tuple[str, str], Implementation] = {}


def _qualified(function: Callable[..., object]) -> str:
    return f"{function.__module__}.{function.__qualname__}"


def implements(
    metric_id: str,
    formula_id: str,
    *,
    version: str = "",
    inputs: tuple[str, ...] = (),
):
    """Помечает функцию реализации. Другая функция на том же ключе — ошибка."""

    def decorate(function: Callable[..., object]) -> Callable[..., object]:
        key = (metric_id, formula_id)
        current = REGISTRY.get(key)
        if current is not None and _qualified(current.function) != _qualified(function):
            raise DuplicateImplementation(f"реализация уже зарегистрирована: {metric_id} {formula_id}")
        REGISTRY[key] = Implementation(metric_id, formula_id, version, function, tuple(inputs))
        return function

    return decorate


# Нет отдельной функции: лестница считает формулу общим маршрутом.
# Четыре метрики ниже — select_ratio → composed_ratio, состав целиком из каталога.
COMMON_ROUTE: frozenset[tuple[str, str]] = frozenset(
    {
        ("net_debt_ebitda", "net_debt_ebitda"),
        ("escrow_coverage", "escrow_coverage"),
        ("total_debt_ebitda", "total_debt_ebitda"),
        ("debt_off_balance_ebitda", "debt_off_balance_ebitda"),
    }
)

_IMPLEMENTATION_MODULES = (
    "finance_analysis.domain.cash_flow",
    "finance_analysis.domain.cover_metrics",
    "finance_analysis.domain.covenant",
    "finance_analysis.domain.debt_incl_off_balance",
    "finance_analysis.domain.free_cash_flow",
    "finance_analysis.domain.housing_cover",
    "finance_analysis.domain.housing_dscr",
    "finance_analysis.domain.metrics",
    "finance_analysis.domain.net_cash_flow",
    "finance_analysis.domain.returns",
    "finance_analysis.domain.total_debt",
)


def load_implementations() -> None:
    """Импорт вешает @implements. Диспетчер расчёта эти метки не вызывает."""

    for name in _IMPLEMENTATION_MODULES:
        __import__(name)


def formula_id_of(metric_id: str, variant: str | None, body: Mapping[str, object]) -> str:
    declared = body.get("formula_id")
    if isinstance(declared, str) and declared:
        return declared
    if variant is None:
        return metric_id
    return f"{metric_id}.{variant}"


def composition_concepts(body: Mapping[str, object]) -> frozenset[str]:
    """Понятия состава формулы. base — наследование, не вход."""

    found: set[str] = set()
    for field in ("numerator", "denominator"):
        if field in body:
            found.update(_term_names(body.get(field)))
    if "rate" in body:
        found.update(_string_names(body.get("rate")))
    for field in ("terminal", "compare_with"):
        found.update(_string_names(body.get(field)))
    add_back = body.get("add_back")
    if isinstance(add_back, dict):
        found.update(_string_names(add_back.get("concept")))
        found.update(_string_names(add_back.get("tax_complement")))
    return frozenset(found)


def check_registry(metrics: Mapping[str, object]) -> None:
    """Каждая формула каталога есть в реестре, состав не шире объявленных входов."""

    problems: list[str] = []
    for metric_id, body in metrics.items():
        if not isinstance(body, dict):
            continue
        _check_formula(str(metric_id), None, body, problems)
        variants = body.get("variants") or {}
        if isinstance(variants, dict):
            for variant, spec in variants.items():
                if isinstance(spec, dict):
                    _check_formula(str(metric_id), str(variant), spec, problems)
    if problems:
        raise ImplementationContractError("\n".join(sorted(problems)))


def _check_formula(
    metric_id: str,
    variant: str | None,
    body: Mapping[str, object],
    problems: list[str],
) -> None:
    formula_id = formula_id_of(metric_id, variant, body)
    if (metric_id, formula_id) in COMMON_ROUTE:
        return
    item = REGISTRY.get((metric_id, formula_id))
    if item is None:
        problems.append(f"{formula_id}: нет реализации в реестре")
        return
    if not item.inputs:
        return
    extra = sorted(composition_concepts(body) - set(item.inputs))
    if extra:
        problems.append(f"{formula_id}: необъявленные входы: {', '.join(extra)}")


def _term_names(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for side in ("plus", "minus"):
            found.update(_string_names(value.get(side)))
        return found
    return _string_names(value)


def _string_names(value: object) -> set[str]:
    if isinstance(value, str) and value:
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str) and item}
    return set()
