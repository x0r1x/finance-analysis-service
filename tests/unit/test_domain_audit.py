"""Отпечаток находки и номер оси (`domain/audit.py`, §6.1)."""

from __future__ import annotations

from finance_analysis.domain.audit import axis_ordinals, fingerprint


def test_fingerprint_and_axis_ordinal():
    left = fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left == fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left != fingerprint("hardcoded_formula", "bk", "2024", "план", "0")
    assert len(left) == 40
    # Вставка строки сдвигает номер шапки, но не порядок осей листа.
    before = axis_ordinals(["PF!r7", "PF!r185", "PF!r11", "TBA!r2"])
    after = axis_ordinals(["PF!r8", "PF!r186", "PF!r12", "TBA!r3"])
    assert before == {"PF!r7": 0, "PF!r11": 1, "PF!r185": 2, "TBA!r2": 0}
    assert [after[key] for key in ("PF!r8", "PF!r12", "PF!r186", "TBA!r3")] == [0, 1, 2, 0]
