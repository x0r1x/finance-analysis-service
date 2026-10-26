# eval/: размеченные книги для привязки (§5.6, §5.10.6, §12 фаза 2b)

Каждая книга — файл `eval/labels/{name}.json`. Книга должна быть загружена в FAS (`…:load`).

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

Команды (нужны `FAS_REDIS_URL` и хранилище FAS; каталог задаёт `FAS_EVAL_DIR`, по умолчанию `eval`):

- `fas eval mapping` — top-1 по понятиям, доля ложных привязок (вся и по понятиям метрик), NIL precision/recall
  (и на critical-строках), ECE и Brier по `confidence`, проверка целей фазы 2b;
- `fas eval mapping --prune cfads,debt_service` — eval с удалённым понятием (BLINKout): строки понятия
  не должны уйти в соседнее;
- `fas calibrator train` — калибратор-кандидат по `examples/` (Platt, isotonic при > 1000 пар, cv по книгам);
  `fas calibrator activate <version>` — включить, `fas calibrator list` — история;
- `fas glossary shadow <version>` — shadow-отчёт кандидата против active (тот же гейт, что у `:transition`).

Цели фазы 2b [допущение]: top-1 ≥ 0.9 на cfads/debt_service/interest, ECE < 0.05, ложные привязки ≤ 2 %,
NIL recall ≥ 0.9 на critical-строках. Проверить их можно только на 20–30 размеченных книгах
(открытый вопрос 2, §14): в репозитории их нет.
