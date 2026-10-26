"""Правила аудита фазы 1 (§6.1): формулы, ссылки, циклы, проверки."""

from finance_analysis.plugins.rules.checks import CHECK_FAILURE, NO_MASTER_CHECK
from finance_analysis.plugins.rules.cycles import (
    ITERATIVE_CALC_ENABLED,
    ITERATIVE_CYCLE_WITHOUT_ITERATE,
    UNEXPECTED_CYCLE,
)
from finance_analysis.plugins.rules.formulas import (
    EXCEL_NPV_USED,
    FORMULA_INCONSISTENT_IN_ROW,
    HARDCODED_FORMULA,
    LITERAL_IN_FORMULA,
    LONG_FORMULA,
    MISSING_CACHED_VALUE,
    NESTED_IF,
    OFFSET_INDIRECT_USED,
)
from finance_analysis.plugins.rules.ratios import (
    MARKER_MIX,
    RATIO_MISMATCH,
    UNMAPPED_IN_METRIC_CHAIN,
)
from finance_analysis.plugins.rules.refs import (
    DANGLING_REF,
    EXTERNAL_REF,
    UNRESOLVED_REF,
)

# Порядок — как в таблице §6.1.
RULES = (
    HARDCODED_FORMULA,
    LITERAL_IN_FORMULA,
    FORMULA_INCONSISTENT_IN_ROW,
    DANGLING_REF,
    UNRESOLVED_REF,
    EXTERNAL_REF,
    UNEXPECTED_CYCLE,
    ITERATIVE_CALC_ENABLED,
    ITERATIVE_CYCLE_WITHOUT_ITERATE,
    CHECK_FAILURE,
    NO_MASTER_CHECK,
    MISSING_CACHED_VALUE,
    OFFSET_INDIRECT_USED,
    EXCEL_NPV_USED,
    NESTED_IF,
    LONG_FORMULA,
    RATIO_MISMATCH,
    MARKER_MIX,
    UNMAPPED_IN_METRIC_CHAIN,
)

__all__ = ["RULES"]
