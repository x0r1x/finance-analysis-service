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
    """Чтение входов формулы. Имя вне обязательных и условных — ошибка."""

    __slots__ = ("_declared", "_values")

    def __init__(
        self,
        declared: tuple[str, ...],
        values: Mapping[str, object],
        optional: tuple[str, ...] = (),
    ) -> None:
        self._declared = frozenset(declared) | frozenset(optional)
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
    """profile_inputs is None — профиль состав не задаёт.

    Кортеж, в том числе пустой, — дополнительные понятия договорной формулы
    сверх inputs и optional_inputs. interest и interest_paid этим полем не сливаются.
    """

    metric_id: str
    formula_id: str
    version: str
    function: Callable[..., object]
    inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...] = ()
    profile_inputs: tuple[str, ...] | None = None


REGISTRY: dict[tuple[str, str], Implementation] = {}


def _qualified(function: Callable[..., object]) -> str:
    return f"{function.__module__}.{function.__qualname__}"


def implements(
    metric_id: str,
    formula_id: str,
    *,
    version: str = "",
    inputs: tuple[str, ...] = (),
    optional_inputs: tuple[str, ...] = (),
    profile_inputs: tuple[str, ...] | None = None,
):
    """Помечает функцию реализации. Другая функция на том же ключе — ошибка.

    profile_inputs=None — профильной формулы нет. Кортеж объявляет
    дополнительные понятия, которые договорный состав может назвать.
    """

    def decorate(function: Callable[..., object]) -> Callable[..., object]:
        key = (metric_id, formula_id)
        current = REGISTRY.get(key)
        if current is not None and _qualified(current.function) != _qualified(function):
            raise DuplicateImplementation(f"реализация уже зарегистрирована: {metric_id} {formula_id}")
        REGISTRY[key] = Implementation(
            metric_id,
            formula_id,
            version,
            function,
            tuple(inputs),
            tuple(optional_inputs),
            None if profile_inputs is None else tuple(profile_inputs),
        )
        return function

    return decorate


# Пустые inputs законны только здесь: состав зависит от профиля, стандарта или аргумента.
DYNAMIC_INPUTS: dict[tuple[str, str], str] = {
    ("dscr", "dscr.corporate_covenant"): "состав заменяет профиль",
    ("dscr", "dscr.housing"): "флаги профиля меняют знаменатель",
    ("icr", "icr.bank"): "стандарт и флаг аренды меняют числитель",
    ("adscr", "adscr.housing"): "ряд считает housing_dscr, состав зависит от профиля",
    ("dscr_min", "dscr_min.housing"): "ряд считает housing_dscr",
    ("dscr_avg", "dscr_avg.housing"): "ряд считает housing_dscr",
    ("llcr", "llcr.cbr590"): "гарантированные деньги зависят от профиля, долг читается шире формулы",
    ("llcr", "llcr.domrf"): "лимит и старшее тело читаются по правилу варианта",
    ("total_debt", "total_debt"): "набор зависит от debt_standard и флага аренды",
    ("escrow_blended_rate", "escrow_blended_rate"): "входы читаются только при шкале профиля",
    ("debt_incl_off_balance", "debt_incl_off_balance"): "слагаемые приходят аргументом из каталога",
    ("fcf_identity", "fcf_identity"): "без названного варианта ряд не читается",
}

# Нет отдельной функции: лестница считает формулу общим маршрутом select_ratio → composed_ratio.
COMMON_ROUTE: dict[tuple[str, str], str] = {
    ("net_debt_ebitda", "net_debt_ebitda"): "состав целиком из каталога",
    ("escrow_coverage", "escrow_coverage"): "состав целиком из каталога",
    ("total_debt_ebitda", "total_debt_ebitda"): "состав целиком из каталога",
    ("debt_off_balance_ebitda", "debt_off_balance_ebitda"): "состав из каталога, забаланс только снимает обязательность",
}

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


def profile_definition_problems(
    definitions: Mapping[tuple[str, str], Mapping[str, object]],
    registry: Mapping[tuple[str, str], Implementation],
) -> list[str]:
    """Состав договорных формул против реестра. Пустой список — нарушений нет.

    Ключ определения — (metric_id, formula_id). Тело — числитель и знаменатель,
    уже без полей профиля. Реализация без profile_inputs состав не принимает.
    """

    problems: list[str] = []
    for metric_id, formula_id in sorted(definitions):
        item = registry.get((metric_id, formula_id))
        if item is None:
            problems.append(f"{formula_id}: нет реализации в реестре")
            continue
        if item.profile_inputs is None:
            problems.append(f"{formula_id}: профильный состав не объявлен")
            continue
        allowed = set(item.inputs) | set(item.optional_inputs) | set(item.profile_inputs)
        extra = sorted(composition_concepts(definitions[(metric_id, formula_id)]) - allowed)
        if extra:
            problems.append(f"{formula_id}: необъявленные профильные входы: {', '.join(extra)}")
    return problems


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
        if (metric_id, formula_id) not in DYNAMIC_INPUTS:
            problems.append(f"{formula_id}: пустые inputs вне DYNAMIC_INPUTS")
        return
    declared = set(item.inputs) | set(item.optional_inputs)
    extra = sorted(composition_concepts(body) - declared)
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
