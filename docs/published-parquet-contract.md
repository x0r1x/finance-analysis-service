# Published Parquet contract (DataMesh)

Фаза 5 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G5). Нормативные внутренние правила записи — [design-v0.23.md](design-v0.23.md) §4.11–4.12. Схемы колонок — `src/finance_analysis/adapters/storage/schemas/*.json`. Машинный индекс наборов — `src/finance_analysis/domain/contracts/published_parquet.json`.

Код проверок: `finance_analysis.domain.published_parquet`.

Этот документ фиксирует **обещания внешнему читателю озера** поверх уже существующих маркеров и схем. FAS **не** пишет Iceberg/Hive/Delta и **не** регистрирует таблицы во внешнем Metastore.

Версия контракта: **`published_parquet@1.0`** (поле `contract_version` в машинном индексе). Смена MAJOR — ломающее изменение обещаний; MINOR — аддитивное уточнение (новые датасеты/поля в индексе).

## 1. Что публикуется

Обычный Parquet (+ JSON-маркеры) в раскладке object store FAS. Группировка — по книге и сборке, не по таблице (design §4.12, решение не вводить `key=value` партиции).

| Зона | Путь (шаблон) | Маркер фиксации | Когда можно читать |
|---|---|---|---|
| Проекция builder | `books/{job_id}/{build_key}/a/{attempt}/projection/{dataset}.parquet` | `…/{build_key}/manifest.json` | только пути из `manifest.files` |
| Derived | `books/{job_id}/{build_key}/derived/{derive_key}/a/{attempt}/{dataset}.parquet` | `…/derived/{derive_key}/_done.json` | только пути из `_done.files` |
| Результаты анализа | `books/{job_id}/{build_key}/results/{analysis_id}/*.parquet` | `…/results/{analysis_id}/result.json` | только пути из `result.files` |
| Релиз глоссария | `glossary/releases/{version}/…` | `glossary/releases/{version}/glossary.json` | после появления `glossary.json` |
| Указатель головы | `books/{job_id}/_head.json`, `glossary/_head.json`, `semantic_models/_head.json` | сам указатель (`put_if_match`) | указывает на текущие ключи; история — отдельно |

`fas_schema_version` (`MAJOR.MINOR`) живёт в маркере сборки и в footer Parquet (`fas.schema = "{dataset}@{MAJOR.MINOR}"`), **не** колонкой таблицы (P5, P9).

## 2. Датасеты и ключи

Машинный перечень — `published_parquet.json` → `datasets[]`. Кратко:

| Группа | Датасеты | Обязательные ключи в каждом файле |
|---|---|---|
| projection | `dim_row`, `dim_period`, `fact_observation`, `graph_links` | `model_id`, `build_key` |
| derived | `bindings`, `row_semantics`, `period_semantics`, `coverage` | `model_id`, `build_key`, `state_seq`, `derive_key` (+ `glossary_version` у bindings) |
| results | `run`, `ratios`, `findings` | `model_id`, `build_key`, `analysis_id`, `state_seq` |
| other | `candidates`, `signals`, `unmapped`, `examples` | см. `schemas/*.json` |

Стабильные идентификаторы для join между наборами: `model_id` (= `job_id` builder), `build_key`, `binding_key`, `row_key`, `axis_id`, `period_id`, `cell_id`, `concept`, `derive_key`, `glossary_version` / `taxonomy_version`, публичный `semantic_model_version` (в `run`, фаза 2).

Семантика полей — в `schemas/{dataset}.json` (`type`, `nullable`, `unit`, `description`, `since`). Этот контракт **не** дублирует описания колонок; он требует, чтобы индекс и `schemas/*.json` совпадали по именам датасетов и чтобы колонки в файле совпадали со схемой (имена, типы, порядок).

## 3. Типы и эволюция схем

Совместимость с design §4.12:

