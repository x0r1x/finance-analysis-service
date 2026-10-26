"""Разбор текста формулы (`domain/formulas.py`)."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.formulas import analyze


def test_formula_facts():
    facts = analyze("=IF(A1>0,IF(B$2<5%,0.07*'Year 2024'!C3,SUM(D1:D9)),\"x 99\")*12")
    assert facts.if_depth == 2
    assert facts.functions == {"IF", "SUM"}
    # 12 и 0 универсальны, 99 в строке и 2024 в имени листа — не литералы.
    assert sorted(facts.literals, key=Decimal) == ["0.05", "0.07"]
    assert analyze("=Z172*(1+AA165)").literals == ()
    assert analyze("=NPV(Rate,B1:B9)").functions == {"NPV"}
    assert analyze("=XNPV(Rate,B1:B9,C1:C9)").functions == {"XNPV"}
    assert analyze("=A:A+3:3").operands == 2
