"""Реестр реализаций формул. Лестница расчёта его не читает."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal


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


Mode = Literal["registered", "composed", "dynamic"]
_MODES = frozenset({"registered", "composed", "dynamic"})
_DEPENDENCY_KINDS = frozenset({"profile", "standard", "variant"})


@dataclass(frozen=True, slots=True)
class ConceptGroup:
    """Понятия, которые реализация читает вместе."""

    name: str
    concepts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConceptDependency:
    """Понятия, которые читаются только в ветке профиля, стандарта или варианта."""

    kind: Literal["profile", "standard", "variant"]
    key: str
    concepts: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in _DEPENDENCY_KINDS:
            raise ImplementationContractError(f"зависимость {self.key}: profile, standard или variant")


@dataclass(frozen=True, slots=True)
class DynamicInputs:
    """Допустимые понятия динамической реализации.

    groups — всегда читаемые группы. dependencies — ветки профиля, стандарта
    или варианта. components — другие формулы, чей набор входит сюда.
    arguments — закрытый список, который вызывающий передаёт аргументом.
    """

    groups: tuple[ConceptGroup, ...] = ()
    dependencies: tuple[ConceptDependency, ...] = ()
    components: tuple[tuple[str, str], ...] = ()
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Implementation:
    """profile_inputs is None — профиль состав не задаёт.

    Кортеж, в том числе пустой, — дополнительные понятия договорной формулы
    сверх inputs и optional_inputs. interest и interest_paid этим полем не сливаются.

    mode — способ реализации: registered, composed или dynamic.
    reason обязательна у composed и dynamic.
    """

    metric_id: str
    formula_id: str
    implementation_version: str
    function: Callable[..., object]
    inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...] = ()
    profile_inputs: tuple[str, ...] | None = None
    mode: Mode = "registered"
    reason: str = ""
    dynamic_inputs: DynamicInputs | None = None


REGISTRY: dict[tuple[str, str], Implementation] = {}


def _qualified(function: Callable[..., object]) -> str:
    return f"{function.__module__}.{function.__qualname__}"


def implements(
    metric_id: str,
    formula_id: str,
    *,
    implementation_version: str = "",
    inputs: tuple[str, ...] = (),
    optional_inputs: tuple[str, ...] = (),
    profile_inputs: tuple[str, ...] | None = None,
    mode: Mode = "registered",
    reason: str = "",
    dynamic_inputs: DynamicInputs | None = None,
):
    """Помечает функцию реализации. Другая функция на том же ключе — ошибка.

    profile_inputs=None — профильной формулы нет. Кортеж объявляет
    дополнительные понятия, которые договорный состав может назвать.
    mode — registered, composed или dynamic. У двух последних нужна причина.
    dynamic_inputs задаёт допустимые понятия только у dynamic.
    """

    def decorate(function: Callable[..., object]) -> Callable[..., object]:
        _require_mode(formula_id, mode, reason)
        if dynamic_inputs is not None and mode != "dynamic":
            raise ImplementationContractError(f"{formula_id}: набор dynamic только у dynamic")
        key = (metric_id, formula_id)
        current = REGISTRY.get(key)
        if current is not None and _qualified(current.function) != _qualified(function):
            raise DuplicateImplementation(f"реализация уже зарегистрирована: {metric_id} {formula_id}")
        REGISTRY[key] = Implementation(
            metric_id,
            formula_id,
            implementation_version,
            function,
            tuple(inputs),
            tuple(optional_inputs),
            None if profile_inputs is None else tuple(profile_inputs),
            mode,
            reason,
            dynamic_inputs,
        )
        return function

    return decorate


def _composed_placeholder(*_args: object, **_kwargs: object) -> None:
    """Лестница эту функцию не вызывает: формулу считает select_ratio → composed_ratio."""

    raise ImplementationContractError("composed считается маршрутом select_ratio, не вызовом реестра")


def composed(metric_id: str, formula_id: str, reason: str) -> None:
    """Формула без своей функции. Общий маршрут select_ratio → composed_ratio."""

    _require_mode(formula_id, "composed", reason)
    key = (metric_id, formula_id)
    current = REGISTRY.get(key)
    if current is not None and current.mode != "composed":
        raise DuplicateImplementation(f"реализация уже зарегистрирована: {metric_id} {formula_id}")
    REGISTRY[key] = Implementation(
        metric_id,
        formula_id,
        "",
        _composed_placeholder,
        (),
        (),
        None,
        "composed",
        reason,
    )


def _require_mode(formula_id: str, mode: str, reason: str) -> None:
    if mode not in _MODES:
        raise ImplementationContractError(f"{formula_id}: способ реализации registered, composed или dynamic")
    if mode != "registered" and not reason.strip():
        raise ImplementationContractError(f"{formula_id}: у {mode} нет причины")


# Нет своей функции: лестница считает формулу общим маршрутом select_ratio → composed_ratio.
composed("net_debt_ebitda", "net_debt_ebitda", "состав целиком из каталога")
composed("escrow_coverage", "escrow_coverage", "состав целиком из каталога")
composed("total_debt_ebitda", "total_debt_ebitda", "состав целиком из каталога")
composed(
    "debt_off_balance_ebitda",
    "debt_off_balance_ebitda",
    "состав из каталога, забаланс только снимает обязательность",
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


def _version_problem(formula_id: str, version: object) -> str | None:
    """implementation_version — formula_id@целое, отдельно от definition_version.

    В конверт анализа и в провенанс ячейки версия не пишется: это опубликованный
    формат ответа. composed своей реализации не имеет, поле остаётся пустым.
    """

    prefix = f"{formula_id}@"
    suffix = version[len(prefix) :] if isinstance(version, str) and version.startswith(prefix) else ""
    if suffix.isascii() and suffix.isdigit() and str(int(suffix)) == suffix:
        return None
    return f"{formula_id}: implementation_version — {formula_id}@<целое>"


def _check_formula(
    metric_id: str,
    variant: str | None,
    body: Mapping[str, object],
    problems: list[str],
) -> None:
    formula_id = formula_id_of(metric_id, variant, body)
    item = REGISTRY.get((metric_id, formula_id))
    if item is None:
        problems.append(f"{formula_id}: нет реализации в реестре")
        return
    if item.mode != "composed":
        problem = _version_problem(formula_id, item.implementation_version)
        if problem:
            problems.append(problem)
    if item.mode == "composed":
        return
    if item.mode == "dynamic":
        if item.inputs:
            problems.append(f"{formula_id}: у dynamic inputs пустые")
        names, missing = _dynamic_names(item, REGISTRY, set())
        for ref in missing:
            problems.append(f"{formula_id}: компонент {ref[1]} не зарегистрирован")
        if not names and not missing:
            problems.append(f"{formula_id}: у dynamic нет допустимого набора")
        extra = sorted(composition_concepts(body) - names)
        if extra:
            problems.append(f"{formula_id}: необъявленные входы: {', '.join(extra)}")
        return
    if not item.inputs:
        problems.append(f"{formula_id}: пустые inputs у registered")
        return
    declared = set(item.inputs) | set(item.optional_inputs)
    extra = sorted(composition_concepts(body) - declared)
    if extra:
        problems.append(f"{formula_id}: необъявленные входы: {', '.join(extra)}")


def _dynamic_names(
    item: Implementation,
    registry: Mapping[tuple[str, str], Implementation],
    seen: set[tuple[str, str]],
) -> tuple[set[str], list[tuple[str, str]]]:
    """Понятия dynamic: свои группы, ветки, аргументы и набор компонентов."""

    key = (item.metric_id, item.formula_id)
    if key in seen:
        return set(), []
    seen.add(key)
    names: set[str] = set(item.inputs) | set(item.optional_inputs)
    if item.profile_inputs:
        names.update(item.profile_inputs)
    missing: list[tuple[str, str]] = []
    spec = item.dynamic_inputs
    if spec is None:
        return names, missing
    for group in spec.groups:
        names.update(group.concepts)
    for dependency in spec.dependencies:
        names.update(dependency.concepts)
    names.update(spec.arguments)
    for ref in spec.components:
        other = registry.get(ref)
        if other is None:
            missing.append(ref)
            continue
        extra, nested = _dynamic_names(other, registry, seen)
        names.update(extra)
        missing.extend(nested)
    return names, missing


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
