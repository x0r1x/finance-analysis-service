"""Синтетический портфель лизингодателя. Формулы считает LibreOffice, не этот скрипт.

Запуск из корня репозитория:

    python tests/fixtures/model_books/leasing/build_lease_book.py
    soffice --headless --norestore -env:UserInstallation=file:///tmp/lo-profile \
        --convert-to xlsx --outdir tests/fixtures/model_books/leasing \
        tests/fixtures/model_books/leasing/lease_portfolio.xlsx
"""

from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).with_name("lease_portfolio.xlsx")


def main() -> None:
    book = Workbook()
    schedule = book.active
    schedule.title = "Schedule"
    schedule.append(["Contract", "Year", "Opening", "Rate", "DPD", "Interest", "Principal", "Payment", "Closing", "NPL"])
    # A и B обслуживаются. C — просрочка 180 дней, процент не начисляется.
    rows = [
        ("A", 1, 1000, 0.1, 0, 100),
        ("A", 2, None, 0.1, 0, 100),
        ("B", 1, 400, 0.1, 0, 100),
        ("B", 2, None, 0.1, 0, 100),
        ("C", 1, 200, 0.1, 180, 0),
        ("C", 2, None, 0.1, 180, 0),
    ]
    for index, (contract, year, opening, rate, dpd, principal) in enumerate(rows, start=2):
        schedule.cell(index, 1, contract)
        schedule.cell(index, 2, year)
        if opening is None:
            schedule.cell(index, 3, f"=I{index - 1}")
        else:
            schedule.cell(index, 3, opening)
        schedule.cell(index, 4, rate)
        schedule.cell(index, 5, dpd)
        schedule.cell(index, 6, f"=IF(E{index}>=90,0,C{index}*D{index})")
        schedule.cell(index, 7, principal)
        schedule.cell(index, 8, f"=F{index}+G{index}")
        schedule.cell(index, 9, f"=C{index}-G{index}")
        schedule.cell(index, 10, f"=IF(E{index}>=90,C{index},0)")
    summary = book.create_sheet("Summary")
    summary["A1"] = "Lessor portfolio"
    summary["A2"] = "Interest income"
    summary["B2"] = "=SUM(Schedule!F2:F7)"
    summary["A3"] = "Gross portfolio"
    summary["B3"] = "=SUMIF(Schedule!B2:B7,1,Schedule!C2:C7)"
    summary["A4"] = "NPL balance"
    summary["B4"] = "=SUMIF(Schedule!B2:B7,1,Schedule!J2:J7)"
    summary["A5"] = "NPL share"
    summary["B5"] = "=B4/B3"
    summary["A6"] = "Provision rate"
    summary["B6"] = 0.5
    summary["A7"] = "Provisions"
    summary["B7"] = "=B6*B4"
    summary["A8"] = "Provision coverage"
    summary["B8"] = "=B7/B4"
    book.save(OUT)


if __name__ == "__main__":
    main()
