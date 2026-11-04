# Книги среза 5

В git лежит книга и LICENSE с зафиксированного коммита. Halyard и Meridian записаны без кэша, поэтому лежит копия `*.recalc_libreoffice.xlsx`. DebtLens и солнечная модель уже с кэшем. Лизинг синтетический: скрипт `leasing/build_lease_book.py`, кэш проставлен LibreOffice.

finance-context-builder эти файлы не читает. Тест сверяет кэш ячеек, а тип модели — по привязкам в `tests/fixtures/model_type_eval/cases.yaml`. Новых метрик по этим строкам нет.

| Каталог | Тип | Источник |
| --- | --- | --- |
| `halyard/` | `lbo_ma` | [bmazzoldi/lbo-engine](https://github.com/bmazzoldi/lbo-engine) @ `3c122a4`, MIT © 2026 Benicio Mazzoldi. MOIC 2.13x, IRR 16.3%, sources = uses = 1052.5, долг / EBITDA = 5.0x |
| `meridian/` | `dcf_valuation` | [sillysofter/dcf-valuation](https://github.com/sillysofter/dcf-valuation) @ `99947d2`, MIT. WACC 9.61%, EV 5 717.6 / 6 192.8 |
| `debtlens/` | `real_estate_income` | [sanjayanvisagendran/ebtlens-real-estate-underwriting](https://github.com/sanjayanvisagendran/ebtlens-real-estate-underwriting) @ `d22dbd5`, MIT © 2026 Sanjayan Visagendran. NOI 3 288 000, cap rate 5.75%, вакансия 5%, DSCR 1.30x |
| `solar/` | `renewables_dpm` | [dogudogukan/solar-financial-modeling](https://github.com/dogudogukan/solar-financial-modeling) @ `8258094`, MIT © 2024 Dogukan Dogu. 25 МВт DC, деградация 0.5%, P50 50 370 МВт·ч, тариф 72.75, DSCR P50 1.35x |
| `leasing/` | `bank_leasing` | Синтетический портфель. Процентный доход 260, NPL 200 из 1 600 (12.5%), резерв 100, покрытие 0.5 |
