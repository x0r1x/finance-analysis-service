"""Нормализация меток стадии 1 (§5.2, §5.5)."""

import json

import pytest

from finance_analysis.application.catalog import load_catalog, load_git_document
from finance_analysis.application.glossary_store import provenance_of
from finance_analysis.application.project import derive_rows
from finance_analysis.domain.glossary import (
    build_package,
    label_features,
    normalize_label,
    with_profile,
)
from finance_analysis.domain.mapping import label_id

_DICTS = {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}}


def _body() -> dict:
    return {"concepts": {"cfads": {"kind": "measure", "unit": "money"}}, "taxonomy": "core-1"}


def _glossary(**extra) -> dict:
    base = {"concept": "cfads", "pref": {"ru": "Денежный поток", "en": "Cash flow"}}
    base.update(extra)
    return {"cfads": base}


def test_trailing_paren_abbreviation_matches_phrase_and_the_abbreviation():
    package = load_catalog()
    raw = "Cash Flow Available for Debt Service (CFADS)"
    assert normalize_label(raw) == normalize_label("Cash flow available for debt service")
    assert package.resolve(raw).concept == "cfads"
    assert package.resolve("Whatever else (CFADS)").concept == "cfads"
    assert label_features(raw).unit is None
    assert label_features(raw).period is None


def test_trailing_paren_explanation_is_not_its_own_key():
    package = load_catalog()
    raw = "Операционная прибыль (убыток)"
    assert normalize_label(raw) == normalize_label("Операционная прибыль")
    assert package.resolve(raw).concept == "operating_profit"
    assert package.resolve("убыток") is None


def test_same_kind_labels_may_collapse_to_one_key():
    package = build_package(
        _body(),
        _glossary(alt={"ru": ["Поток (убыток)", "Поток"]}),
        _DICTS,
    )
    assert package.resolve("Поток").concept == "cfads"
    assert package.resolve("Поток (убыток)").concept == "cfads"


@pytest.mark.parametrize(
    ("raw", "body", "unit"),
    [
        ("Выручка, тыс. руб.", "выручка", "тыс. руб."),
        ("Выручка, млн руб.", "выручка", "млн руб."),
        ("Выручка, млрд руб.", "выручка", "млрд руб."),
        ("Выручка, руб.", "выручка", "руб."),
        ("Выручка (тыс. руб.)", "выручка", "тыс. руб."),
        ("EBIT, %", "ebit", "%"),
        ("Маржа (%)", "маржа", "%"),
        ("Revenue$000", "revenue", "$000"),
        ("Revenue $'000", "revenue", "$'000"),
        ("Revenue USD k", "revenue", "USD k"),
        ("Revenue EUR 000", "revenue", "EUR 000"),
        ("Interest (k£)", "interest", "k£"),
        ("Revenue £000", "revenue", "£000"),
    ],
)
def test_trailing_unit_is_stripped_and_kept(raw, body, unit):
    assert normalize_label(raw) == body
    features = label_features(raw)
    assert features.unit == unit
    assert features.period is None


@pytest.mark.parametrize(
    ("raw", "body", "period"),
    [
        ("Выручка за кв.", "выручка", "за кв."),
        ("Выручка за квартал", "выручка", "за квартал"),
        ("Выручка за год", "выручка", "за год"),
        ("Выручка за период", "выручка", "за период"),
        ("Revenue (last 12 months)", "revenue", "last 12 months"),
        ("Revenue LTM", "revenue", "LTM"),
        ("Revenue (LTM)", "revenue", "LTM"),
    ],
)
def test_trailing_period_is_stripped_and_kept(raw, body, period):
    assert normalize_label(raw) == body
    features = label_features(raw)
    assert features.period == period
    assert features.unit is None


def test_unit_and_period_both_survive_either_order():
    left = label_features("Выручка за год, тыс. руб.")
    right = label_features("Выручка, тыс. руб. за год")
    assert normalize_label("Выручка за год, тыс. руб.") == "выручка"
    assert normalize_label("Выручка, тыс. руб. за год") == "выручка"
    assert left.unit == right.unit == "тыс. руб."
    assert left.period == right.period == "за год"


def test_spaces_and_punctuation_collapse():
    assert normalize_label("Cash-Flow / available") == "cash flow available"
    assert normalize_label("Cash   flow") == "cash flow"
    assert normalize_label("дпод.") == normalize_label("ДПОД")


def test_simple_english_plural_does_not_eat_acronyms():
    package = load_catalog()
    assert normalize_label("Interests") == "interest"
    assert package.resolve("Interests").concept == "interest"
    assert normalize_label("CFADS") == "cfads"
    assert package.resolve("cfads").concept == "cfads"


def test_body_and_abbreviation_of_different_concepts_do_not_bind():
    assert load_catalog().resolve("EBIT (CFADS)") is None


def test_profile_overlay_uses_the_same_normalization():
    document = load_git_document()
    package = load_catalog()
    document["glossaries"]["interest"].setdefault("scoped", {})["bank"] = {"alt": {"en": ["Coupon, %"]}}
    assert package.resolve("Coupon, %") is None
    assert with_profile(package, document, "bank").resolve("Coupon, %").concept == "interest"


