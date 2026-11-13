"""Загрузка configs/model_types и формул метрик (§5.7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from finance_analysis.application.catalog import catalog_file
from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.ids import concept_id as check_concept_id
from finance_analysis.domain.model_type import (
    Composed,
    MetricExpression,
    MetricInputs,
    ModelTypeCatalog,
    RowFallback,
    Side,
    Signal,
    TypeSpec,
)
from finance_analysis.domain.validation.catalog_integrity import (
    CatalogIntegrityError,
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    build_applicability_matrix,
    validate_applicability_matrix,
)


def model_types_dir() -> Path:
    return catalog_file().parent.parent / "model_types"


def matrix_file(path: Path | None = None) -> Path:
    return (path or model_types_dir()) / "matrix.json"


def metrics_file() -> Path:
    return catalog_file().parent.parent / "metrics" / "coverage.yaml"


_BASE_EXCLUSIVE = frozenset({"numerator", "denominator", "rate"})


def _assert_base_standalone(body: dict, name: str) -> None:
    """base — полный режим наследования; numerator/denominator/rate рядом запрещены."""

    if "base" not in body:
        return
    clash = sorted(key for key in _BASE_EXCLUSIVE if key in body)
    if clash:
        raise ModelTypeInvalid(
            f"{name}: base — самостоятельное наследование, нельзя вместе с {', '.join(clash)}"
        )


def _inputs(body: dict, refs: dict[str, MetricInputs], name: str) -> MetricInputs:
    _assert_base_standalone(body, name)
    base = body.get("base")
    if "base" in body:
        if not isinstance(base, str) or not base:
            raise ModelTypeInvalid(f"{name}: base — непустая строка")
        if base not in refs:
            raise ModelTypeInvalid(f"{name}: base {base} не объявлен раньше")
        return refs[base]
    all_of: set[str] = set()
    one_of: set[str] = set()
    if "numerator" in body:
        num_all, num_one = _term_names(body.get("numerator"), name, "numerator")
        all_of.update(num_all)
        one_of.update(num_one)
    if "denominator" in body:
        den_all, den_one = _term_names(body.get("denominator"), name, "denominator")
        all_of.update(den_all)
        all_of.update(den_one)
    if "rate" in body:
        rate = body.get("rate")
        if not isinstance(rate, str) or not rate:
            raise ModelTypeInvalid(f"{name}: rate — непустая строка")
        all_of.add(rate)
    return MetricInputs(frozenset(all_of), frozenset(one_of))


def _term_names(value: object, owner: str, field: str) -> tuple[set[str], set[str]]:
    """Разбор numerator/denominator → (all_of, one_of)."""

    if isinstance(value, dict):
        names = _names(value, f"{owner}.{field}")
        if not names:
            raise ModelTypeInvalid(f"{owner}: {field} пустой (нужен хотя бы один plus/minus)")
        return names, set()
    if isinstance(value, str):
        if not value:
            raise ModelTypeInvalid(f"{owner}: {field} пустая строка")
        return {value}, set()
    if isinstance(value, list):
        if not value or any(not isinstance(item, str) or not item for item in value):
            raise ModelTypeInvalid(f"{owner}: {field} — непустой список строк")
        names = [str(item) for item in value]
        if len(names) > 1 and field == "numerator":
            return set(), set(names)
        return set(names), set()
    raise ModelTypeInvalid(f"{owner}: {field} — строка, список строк или объект plus/minus")


def _names(side: dict, name: str) -> set[str]:
    if set(side) - {"plus", "minus"}:
        raise ModelTypeInvalid(f"{name}: у слагаемых только plus и minus")
    plus = side.get("plus") if "plus" in side else []
    minus = side.get("minus") if "minus" in side else []
    if "plus" in side and (not isinstance(plus, list) or any(not isinstance(item, str) or not item for item in plus)):
        raise ModelTypeInvalid(f"{name}.plus: список строк")
    if "minus" in side and (
        not isinstance(minus, list) or any(not isinstance(item, str) or not item for item in minus)
    ):
        raise ModelTypeInvalid(f"{name}.minus: список строк")
    if not isinstance(plus, list):
        plus = []
    if not isinstance(minus, list):
        minus = []
    return {str(item) for item in plus} | {str(item) for item in minus}


def _side(raw: dict) -> Side:
    return Side(tuple(str(item) for item in raw.get("plus") or []), tuple(str(item) for item in raw.get("minus") or []))


def _composed(body: dict, name: str) -> Composed | None:
    if body.get("aggregation") == "stock":
        numerator = body.get("numerator")
        if not isinstance(numerator, dict) or body.get("window") != "period" or "denominator" in body:
            raise ModelTypeInvalid(f"{name}: сумма запаса — числитель, окно period, без знаменателя")
        side = _side(numerator)
        if not side.plus and not side.minus:
            raise ModelTypeInvalid(f"{name}: сумма пуста")
        return Composed(side, Side((), ()), "period")
    numerator = body.get("numerator")
    if not isinstance(numerator, dict):
        return None
    # FCFF объявляет plus/minus без окна и знаменателя: это не частное.
    if "window" not in body and "denominator" not in body:
        return None
    window = body.get("window")
    denominator = body.get("denominator")
    if window not in {"LTM", "period"}:
        raise ModelTypeInvalid(f"{name}: окно LTM или period")
    if not isinstance(denominator, dict):
        raise ModelTypeInvalid(f"{name}: знаменатель — plus и minus")
    den = _side(denominator)
    if not den.plus and not den.minus:
        raise ModelTypeInvalid(f"{name}: знаменатель пуст")
    return Composed(_side(numerator), den, str(window))


def _expression(body: dict, name: str) -> MetricExpression:
    _assert_base_standalone(body, name)
    if "base" in body:
        base = body.get("base")
        if not isinstance(base, str) or not base:
            raise ModelTypeInvalid(f"{name}: base — непустая строка")
        return MetricExpression(base=base)
    rate = None
    if "rate" in body:
        raw_rate = body.get("rate")
        if not isinstance(raw_rate, str) or not raw_rate:
            raise ModelTypeInvalid(f"{name}: rate — непустая строка")
        rate = raw_rate
    one_of: set[str] = set()
    num_plus: tuple[str, ...] = ()
    num_minus: tuple[str, ...] = ()
    den_plus: tuple[str, ...] = ()
    den_minus: tuple[str, ...] = ()
    if "numerator" in body:
        num_plus, num_minus, one_of = _expression_side(body.get("numerator"), name, "numerator")
    if "denominator" in body:
        den_plus, den_minus, den_one = _expression_side(body.get("denominator"), name, "denominator")
        if den_one:
            # Альтернативы допустимы только у числителя (ICR); знаменатель — all_of.
            den_plus = tuple(sorted(den_one))
    return MetricExpression(
        numerator_plus=num_plus,
        numerator_minus=num_minus,
        denominator_plus=den_plus,
        denominator_minus=den_minus,
        one_of=frozenset(one_of),
        rate=rate,
        base=None,
    )


def _expression_side(
    value: object, owner: str, field: str
) -> tuple[tuple[str, ...], tuple[str, ...], set[str]]:
    if isinstance(value, dict):
        names = _names(value, f"{owner}.{field}")
        if not names:
            raise ModelTypeInvalid(f"{owner}: {field} пустой (нужен хотя бы один plus/minus)")
        plus = tuple(str(item) for item in (value.get("plus") or []))
        minus = tuple(str(item) for item in (value.get("minus") or []))
        return plus, minus, set()
    if isinstance(value, str):
        if not value:
            raise ModelTypeInvalid(f"{owner}: {field} пустая строка")
        return (value,), (), set()
    if isinstance(value, list):
        if not value or any(not isinstance(item, str) or not item for item in value):
            raise ModelTypeInvalid(f"{owner}: {field} — непустой список строк")
        names = [str(item) for item in value]
        if len(names) > 1 and field == "numerator":
            return (), (), set(names)
        return tuple(names), (), set()
    raise ModelTypeInvalid(f"{owner}: {field} — строка, список строк или объект plus/minus")


def load_metric_inputs(path: Path | None = None) -> dict[str, MetricInputs]:
    inputs, _variants, _composed_formulas, _bases, _rates, _expressions = load_metric_catalog(path)
    return inputs


def load_metric_catalog(
    path: Path | None = None,
) -> tuple[
    dict[str, MetricInputs],
    dict[str, dict[str, MetricInputs]],
    dict[str, Composed],
    dict[str, str],
    dict[str, str],
    dict[str, MetricExpression],
]:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    raw = document.get("metrics") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет metrics")
    inputs: dict[str, MetricInputs] = {}
    variants: dict[str, dict[str, MetricInputs]] = {}
    composed: dict[str, Composed] = {}
    bases: dict[str, str] = {}
    rates: dict[str, str] = {}
    expressions: dict[str, MetricExpression] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{name}: формула метрики не объект")
        metric = str(name)
        if "base" in body:
            base = body.get("base")
            if not isinstance(base, str) or not base:
                raise ModelTypeInvalid(f"{metric}: base — непустая строка")
            bases[metric] = base
        if "rate" in body:
            rate = body.get("rate")
            if not isinstance(rate, str) or not rate:
                raise ModelTypeInvalid(f"{metric}: rate — непустая строка")
            rates[metric] = rate
        inputs[metric] = _inputs(body, inputs, metric)
        expressions[metric] = _expression(body, metric)
        own = _composed(body, metric)
        if own is not None:
            composed[metric] = own
        if "variants" in body and not isinstance(body.get("variants"), dict):
            raise ModelTypeInvalid(f"{metric}: variants должен быть объектом")
        raw_variants = body.get("variants") or {}
        if not isinstance(raw_variants, dict):
            raise ModelTypeInvalid(f"{metric}: variants должен быть объектом")
        found: dict[str, MetricInputs] = {}
        for variant, spec in raw_variants.items():
            if not isinstance(spec, dict):
                raise ModelTypeInvalid(f"{metric}.{variant}: вариант не объект")
            if "variants" in spec:
                raise ModelTypeInvalid(f"{metric}.{variant}: вложенные variants не поддерживаются")
            key = f"{metric}.{variant}"
            found[str(variant)] = _inputs(spec, inputs, key)
            expressions[key] = _expression(spec, key)
            if "base" in spec:
                base = spec.get("base")
                if not isinstance(base, str) or not base:
                    raise ModelTypeInvalid(f"{key}: base — непустая строка")
                bases[key] = base
            item = _composed(spec, key)
            if item is not None:
                composed[key] = item
            if "rate" in spec:
                rate = spec.get("rate")
                if not isinstance(rate, str) or not rate:
                    raise ModelTypeInvalid(f"{key}: rate — непустая строка")
                rates[key] = rate
        if found:
            variants[metric] = found
    return inputs, variants, composed, bases, rates, expressions


def _signal(type_id: str, raw: dict) -> Signal:
    concepts = tuple(str(item) for item in raw.get("concepts") or [])
    groups = tuple(tuple(str(name) for name in group) for group in raw.get("groups") or [])
    absent = tuple(str(item) for item in raw.get("absent") or [])
    return Signal(str(raw["kind"]), float(raw["weight"]), concepts, groups, absent)


def _use(body) -> str:
    if isinstance(body, str):
        return body
    return str(body["use"])


def load_coverage_document(path: Path | None = None) -> dict:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ModelTypeInvalid("configs/metrics: документ должен быть объектом")
    return document


def load_row_fallbacks(path: Path | None = None) -> dict[str, RowFallback]:
    """Альтернативные идентификаторы строк. Не входят в таксономию понятий.

    `binding_key` и `matching.rule` хранятся как декларативные метаданные.
    Lookup — по id fallback в `interest_order` среди primaries.
    """

    document = load_coverage_document(path)
    raw = document.get("row_fallbacks") or {}
    if not isinstance(raw, dict):
        raise ModelTypeInvalid("configs/metrics: row_fallbacks должен быть объектом")
    found: dict[str, RowFallback] = {}
    for key, body in raw.items():
        name = check_concept_id(str(key))
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"row_fallbacks.{name}: объект")
        matching = body.get("matching") or {}
        if not isinstance(matching, dict):
            raise ModelTypeInvalid(f"row_fallbacks.{name}: matching должен быть объектом")
        canonical = body.get("canonical")
        binding_key = body.get("binding_key")
        rule = matching.get("rule")
        if not isinstance(canonical, str) or not canonical:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен canonical")
        if not isinstance(binding_key, str) or not binding_key:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен binding_key")
        if not isinstance(rule, str) or not rule:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен matching.rule")
        found[name] = RowFallback(
            id=name,
            canonical=check_concept_id(canonical),
            binding_key=check_concept_id(binding_key),
            matching_rule=str(rule),
        )
    return found


def load_interest_order(
    path: Path | None = None,
    *,
    concepts: frozenset[str] | None = None,
    fallbacks: dict[str, RowFallback] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Порядок процентов из coverage.yaml. Имена — concept_id или row_fallback."""

    document = load_coverage_document(path)
    raw = document.get("interest_order") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет interest_order")
    allowed = None
    if concepts is not None:
        names = set(concepts) | set(fallbacks or ())
        allowed = names
    order: dict[str, tuple[str, ...]] = {}
    for key, names_raw in raw.items():
        if not isinstance(names_raw, list) or not names_raw or any(not isinstance(item, str) for item in names_raw):
            raise ModelTypeInvalid(f"interest_order.{key}: список имён")
        cleaned = tuple(str(item) for item in names_raw)
        if allowed is not None:
            unknown = [item for item in cleaned if item not in allowed]
            if unknown:
                raise ModelTypeInvalid(
                    f"interest_order.{key}: неизвестные id: {', '.join(unknown)}"
                )
        order[str(key)] = cleaned
    return order


