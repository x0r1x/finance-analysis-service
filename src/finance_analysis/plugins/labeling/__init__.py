"""Labeling functions по графу и числам книги (§5.11.1). Голос «за», «против» или воздержание."""

from finance_analysis.plugins.labeling.functions import (
    LABELING_FUNCTIONS,
    identity,
    ratio_numerator,
    rollforward,
    run_all,
    sum_component,
    unit_sign,
)

__all__ = [
    "LABELING_FUNCTIONS",
    "identity",
    "ratio_numerator",
    "rollforward",
    "run_all",
    "sum_component",
    "unit_sign",
]
