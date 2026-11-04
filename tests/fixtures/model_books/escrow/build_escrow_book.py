"""Синтетическая книга девелопмента по 214-ФЗ. Формулы считает LibreOffice, не этот скрипт.

Запуск из корня репозитория:

    python tests/fixtures/model_books/escrow/build_escrow_book.py
    soffice --headless --norestore --nolockcheck \\
        -env:UserInstallation=file:///tmp/lo-profile-escrow \\
        --convert-to xlsx --outdir /tmp/lo-escrow-out \\
        tests/fixtures/model_books/escrow/development_escrow_214.xlsx

В репозиторий кладётся только файл с кэшем: development_escrow_214.recalc_libreoffice.xlsx.
"""

from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).with_name("development_escrow_214.xlsx")
MONTHS = 36

# Уровни ставки, порог покрытия и доля года — ячейки листа «Вводы», не литералы формул.
_BASE = "$B$11"
_SPECIAL = "$B$12"
_FULL = "$B$17"
_PER_YEAR = "$B$18"
_RVE = "$B$14"
_LAG = "$B$15"


def _prev(column: str, row: int) -> str:
    return "0" if row == 2 else f"{column}{row - 1}"


def _model_row(row: int) -> list:
    month = row - 1
    prev_loan = _prev("Q", row)
    prev_escrow = _prev("I", row)
    drawn = "0" if row == 2 else f"SUM($L$2:L{row - 1})"
    equity_cum = "0" if row == 2 else f"SUM($K$2:K{row - 1})"
    release_month = f"'Вводы'!{_RVE}+'Вводы'!{_LAG}"
    cap_interest = f"IF(A{row}<='Вводы'!{_RVE},O{row},0)"
    return [
        month,
        f"=IF(A{row}='Вводы'!{_RVE},1,0)",
        f"=IF(A{row}={release_month},1,0)",
        f"=IF(A{row}<='Вводы'!$B$5,'Вводы'!$B$4,0)",
        f"='Вводы'!$B$3*(1+'Вводы'!$B$6)^(A{row}-1)",
        f"=D{row}*E{row}",
        f"=IF(A{row}>{release_month},0,F{row}*'Вводы'!$B$13)",
        f"=C{row}*({prev_escrow}+G{row})",
        f"={prev_escrow}+G{row}-H{row}",
        f"=IF(A{row}<='Вводы'!$B$8,'Вводы'!$B$7,0)",
        f"=MIN(J{row},MAX(0,'Вводы'!$B$9*'Вводы'!$B$7*'Вводы'!$B$8-{equity_cum}))",
        f"=MIN(MAX(0,J{row}-K{row}),MAX(0,'Вводы'!$B$10-{drawn}))",
        f'=IF({prev_loan}<=0,"",{prev_escrow}/{prev_loan})',
        (
            f"=IF({prev_loan}<=0,'Вводы'!{_BASE},"
            f"MIN(M{row},'Вводы'!{_FULL})*'Вводы'!{_SPECIAL}"
            f"+(1-MIN(M{row},'Вводы'!{_FULL}))*'Вводы'!{_BASE})"
        ),
        f"={prev_loan}*N{row}/'Вводы'!{_PER_YEAR}",
        f"=MIN({prev_loan}+L{row}+{cap_interest},H{row}*'Вводы'!$B$16)",
        f"={prev_loan}+L{row}+{cap_interest}-P{row}",
        f"=(F{row}-G{row})+(H{row}-P{row})-IF(A{row}<='Вводы'!{_RVE},0,O{row})",
    ]