def load_matrix_snapshot(folder: Path | None = None) -> dict:
    """Читает checked-in снимок configs/model_types/matrix.json."""

    file = matrix_file(folder)
    if not file.is_file():
        raise ModelTypeInvalid("нет configs/model_types/matrix.json")
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ModelTypeInvalid("matrix.json: корень должен быть объектом")
    return raw


def _load_model_type_documents(folder: Path) -> tuple[dict, dict[str, dict]]:
    """Читает _common.yaml и документы типов без сверки matrix.json."""

    common_path = folder / "_common.yaml"
    if not common_path.is_file():
        raise ModelTypeInvalid("нет configs/model_types/_common.yaml")
    common = yaml.safe_load(common_path.read_text(encoding="utf-8")) or {}
    if not isinstance(common, dict):
        raise ModelTypeInvalid("_common.yaml должен быть объектом")
    documents: dict[str, dict] = {}
    for file in sorted(folder.glob("*.yaml")):
        if file.name.startswith("_"):
            continue
        body = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if not isinstance(body, dict) or body.get("id") != file.stem:
            raise ModelTypeInvalid(f"{file.name}: id должен совпадать с именем файла")
        documents[file.stem] = body
    return common, documents


def dump_applicability_matrix(folder: Path | None = None) -> dict[str, dict[str, dict[str, str]]]:
    """Снимок тип×метрика из YAML в форме validate_applicability_matrix (без сверки matrix.json)."""

    root = folder or model_types_dir()
    common, documents = _load_model_type_documents(root)
    default = common.get("default_use")
    if default not in {"required", "optional", "not_applicable"}:
        raise ModelTypeInvalid("default_use: required, optional или not_applicable")
    metric_inputs, *_rest = load_metric_catalog()
    return build_applicability_matrix(documents, metric_inputs, default_use=str(default))


