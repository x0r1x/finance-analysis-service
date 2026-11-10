# eval/: размеченные книги для привязки (§5.6, §5.10.6, §12 фаза 2b)

Каждая книга — файл `eval/labels/{name}.json`. Книга должна быть загружена в FAS (`…:load`).

Дорожная карта аналитического ядра (матрица тип×метрика, корпус, `finding_kind`): [docs/analytical-core-roadmap.md](../docs/analytical-core-roadmap.md).

## Источники корпуса

Разметка и прогон mapping-eval с реальными книгами — на **локальной** машине с checkout FAS и соседним [finance-context-builder](https://github.com/x0r1x/finance-context-builder). Cloud CI приватные xlsx не хостит.

| Книга | Откуда брать | В этом репозитории |
|---|---|---|
| Packt | builder `resources/corpus/` (`packt-project-finance.xlsx`, fetch по `corpus.lock.json`) | golden dump: `tests/fixtures/builder/` + алиас `packt` в `tests/books.py` |
| RVI | то же (`rvi-project-finance.xlsx`) | dump + алиас `rvi` |
| Ашан | builder `resources/corpus/АШАН_модель*.xls(x)` (приватно; не в lock / не в git) | нет; labels при чувствительных путях — только локально |

Интеграционный путь FAS: `FAS_IT_CORPUS` или sibling `…/finance-context-builder/resources/corpus`, плюс `BUILDER_BASE_URL` и `POST /v1/books/{job_id}:load`. Для unit/contract без живого builder достаточно fixture dumps (`FixtureBuilder`).

Снимок **типа модели** (`eval/model_type/`, `tests/eval`) — отдельный прогон; он **не** заменяет mapping-eval по строкам.

## Формат labels

```json
{
  "job_id": "<sha256 содержимого книги>",
  "labels": {"<binding_key>": "cfads"},
  "by_path": {"Лист › Раздел › CFADS": "cfads", "Лист › Раздел › Agency fee": "NIL"},
  "critical": ["<binding_key>"],
  "critical_paths": ["Лист › Раздел › Total debt service"]
}
```

`NIL` — строка вне глоссария: её правильный исход `unknown` или `ambiguous`, а не соседнее понятие.
`by_path` сверяется с `label_path_text` строки; `labels` по `binding_key` приоритетнее.

## Workflow разметки (локально)

1. Убедиться, что книга есть в корпусе builder или уже загружена по fixture `job_id` (Packt/RVI — `tests/books.py`).
2. Загрузить книгу в локальный FAS (`…:load`), зафиксировать `job_id`.
3. Создать `eval/labels/{name}.json`: critical-понятия метрик (`cfads`, `debt_service`, `interest`) и NIL-строки на critical path; где путь стабилен — `by_path` / `critical_paths`.
4. Прогнать `fas eval mapping` (ниже); при регрессе соседних понятий — `--prune`.
5. Non-secret labels коммитить в git. Ашан и прочие клиентские книги — local-only, если пути/имена чувствительны (как K3 / escrow: env + `.local.yaml`, без имён клиентов в git).
6. Числа top-1 / ECE / false binds / NIL recall записывать в отчёт только после реального прогона; до появления labels цели фазы 2b остаются **допущениями**.

В репозитории каталог `eval/labels/` пока пуст (только `.gitkeep`).

## Команды

Нужны `FAS_REDIS_URL` и хранилище FAS; каталог задаёт `FAS_EVAL_DIR`, по умолчанию `eval`:

- `fas eval mapping` — top-1 по понятиям, доля ложных привязок (вся и по понятиям метрик), NIL precision/recall
  (и на critical-строках), ECE и Brier по `confidence`, проверка целей фазы 2b;
- `fas eval mapping --prune cfads,debt_service` — eval с удалённым понятием (BLINKout): строки понятия
  не должны уйти в соседнее;
- `fas calibrator train` — калибратор-кандидат по `examples/` (Platt, isotonic при > 1000 пар, cv по книгам);
  `fas calibrator activate <version>` — включить, `fas calibrator list` — история;
- `fas glossary shadow <version>` — shadow-отчёт кандидата против active (тот же гейт, что у `:transition`).

## Цели фазы 2b

Цели фазы 2b **[допущение]** до появления размеченного корпуса: top-1 ≥ 0.9 на cfads/debt_service/interest, ECE < 0.05, ложные привязки ≤ 2 %,
NIL recall ≥ 0.9 на critical-строках. Проверить их можно только на 20–30 размеченных книгах
(открытый вопрос 2, §14): в репозитории labels нет. После локальной разметки Packt/RVI/Ашан (+ рост корпуса)
числа из `fas eval mapping` становятся evidence; до этого пороги в README/design не считать измеренными.