| Правило | Обещание Mesh |
|---|---|
| P1 | Плоские простые типы; сложные поля — `*_json` строкой. Исключение (согласовано с design §4.12): `binary` **только** у `embedding_f32` — сырой `float32` little-endian (`<f4`), длина `4×dims`, `dims` от `embed_model`; decode `np.frombuffer(raw, dtype="<f4")` |
| P2 | Имена `snake_case` ASCII; переименование = MAJOR |
| P3 | Время — `timestamp(us, tz=UTC)` в колонках `*_utc`; даты периодов — `date32` |
| P4 | Деньги: источник истины `DECIMAL`; `float64`-копия документирована |
| P5 | Ключи в каждом файле (см. §2) |
| P6 | В пределах MAJOR — **только аддитивно**: новая nullable-колонка в **конец**, с `since = MAJOR.MINOR` |
| P7 | Файлы неизменяемы; маркер пишется последним и перечисляет `sha256` / `rows` / `schema` |
| P8–P10 | zstd, один row group на файл книги, footer `fas.*`, описание в `schemas/*.json` |

Старые сборки остаются на своей версии схемы навсегда (design §4.10). Читатель различает версии по `fas.schema` / `fas_schema_version`.

## 4. Маркеры и история

1. Папка **без** маркера для внешнего читателя **не существует**: GC удаляет недописанное (design §4.10).  
2. Список файлов сборки / derived / result берётся **из маркера**, не листингом префикса до появления маркера.  
3. Каждый элемент `files` обязан содержать `sha256` (64 hex), `rows` (int ≥ 0) и `schema` (`dataset@MAJOR.MINOR`). Пустой meta `{}` — не commit.  
4. Зафиксированное не удаляется: сборки с `manifest.json`, `derived/` с `_done.json`, `results/` с `result.json`, журнал, `_builds/`, релизы глоссария.  
5. «Текущая» сборка — из `_head.json`; история — листинг `books/{job_id}/_builds/` (одна запись на `build_key`).

Код: `parse_marker_files` (структура) и `verify_committed_files` (sha256 / rows / `fas.schema` против payload).

## 5. Что FAS **не** гарантирует

| Не обещается | Почему |
|---|---|
| List-before-marker | Префикс без маркера может быть частичным или под GC; читатель обязан ждать маркер |
| Cross-bucket / multi-object transactions | Атомарность — `put_if_absent` маркера + CAS `_head`, не распределённая транзакция |
| Iceberg / Hive / Delta writers и Metastore | Снято в design 0.8/0.12; внешний процесс может сам построить таблицы поверх Parquet |
| `LakePublisherPort`, Airflow-операторы внутри FAS, `_consumers/` | Не-цели фазы 5 и дорожной карты |
| SLA оркестраторам и движкам озера | Внешнее потребление — ответственность читателя (decision 19 / §4.11) |
| Раскладка `dataset/job_id=…/build_key=…` | Не вводится; ключи уже в файлах (P5) |

## 6. Совместимость с §4.11–4.12

Этот контракт **уточняет**, а не заменяет §4.11–4.12:

- внутренние инварианты записи (§4.11) остаются источником истины для писателя FAS;  
- правила P1–P10 (§4.12) — источник истины для формы Parquet;  
- здесь — публичный срез для DataMesh: маркеры как commit-сигнал, индекс датасетов, запрет list-before-marker, явное «нет writers каталога таблиц».

При расхождении документа фазы 5 и design приоритет у **кода + `schemas/*.json`**, пока не принят MAJOR контракта / схемы.

## 7. Машинный индекс

`src/finance_analysis/domain/contracts/published_parquet.json`:

- `contract_version` — версия этого контракта;  
- `aligns_with` — ссылки на design §4.11–4.12 и `fas_schema_version`;  
- `markers` — имена маркеров и роль;  
- `datasets[]` — `{name, group, schema, required_keys[], marker}`;  
- `non_guarantees[]` — стабильные коды из §5.

Читатель или CI сверяет индекс с `schemas/*.json` и гоняет тесты `tests/unit/test_published_parquet_contract.py`.