def write_applicability_matrix(
    folder: Path | None = None,
    *,
    path: Path | None = None,
) -> Path:
    """Пишет configs/model_types/matrix.json (или path) из dump_applicability_matrix."""

    root = folder or model_types_dir()
    target = path or matrix_file(root)
    payload = dump_applicability_matrix(root)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_model_types(path: Path | None = None, *, concepts: frozenset[str] | None = None) -> ModelTypeCatalog:
    folder = path or model_types_dir()
    common, documents = _load_model_type_documents(folder)
    package = None
    if concepts is None:
        from finance_analysis.application.catalog import load_catalog

        package = load_catalog()
        concepts = package.ids
    metric_inputs, variant_inputs, composed, metric_bases, metric_rates, expressions = load_metric_catalog()
    row_fallbacks = load_row_fallbacks()
    interest_order = load_interest_order(concepts=concepts, fallbacks=row_fallbacks)
    _check_signal_concepts(documents, concepts)
    if package is None:
        from finance_analysis.application.catalog import load_catalog

        package = load_catalog()
    from finance_analysis.application.catalog import load_dimensions

    coverage = load_coverage_document()
    default = common.get("default_use")
    if default not in {"required", "optional", "not_applicable"}:
        raise ModelTypeInvalid("default_use: required, optional или not_applicable")
    try:
        validate_catalog_integrity(
            concepts=concepts,
            concept_dimensions={name: item.dimension for name, item in package.concepts.items()},
            dimensions=load_dimensions(),
            model_documents=documents,
            metric_inputs=metric_inputs,
            variant_inputs=variant_inputs,
            metric_expressions=expressions,
            metric_bases=metric_bases,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            coverage_document=coverage,
        )
    except CatalogIntegrityError as exc:
        raise ModelTypeInvalid(str(exc)) from exc
    snapshot = load_matrix_snapshot(folder)
    validate_applicability_matrix(
        documents,
        metric_inputs,
        default_use=str(default),
        snapshot=snapshot,
    )
    compatible = _compatible(common.get("compatible"), documents)
    types = {type_id: _spec(type_id, body) for type_id, body in documents.items()}
    version = hashlib.sha256(
        canonical_json({"common": common, "types": documents}).encode("utf-8")
    ).hexdigest()[:16]
    return ModelTypeCatalog(
        types,
        str(default),
        version,
        concepts,
        metric_inputs,
        documents,
        compatible,
        composed,
        variant_inputs,
        interest_order,
        row_fallbacks,
        metric_bases,
        metric_rates,
        expressions,
    )


