# Фикстуры ГЧП и инвестиционного проекта

Компактные ряды из двух моделей MIT. В git лежит только то, что сверяют тесты: денежный поток, обслуживание долга и опубликованные NPV, IRR и минимум DSCR. Исходные xlsx не коммитятся. finance-context-builder эти файлы не читает.

| Файл | Книга | Что сверяется |
| --- | --- | --- |
| `toll_road.json` | [Infrastructure Project Finance Model](https://github.com/mahitha-kunireddy/Infrastructure-Project-Finance-Model), MIT, © 2026 mahitha-kunireddy | Минимум DSCR 0.88x (в книге 0.8760284169069288), среднее 2.51x, NPV при WACC 11% ₹2,310 млн, project IRR 15.26%. Порог ковенанта 1.20x, три года ниже порога, equity IRR 20.59% — факты книги, отдельными метриками FAS не считаются |
| `port.json` | [Port Logistics PPP Feasibility](https://github.com/kushwanth7010/Port-Logistics-PPP-Feasibility), MIT, © 2026 Sampathi Kushwanth | Бездолгий проект: NPV 44.38645685868875 и project IRR 0.127826852360176 при ставке 12% |

Тексты лицензий: `LICENSE-toll-road`, `LICENSE-port`.

Плата концедента, капитальный грант и возмещение до минимального гарантированного дохода в этих книгах не выделены отдельными строками. Поэтому дорога по сигналам каталога — `project_finance`, порт — `investment_project`. Гибрид `ppp_concession` + `project_finance` проверяется синтетической привязкой, не этими файлами.
