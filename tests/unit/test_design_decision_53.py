"""Сверка текста решения 53 с телом хеша плана. Фикстур книг нет."""

from pathlib import Path

_DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design-v0.23.md"

_SMV_AND_EVIDENCE = "`semantic_model_version` входит в тело `content_sha256` и в `evidence_id`"
_SMV_IN_BODY = "`semantic_model_version` входит в тело `content_sha256`"
_ORIGIN = (
    "`origin_view` при переданном плане читает семена из `plan.lineage` "
    "и `resolve_semantic_inputs` снова не вызывает. "
    "Без плана он берёт `resolve_semantic_inputs` как фасад старого вызова. "
    "Семена с `row_key` становятся `FormulaOrigin` и `FormulaChain` для отчёта."
)
_RELATIONS = (
    "Типы семантических связей `equivalent_to`, `supersedes` и `replaced_by` неактивны, "
    "и валидатор их отвергает. Поля решений пользователя остаются как есть."
)
_DEFINITION = (
    "`definition_hash` хеширует определение формулы и SMV не включает. "
    "Семантическая версия лежит отдельно в `semantic_model_version` и проверяется при исполнении. "
    "`execute_bound` сначала проверяет `definition_mismatch`, затем `semantic_mismatch`."
)
_ABSENT = (
    "SMV в хеш не входит",
    "в хеш и в идентичность плана не входит",
    "в идентичность плана не входит и не хешируется",
    "вне идентичности плана и не хешируется",
    "на плане есть и в хеш не входит",
    "и в хеш не входит",
    "Смена остального SMV хеш не двигает",
    "хеш плана не двигается",
    "не хешируем весь SMV",
    "`replaced_by` неактивен, как `equivalent_to` и `supersedes`",
    "для каждой метрики снова вызывает `resolve_semantic_inputs`",
)


def _fragments() -> tuple[str, str, str]:
    text = _DESIGN.read_text(encoding="utf-8")
    changelog_at = text.index("**Что изменилось 22.11 (решение 53):")
    changelog = text[changelog_at : text.index("Подробности — §5.14.", changelog_at)]
    section_at = text.index("### 5.14 План разрешения метрики")
    section = text[section_at : text.index("\n## 6. Аналитический слой", section_at)]
    journal_at = text.index("53. **План разрешения метрики")
    journal = text[journal_at : text.index("\n54. **След расчёта", journal_at)]
    return changelog, section, journal


def test_decision_53_records_smv_inside_the_plan_hash():
    """Каждый фрагмент решения 53 называет свою часть идентичности."""

    changelog, section, journal = _fragments()
    assert _SMV_AND_EVIDENCE in changelog
    assert _SMV_IN_BODY in section
    excluded = section.split("Не входят:", 1)[1].split(".", 1)[0]
    assert "semantic_model_version" not in excluded
    assert _SMV_AND_EVIDENCE in journal
    assert _ORIGIN in section
    assert _RELATIONS in changelog
    assert _RELATIONS in journal
    assert _DEFINITION in changelog
    assert _DEFINITION in section
    assert _DEFINITION in journal
    for fragment in (changelog, section, journal):
        for phrase in _ABSENT:
            assert phrase not in fragment