def _check_signal_concepts(documents: dict[str, dict], concepts: frozenset[str]) -> None:
    for type_id, body in documents.items():
        for signal in body.get("signals") or []:
            named = [*(signal.get("concepts") or []), *(signal.get("absent") or [])]
            unknown = [check_concept_id(str(name)) for name in named if str(name) not in concepts]
            if unknown:
                raise ModelTypeInvalid(f"{type_id}: понятие признака вне каталога: {', '.join(unknown)}")


def _compatible(raw, documents: dict[str, dict]) -> frozenset[frozenset[str]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ModelTypeInvalid("compatible должен быть списком пар")
    found: set[frozenset[str]] = set()
    for pair in raw:
        if not isinstance(pair, list) or len(pair) != 2 or any(item not in documents for item in pair):
            raise ModelTypeInvalid("compatible: обе стороны пары должны быть типами")
        found.add(frozenset(str(item) for item in pair))
    return frozenset(found)


def _spec(type_id: str, body: dict) -> TypeSpec:
    metrics: dict[str, str] = {}
    variants: dict[str, str] = {}
    for name, value in (body.get("metrics") or {}).items():
        metrics[str(name)] = _use(value)
        if isinstance(value, dict) and isinstance(value.get("variant"), str):
            variants[str(name)] = value["variant"]
    return TypeSpec(
        type_id,
        tuple(_signal(type_id, item) for item in body.get("signals") or []),
        frozenset(str(name) for name in body.get("required_concepts") or []),
        metrics,
        variants,
    )
