"""Сверка текста решения 53 с телом хеша плана. Фикстур книг нет."""

from pathlib import Path

_DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design-v0.23.md"

_REQUIRED = "`semantic_model_version` входит в тело `content_sha256`"

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
)


def _decision_53_paragraphs() -> str:
    text = _DESIGN.read_text(encoding="utf-8")
    changelog_at = text.index("**Что изменилось 22.11 (решение 53):")
    changelog = text[changelog_at : text.index("Подробности — §5.14.", changelog_at)]
    section_at = text.index("### 5.14 План разрешения метрики")
    section = text[section_at : text.index("\n## 6. Аналитический слой", section_at)]
    journal_at = text.index("53. **План разрешения метрики")
    journal = text[journal_at : text.index("\n54. **След расчёта", journal_at)]
    return f"{changelog}\n{section}\n{journal}"


def test_decision_53_records_smv_inside_the_plan_hash():
    """Абзацы решения 53 говорят, что SMV входит в тело content_sha256."""

    paragraphs = _decision_53_paragraphs()
    assert _REQUIRED in paragraphs
    excluded = paragraphs.split("Не входят:", 1)[1].split(".", 1)[0]
    assert "semantic_model_version" not in excluded
    for phrase in _ABSENT:
        assert phrase not in paragraphs
