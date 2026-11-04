# Прогон типа модели

Пороги: accept 0.6, gap 0.15. Прогон пороги не меняет.

| книга | ожидание | ответ | top1 | top2 | разрыв | ≥ accept | ≥ gap | ложные |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| packt | project_finance | project_finance | project_finance 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| rvi | project_finance | project_finance | project_finance 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| toll_road | project_finance | project_finance | project_finance 1.000 | lbo_ma 0.500 | 0.500 | да | да | — |
| port | investment_project | investment_project | investment_project 1.000 | lbo_ma 0.500 | 0.500 | да | да | — |
| hybrid_ppp | ppp_concession + project_finance | ppp_concession + project_finance | ppp_concession 1.000 | project_finance 1.000 | 0.000 | да | нет | — |
| corporate | corporate | corporate | corporate 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| ambiguous_statements_and_debt | вопрос: ambiguous | вопрос: ambiguous | corporate 1.000 | project_finance 1.000 | 0.000 | да | нет | — |
| ask_instead_of_other | вопрос: unknown | вопрос: unknown | bank_leasing 0.000 | corporate 0.000 | 0.000 | нет | нет | — |
| partial_npv | вопрос: unknown | вопрос: unknown | lbo_ma 0.500 | bank_leasing 0.000 | 0.500 | нет | да | — |
| halyard | lbo_ma | lbo_ma | lbo_ma 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| meridian | dcf_valuation | dcf_valuation | dcf_valuation 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| debtlens | real_estate_income | real_estate_income | real_estate_income 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| solar_dogu | renewables_dpm | renewables_dpm | renewables_dpm 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |
| lease_portfolio | bank_leasing | bank_leasing | bank_leasing 1.000 | corporate 0.000 | 1.000 | да | да | — |
| purchase_price_allocation | вопрос: unknown | вопрос: unknown | bank_leasing 0.000 | corporate 0.000 | 0.000 | нет | нет | — |
| sources_without_exit | вопрос: unknown | вопрос: unknown | lbo_ma 0.500 | bank_leasing 0.000 | 0.500 | нет | да | — |
| development_escrow | development_escrow | development_escrow | development_escrow 1.000 | bank_leasing 0.000 | 1.000 | да | да | — |

## Сводка

- accuracy основного типа: 12/12 = 1.000
- доля вопросов: 5/17 = 0.294
- верные решения: 17/17 = 1.000

| тип | ложные | доля |
| --- | --- | --- |
| bank_leasing | 0 | 0.000 |
| corporate | 0 | 0.000 |
| dcf_valuation | 0 | 0.000 |
| development_escrow | 0 | 0.000 |
| investment_project | 0 | 0.000 |
| lbo_ma | 0 | 0.000 |
| other | 0 | 0.000 |
| ppp_concession | 0 | 0.000 |
| project_finance | 0 | 0.000 |
| real_estate_income | 0 | 0.000 |
| renewables_dpm | 0 | 0.000 |

Минимальный score верного одиночного типа: 1.000. Минимальный разрыв верного одиночного типа: 0.500. Уверенные ответы с разрывом ниже порога: hybrid_ppp. Вопросы, где оба лидера не ниже accept, а разрыв ниже порога: ambiguous_statements_and_debt.