def test_profile_does_not_take_another_concepts_key():
    document = load_git_document()
    package = load_catalog()
    document["glossaries"]["interest"].setdefault("scoped", {})["bank"] = {"alt": {"en": ["Coupon (CFADS)"]}}
    scoped = with_profile(package, document, "bank")
    assert scoped.resolve("Coupon").concept == "interest"
    assert scoped.resolve("CFADS").concept == "cfads"
    assert package.resolve("CFADS").concept == "cfads"


@pytest.mark.parametrize(
    ("concept", "label"),
    [
        ("interest", "Проценты к уплате"),
        ("interest", "Финансовые расходы"),
        ("interest", "Процентные расходы"),
        ("interest", "Debt interest"),
        ("principal", "Погашение кредитов и займов"),
        ("principal", "Погашение обязательств по привлеченным кредитам"),
        ("principal", "Погашено займов и кредитов"),
        ("principal", "Debt principal"),
        ("debt_outstanding", "Финансовый долг"),
        ("debt_outstanding", "Долг всего"),
        ("debt_outstanding", "Остаток долга"),
        ("debt_outstanding", "Остаток кредитов на конец периода"),
        ("operating_profit", "Операционная прибыль"),
        ("operating_profit", "Операционная прибыль (убыток)"),
        ("ebit", "Earnings before interest and taxes"),
        ("ebit", "Earnings before interest and tax"),
        ("ebit", "Прибыль до вычета процентов и налогов"),
        ("ebit", "Прибыль до уплаты процентов и налогов"),
        ("ebit", "Прибыль до процентов и налогов"),
        ("capex", "Капитальные затраты"),
        ("capex", "Капитальные вложения"),
        ("capex", "Капитальные затраты без учета приобретений"),
        ("capex", "Капитальные затраты без учета приобретений с учетом НДС"),
        ("capex", "Капитальные затраты без учета приобретений с учетом НДС за кв."),
        ("debt_service", "Обслуживание долга"),
        ("debt_service", "Total debt service"),
        ("dscr", "Debt Service Coverage Ratio"),
    ],
)
def test_ras_ifrs_labels_resolve(concept, label):
    assert load_catalog().resolve(label).concept == concept


def test_interest_form_codes_bind_and_a_stray_number_does_not():
    package = load_catalog()
    assert package.resolve("070").concept == "interest"
    assert package.resolve("2330").concept == "interest"
    assert package.resolve("стр. 070").concept == "interest"
    hit, strength = package.resolve_match("(070)")
    assert hit.concept == "interest" and strength == "exact"
    hit, strength = package.resolve_match("Проценты к уплате (2330)")
    assert hit.concept == "interest" and strength == "exact"
    assert package.resolve("Выручка (1000)") is None or package.resolve("Выручка (1000)").concept != "interest"
    assert package.resolve("(1000)") is None


def test_instruction_and_parenthetical_tail_match_more_weakly():
    package = load_catalog()
    raw = "Финансовые расходы (процентные расходы), укажите с '+'"
    hit, strength = package.resolve_match(raw)
    assert hit.concept == "interest"
    assert strength == "exact"
    assert package.resolve_match("Финансовые расходы")[1] == "exact"
    assert package.resolve_match("Финансовые расходы, введите сумму")[1] == "exact"
    assert package.resolve_match("Операционная прибыль (убыток)")[1] == "exact"


def test_stripped_unit_and_period_land_in_row_evidence():
    row = {
        "model_id": "m",
        "build_key": "b",
        "row_key": "r",
        "binding_key": "r",
        "label": "Проценты к уплате, тыс. руб. за год",
        "label_path_text": "Проценты к уплате, тыс. руб. за год",
        "kind": "fact",
        "hidden": False,
        "check_row": False,
        "unit": "money",
        "unit_per": None,
        "currency": "RUB",
        "scale": "k",
    }
    derived = derive_rows(
        {"dim_row": [row], "dim_period": []},
        state_seq=0,
        derive="d",
        versions={"glossary": "none"},
        glossary=load_catalog(),
    )
    sem = derived["row_semantics"][0]
    evidence = json.loads(sem["evidence_json"])
    assert evidence["label_unit"] == "тыс. руб."
    assert evidence["label_period"] == "за год"
    assert sem["period_position"] is None
    assert row["unit"] == "money"
    assert row["scale"] == "k"
    assert row["currency"] == "RUB"


def test_collapsed_alts_keep_separate_provenance():
    short = "Операционная прибыль"
    longer = "Операционная прибыль (убыток)"
    assert label_id("operating_profit", "alt", short) != label_id("operating_profit", "alt", longer)
    added = provenance_of(
        [
            {"concept": "operating_profit", "kind": "alt", "text": short, "change": "add"},
            {"concept": "operating_profit", "kind": "alt", "text": longer, "change": "add"},
        ],
        {},
        origin="base_git",
        seq=1,
        version="g",
        proposals=None,
    )
    left = provenance_of(
        [{"concept": "operating_profit", "kind": "alt", "text": longer, "change": "remove"}],
        added,
        origin="review",
        seq=2,
        version="g2",
        proposals=None,
    )
    assert label_id("operating_profit", "alt", short) in left
    assert label_id("operating_profit", "alt", longer) not in left
