# eval/: размеченные книги для привязки (§5.6, §5.10.6, §12 фаза 2b)

Каждая книга — файл `eval/labels/{name}.json`. Книга должна быть загружена в FAS (`…:load`).

Дорожная карта аналитического ядра (матрица тип×метрика, корпус, `finding_kind`): [docs/analytical-core-roadmap.md](../docs/analytical-core-roadmap.md).

## Источники корпуса

Разметка и прогон mapping-eval с реальными книгами — на **локальной** машине с checkout FAS и соседним [finance-context-builder](https://github.com/x0r1x/finance-context-builder). Cloud CI приватные xlsx не хостит.

| Книга | Откуда брать | В этом репозитории |
|---|---|---|
| Packt | builder `resources/corpus/` (`packt-project-finance.xlsx`, fetch по `corpus.lock.json`) | golden dump: `tests/fixtures/builder/` + алиас `packt` в `tests/books.py`; `eval/labels/packt.json` |
| RVI | то же (`rvi-project-finance.xlsx`) | dump + алиас `rvi`; `eval/labels/rvi.json` |
| Ашан и др. client CF | builder `resources/corpus/` private xls(x) (не в lock / не в git) | **не коммитить**; labels → `eval/local/labels/` (gitignore), см. `eval/local/README.md` |
| Slice-5 model workbooks | `tests/fixtures/model_books/` (halyard, meridian, …) | model-type / cite only; mapping labels **ещё нет** (нужен builder dump + `job_id`) |

Рост корпуса **где feasible**: новые non-secret labels в `eval/labels/`; private — только `eval/local/labels/` (мержится автоматически при `FAS_EVAL_DIR=eval`). До появления новых golden dumps commit-safe набор остаётся Packt+RVI.

Интеграционный путь FAS: `FAS_IT_CORPUS` или sibling `…/finance-context-builder/resources/corpus`, плюс `BUILDER_BASE_URL` и `POST /v1/books/{job_id}:load`. Для unit/contract без живого builder достаточно fixture dumps (`FixtureBuilder`).

Снимок **типа модели** (`eval/model_type/`, `tests/eval`) — отдельный прогон; он **не** заменяет mapping-eval по строкам.

## Формат labels

```json
{
  "schema_version": "1",
  "id": "packt",
  "job_id": "<sha256 содержимого книги>",
  "labels": {"<binding_key>": "cfads"},
  "by_path": {"Лист › Раздел › CFADS": "cfads", "Лист › Раздел › Agency fee": "NIL"},
  "critical": ["<binding_key>"],
  "critical_paths": ["Лист › Раздел › Total debt service"]
}
```

`id` — короткий ключ книги в `summary.top1_by_book` (если нет — stem имени файла). В итоговом eval-наборе `id` должен быть уникален (два разных `job_id` с одним `id` — ошибка загрузки).

`NIL` — строка вне глоссария: её правильный исход `unknown` или `ambiguous`, а не соседнее понятие.
`by_path` сверяется с `label_path_text` строки; `labels` по `binding_key` приоритетнее.

**Контракт NIL-метрик** (`domain/evaluation.py`, `NIL_STATUSES`): recall и precision считают попаданием только статусы `unknown` и `ambiguous`. Статусы `not_applicable` и `ignored` **не** входят в NIL recall и **не** считаются предсказанием NIL для precision (даже если truth = `NIL`).

## Workflow разметки (локально)

1. Убедиться, что книга есть в корпусе builder или уже загружена по fixture `job_id` (Packt/RVI — `tests/books.py`).
2. Загрузить книгу в локальный FAS (`…:load`), зафиксировать `job_id`.
3. Создать `eval/labels/{name}.json`: critical-понятия метрик (`cfads`, `debt_service`, `interest`) и NIL-строки на critical path; где путь стабилен — `by_path` / `critical_paths`.
4. Прогнать `fas eval mapping` (ниже); при регрессе соседних понятий — `--prune`.
5. Non-secret labels коммитить в git. Ашан и прочие клиентские книги — local-only, если пути/имена чувствительны (как K3 / escrow: env + `.local.yaml`, без имён клиентов в git).
6. Числа top-1 / ECE / false binds / NIL recall записывать в отчёт только после реального прогона; до появления labels цели фазы 2b остаются **допущениями**.
7. **Pins воспроизводимости** (обязательны в каждом измеренном отчёте; без них дельты метрик недействительны):
   - version схемы labels;
   - SHA/version glossary (и taxonomy, если версионируется отдельно);
   - identity builder;
   - FAS git SHA / mapping version;
   - источник книги + `job_id`;
   - точная командная строка `fas eval mapping` (включая `--prune`, если был);
   - version калибратора — если в отчёте есть ECE.

В репозитории: `eval/labels/packt.json` и `eval/labels/rvi.json` (fixture `job_id` из `tests/books.py`). Ашан и прочие private — только `eval/local/labels/` (см. `eval/local/README.md`); loader мержит их с committed labels. Клиентские имена/пути и xlsx в git не попадают.

Измеренный прогон на этом срезе: [eval/mapping/report.md](mapping/report.md). CLI печатает агрегат и **per-book top-1** (`summary.top1_by_book`). Это **не** полный корпус 20–30 книг; цели фазы 2b по-прежнему нельзя считать закрытыми.

## Команды

Нужны `FAS_REDIS_URL` и хранилище FAS; каталог задаёт `FAS_EVAL_DIR`, по умолчанию `eval`:

- `fas eval mapping` — top-1 по понятиям (агрегат + `top1_by_book`), доля ложных привязок (вся и по понятиям метрик), NIL precision/recall
  (и на critical-строках), ECE и Brier по `confidence`, проверка целей фазы 2b;
- `fas eval mapping --prune cfads,debt_service` — eval с удалённым понятием (BLINKout): строки понятия
  не должны уйти в соседнее;
- `fas calibrator train` — калибратор-кандидат по `examples/` (Platt, isotonic при > 1000 пар, cv по книгам);
  `fas calibrator activate <version>` — включить, `fas calibrator list` — история;
- `fas glossary shadow <version>` — shadow-отчёт кандидата против active (тот же гейт, что у `:transition`).

## Цели фазы 2b

Цели фазы 2b **[допущение]** до появления размеченного корпуса: top-1 ≥ 0.9 на cfads/debt_service/interest, ECE < 0.05, ложные привязки ≤ 2 %,
NIL recall ≥ 0.9 на critical-строках. Проверить их можно только на 20–30 размеченных книгах
(открытый вопрос 2, §14): есть стартовые labels Packt/RVI; полный корпус 20–30 книг ещё не собран. Числа в `eval/mapping/report.md` — evidence на **размеченном срезе** **только вместе с pin-набором** (см. workflow п. 7), не закрытие целей фазы 2b. Сравнение прогонов без совпадающих pins — не evidence.