def main() -> None:
    book = Workbook()
    inputs = book.active
    inputs.title = "Вводы"
    inputs["A1"] = "Параметры книги 214-ФЗ"
    parameters = [
        ("Месяцев", MONTHS),
        ("Цена за м2", 100),
        ("Площадь в месяц, м2", 20),
        ("Продажи до месяца включительно", 30),
        ("Индексация цены", 0),
        ("Бюджет стройки в месяц", 1000),
        ("Стройка до месяца включительно", 24),
        ("Доля собственных средств", 0),
        ("Лимит кредита", 100000),
        ("Базовая ставка", 0.12),
        ("Специальная ставка", 0.06),
        ("Доля оплаты на эскроу", 1),
        ("Месяц РВЭ", 24),
        ("Лаг раскрытия, мес", 0),
        ("Доля раскрытия в погашение", 1),
        ("Порог полного покрытия", 1),
        ("Периодов в году", 12),
        ("Запас срока депонирования, мес", 6),
    ]
    for offset, (label, value) in enumerate(parameters, start=2):
        inputs.cell(offset, 1, label)
        inputs.cell(offset, 2, value)

    model = book.create_sheet("Модель")
    model.append(
        [
            "Месяц",
            "Флаг РВЭ",
            "Флаг раскрытия",
            "Продано, м2",
            "Цена за м2",
            "Выручка ДДУ",
            "Поступления на эскроу",
            "Раскрытие эскроу",
            "Остаток на счетах эскроу",
            "Капитальные затраты",
            "Взнос собственных средств",
            "Выборка кредита",
            "Покрытие эскроу",
            "Эффективная ставка",
            "Проценты",
            "Погашение кредита",
            "Остаток долга",
            "Деньги застройщику",
        ]
    )
    last = 1 + MONTHS
    for row in range(2, last + 1):
        for column, value in enumerate(_model_row(row), start=1):
            model.cell(row, column, value)

    checks = book.create_sheet("Проверки")
    span = f"$A$2:$A${last}"
    cash = (
        f"SUMPRODUCT(ABS('Модель'!R2:R{last}"
        f"+('Модель'!G2:G{last}-'Модель'!H2:H{last})"
        f"+'Модель'!P2:P{last}"
        f"+('Модель'!{span}>'Вводы'!{_RVE})*('Модель'!O2:O{last})"
        f"-'Модель'!F2:F{last}))"
    )
    roll = (
        f"SUMPRODUCT(ABS('Модель'!I3:I{last}"
        f"-('Модель'!I2:I{last - 1}+'Модель'!G3:G{last}-'Модель'!H3:H{last})))"
    )
    rows = [
        ("Эскроу не ниже нуля", f"=MIN('Модель'!I2:I{last})>=0"),
        (
            "После раскрытия остаток нулевой",
            f"=SUMPRODUCT(('Модель'!{span}>='Вводы'!{_RVE}+'Вводы'!{_LAG})*('Модель'!I2:I{last}<>0))=0",
        ),
        ("Кредит погашен к концу", f"=ABS(INDEX('Модель'!Q2:Q{last},'Вводы'!$B$2))<0.000001"),
        (
            "Свои средства не ниже доли бюджета",
            f"=SUM('Модель'!K2:K{last})>='Вводы'!$B$9*'Вводы'!$B$7*'Вводы'!$B$8",
        ),
        ("Поступления равны раскрытию", f"=ABS(SUM('Модель'!G2:G{last})-SUM('Модель'!H2:H{last}))<0.000001"),
        (
            "Продажи после раскрытия мимо эскроу",
            f"=SUMPRODUCT(('Модель'!{span}>'Вводы'!{_RVE}+'Вводы'!{_LAG})*('Модель'!G2:G{last}<>0))=0",
        ),
        ("Деньги месяца сходятся", f"={cash}<0.000001"),
        (
            "Стройка покрыта взносом и кредитом",
            f"=SUMPRODUCT(ABS('Модель'!J2:J{last}-'Модель'!K2:K{last}-'Модель'!L2:L{last}))<0.000001",
        ),
        ("На остаток эскроу проценты не начисляются", f"=AND('Модель'!I2='Модель'!G2-'Модель'!H2,{roll}<0.000001)"),
        (
            "Срок депонирования в пределах ввода и запаса",
            f"='Вводы'!{_RVE}+'Вводы'!{_LAG}<='Вводы'!{_RVE}+'Вводы'!$B$19",
        ),
    ]
    for index, (label, formula) in enumerate(rows, start=1):
        checks.cell(index, 1, label)
        checks.cell(index, 2, formula)

    book.calculation.calcMode = "auto"
    book.calculation.fullCalcOnLoad = True
    book.save(OUT)


if __name__ == "__main__":
    main()
