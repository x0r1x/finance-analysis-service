"""Ссылочная целостность configs/model_types (§5.7). Без ввода-вывода."""

from __future__ import annotations

from finance_analysis.domain.model_type import MetricInputs

_USES = frozenset({"required", "optional", "not_applicable"})
_KINDS = frozenset({"concepts_bound_all", "sheets_any"})


class ModelTypeInvalid(ValueError):
    """Каталог типов не сходится со ссылками. Сервис с таким каталогом не стартует."""


def _use(body) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, dict) and isinstance(body.get("use"), str):
        return body["use"]
    raise ModelTypeInvalid("use метрики: required, optional или not_applicable")


def validate_model_types(
    types: dict[str, dict],
    *,
    concepts: frozenset[str],
    metric_inputs: dict[str, MetricInputs],
    variant_inputs: dict[str, dict[str, MetricInputs]] | None = None,
) -> None:
    if "other" not in types:
        raise ModelTypeInvalid("нет типа other")
    seen: set[str] = set()
    for type_id, body in types.items():
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{type_id}: файл типа не объект")
        declared = body.get("id")
        if declared != type_id or type_id in seen:
            raise ModelTypeInvalid(f"{type_id}: id не совпадает с именем или повторяется")
        seen.add(type_id)
        _signals(type_id, body.get("signals"))
        required = _concepts(type_id, body.get("required_concepts"), concepts)
        _metrics(type_id, body.get("metrics"), required, metric_inputs, variant_inputs or {})
        parent = body.get("inherits")
        if parent is not None and parent not in types:
            raise ModelTypeInvalid(f"{type_id}: inherits {parent} не найден")
    _cycles(types)


def _signals(type_id: str, raw) -> None:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ModelTypeInvalid(f"{type_id}: signals должен быть списком")
    total = 0.0
    for item in raw:
        if not isinstance(item, dict) or item.get("kind") not in _KINDS:
            raise ModelTypeInvalid(f"{type_id}: неизвестный признак")
        weight = item.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise ModelTypeInvalid(f"{type_id}: вес признака должен быть больше нуля")
        total += float(weight)
        if item["kind"] == "concepts_bound_all" and not item.get("concepts"):
            raise ModelTypeInvalid(f"{type_id}: concepts_bound_all без понятий")
        if item["kind"] == "sheets_any":
            _sheet_groups(type_id, item.get("groups"))
    if type_id != "other" and total <= 0:
        raise ModelTypeInvalid(f"{type_id}: сумма весов signals должна быть больше нуля")


def _sheet_groups(type_id: str, groups) -> None:
    """Группа — список непустых строк. Плоский список имён лоадер читает посимвольно."""

    if not isinstance(groups, list) or not groups:
        raise ModelTypeInvalid(f"{type_id}: sheets_any без групп листов")
    for group in groups:
        if (
            not isinstance(group, list)
            or not group
            or any(not isinstance(name, str) or not name for name in group)
        ):
            raise ModelTypeInvalid(f"{type_id}: группа листов — список непустых строк")


def _concepts(type_id: str, raw, concepts: frozenset[str]) -> frozenset[str]:
    if raw is None:
        raw = []
    if not isinstance(raw, list) or any(not isinstance(name, str) for name in raw):
        raise ModelTypeInvalid(f"{type_id}: required_concepts должен быть списком id")
    unknown = [name for name in raw if name not in concepts]
    if unknown:
        raise ModelTypeInvalid(f"{type_id}: понятие вне каталога: {', '.join(unknown)}")
    return frozenset(raw)


def _metrics(
    type_id: str,
    raw,
    required: frozenset[str],
    metric_inputs: dict[str, MetricInputs],
    variant_inputs: dict[str, dict[str, MetricInputs]],
) -> None:
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid(f"{type_id}: metrics пуст")
    for name, body in raw.items():
        if name != "*" and name not in metric_inputs:
            raise ModelTypeInvalid(f"{type_id}: метрика {name} нет в configs/metrics")
        use = _use(body)
        if use not in _USES:
            raise ModelTypeInvalid(f"{type_id}: use {name} вне списка")
        variant = body.get("variant") if isinstance(body, dict) else None
        if variant is not None and variant not in variant_inputs.get(name, {}):
            raise ModelTypeInvalid(f"{type_id}: вариант {name}.{variant} не объявлен")
        if use != "required" or name == "*":
            continue
        spec = variant_inputs.get(name, {}).get(variant, metric_inputs[name]) if variant else metric_inputs[name]
        missing = sorted(concept for concept in spec.all_of if concept not in required)
        if spec.one_of and not (spec.one_of & required):
            missing.append("one_of:" + "|".join(sorted(spec.one_of)))
        if missing:
            raise ModelTypeInvalid(f"{type_id}: входы {name} недостижимы: {', '.join(missing)}")


def _cycles(types: dict[str, dict]) -> None:
    for type_id in types:
        seen: set[str] = set()
        current = type_id
        while True:
            parent = types[current].get("inherits")
            if not parent:
                break
            if parent in seen or parent == type_id:
                raise ModelTypeInvalid(f"{type_id}: цикл inherits")
            seen.add(current)
            current = parent
