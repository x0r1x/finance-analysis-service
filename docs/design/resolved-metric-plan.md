# Неизменяемый план разрешения метрики

Снято с `main` `b9e91b4` (слияние PR 107). Кода этот документ не меняет.

После единого резолвера в `domain/semantic_input.py` следующий шаг — одно семантическое исполнение метрики:

```text
каталог → движок разрешения → неизменяемый Resolved Metric Plan → расчёт
```

Тот же план читают след, пояснение и аудит. Расчёт, след, пояснение и аудит не выбирают вход заново. План — результат разрешения для одной метрики одной сборки, не второй каталог правил.

Цели: число совпадает с происхождением; видно, почему взят вход; видны отвергнутые варианты и причина; прогон воспроизводим; у плана есть версия и след для аудита.

Уточнения ниже приняты на ревью PR 108. Открытых вопросов из первой редакции нет.

## Инварианты

Три правила. Миграция проверяет каждое, а не только совпадение строк.

1. Один анализ даёт один план на метрику и `build_key`. `Analyses`, расчёт, след и `origin_view` читают этот результат. Они не вызывают `resolve_metric_plan` ещё раз, чтобы собрать «такой же» план.
2. Расчёт, след, пояснение и аудит пользуются этим разрешением и не повторяют выбор: ни `select_primary`, ни `choose_one_of`, ни `dscr_denominator_plan`, ни `interest_choice`, ни `confirm_paid_interest`, ни `shield_concepts`, ни `_basis`.
3. План строится на полном контексте сегодняшнего `free_cash_flow` и резолвера: факты, `graph_links`, привязки, вариант, `interest_order`, `row_fallbacks`, плюс `absent` и листы отчётности. Если след запрошен без расчёта, строитель один и контекст тот же полный. Урезанный план «только для следа» не строится.

DuckDB отделяет разрешение имён от исполнения. Binder подставляет таблицы и колонки по каталогу. Logical planner строит дерево логических операторов, генератор физического плана превращает его в дерево `PhysicalOperator`. Исполнение пушит `DataChunk` по этому дереву и к разбору запроса не возвращается. `EXPLAIN` показывает физический план и запрос не выполняет. Берём границу: потребители получают готовый план и выбор не повторяют. Отход: у DuckDB оптимизатор ещё переписывает логическое дерево до физического. У нас второго оптимизатора нет. Повторный вызов движка из расчёта или следа — нарушение инварианта, даже если строки сошлись бы.

OpenLineage запрещает потребителю достраивать рёбра из общих списков, если фасет уже назвал источники. Берём тот же запрет для выбора входа.

- [DuckDB internals](https://duckdb.org/docs/2.0/internals/overview.html) — binder, logical planner, physical plan generator, execution
- [DuckDB EXPLAIN](https://duckdb.org/docs/2.0/guides/meta/explain.html) — физический план, запрос не исполняется
- [Lineage Job Facet](https://openlineage.io/docs/spec/facets/job-facets/lineage/)

## 1. Где выбор входа живёт на этом main

Правила каталога остаются в `MetricExpression`, `interest_order` и `row_fallbacks`. Их загружает `application/model_types.py` (`load_interest_order`). Исполняемый выбор — другие функции. Их вызывают и расчёт, и резолвер, каждый своим проходом.

| Что выбирается | Где | Кто ещё вызывает |
|---|---|---|
| Понятие строки: `effective_concept`, иначе `concept` | `declared_concept` в `domain/binding_resolution.py` | расчёт, резолвер, правила, происхождение факта |
| Одна не-stale основная привязка. Несколько свежих bound: минимальный `binding_key` и флаг неоднозначности | `select_primary` там же | только резолвер (`_select_primary` в `domain/semantic_input.py`) |
| Член `one_of`. EBITDA и EBIT вместе дают EBITDA. Порядок YAML не участвует | `choose_one_of` в `domain/metrics.py` | `coverage_ratio` и `_specs` резолвера |
| Состав знаменателя DSCR: `debt_service` или запас из процентов и тела. Нет CFADS — в списке только CFADS. ADSCR сюда не входит | `dscr_denominator_plan` там же | `coverage_ratio` и `_dscr_plan` резолвера |
| Первое имя `interest_order`, у которого есть основная строка. Предупреждение `interest_basis_fallback`, если взяты уплаченные проценты, а начисления нет | `interest_choice` там же | `coverage_ratio`, `covenant_dscr` через `_swap_interest`, резолвер через `_interest_pick` |
| Единственная строка `interest` с кодом 4123 занимает пустой `interest_paid`. Занятый ключ не переписывается. Две такие строки ничего не добавляют | `confirm_paid_interest`, `paid_interest_row` там же | `coverage_ratio`, `free_cash_flow`, `covenant_dscr`, резолвер (`_with_confirmed_paid`) |
| Щит FCFF: `interest_paid` только у метрики `fcff` и только при базисе `interest_included` или `candidate` | `shield_concepts` и `_basis` в `domain/free_cash_flow.py` | резолвер (`_with_shield`). Сам `free_cash_flow` зовёт `_basis` ещё раз, не `shield_concepts` |
| Список входов, который расчёт берёт | `resolve_semantic_inputs` в `domain/semantic_input.py` | след и происхождение. Расчёт эту функцию не вызывает |

Слой уже такой: `binding_resolution` никого выше не импортирует. `semantic_input` импортирует `binding_resolution`, `metrics` и `free_cash_flow`.

### Расчёт выбирает сам

`coverage_ratio` (`domain/metrics.py`) вызывает `confirm_paid_interest`, для DSCR — `dscr_denominator_plan`, для ICR — `interest_choice` и `choose_one_of`. Неоднозначность ищет своим `_groups`: основная, не stale, статус не обязан быть `bound`. Отдельная ветка ловит `status == "ambiguous"`. При неоднозначности возвращает `status: needs_input` и `needs_input[{kind: concept, reason: ambiguous, subject}]`. Строку по минимальному `binding_key` не выбирает: `select_primary` расчёт не вызывает. `_primaries` при нескольких строках оставляет последнюю в списке, но до арифметики `coverage_ratio` при `len > 1` уже останавливается.

`free_cash_flow` вызывает `confirm_paid_interest` и `_basis`. Неоднозначность OCF и capex считает `_ambiguous_primary`: статус `bound` или `bound_with_warning`, stale не отсекает.

`covenant_dscr` (`domain/covenant.py`) снова вызывает `confirm_paid_interest` и подменяет проценты через `_swap_interest`. `select_ratio` оттуда ведёт в `coverage_ratio` или `free_cash_flow`. Снаружи это `Analyses` (`application/analyses.py`): `dispatch_cover`, иначе `select_ratio`.

Правила ходят в расчёт и местами выбирают строку третий раз:

- `plugins/rules/coverage.py` вызывает `coverage_ratio` и свой `_primary` (`_groups` и `_primaries`);
- `plugins/rules/ratios.py` вызывает `coverage_ratio` и свой `_primary`: первая bound-строка, если она ровно одна; stale не отфильтрован; минимальный `binding_key` не используется.

`cover_metrics.py` вызывает `coverage_ratio` для сводок.

### След, происхождение и цепь читают резолвер, не результат расчёта

`trace_metric` (`domain/graphs.py`) вызывает `resolve_semantic_inputs`. `_step_for_resolved` привязку заново не выбирает: шаг собирается из уже выбранного `SemanticInput`. Несколько свежих основных дают finding `ambiguous_primary_binding` и шаг с минимальным `binding_key`. Расчёт в этом случае число не считает. Это текущий раскол, его держит `test_two_primaries_are_visible_in_the_trace_and_not_a_confirmed_origin_input` и `test_two_concept_only_primaries_block_calculation_and_stay_ambiguous_on_the_trace`.

`check_metric_physical_trace` только оборачивает `trace_metric`. HTTP собирает `application/service.py` `metric_trace_view`: в след кладётся `financial_catalog.version` как `catalog_version` и `build_key` сборки.

`origin_view` (`domain/formula_origin.py`) для каждой метрики снова вызывает `resolve_semantic_inputs`. Семена с `row_key` идут в `FormulaOrigin` и в `FormulaChain` (глубина, семя, `source` семени, `confirmed`). Аудит вызывает это из `Analyses._formula_origin` и кладёт словарь в `result_data.formula_origin`. Полноту графа считает `lineage_completeness` отдельно от выбора входа.

`application/explain.py` (`template_text`, `narrate`) выбор строки не делает: фраза строится из `code` и `params` находки. Маршрут — `explain_finding` в `adapters/api/route/analyses.py`.

Пунктирные строки NCF добавляет сам `trace_metric` (`dashed_lines`), не резолвер.

Тесты `tests/unit/test_semantic_input.py` сравнивают два прохода: резолвер против `coverage_ratio` и против следа. Общего объекта, который расчёт был бы обязан прочитать, нет. Функции выбора остаются публичным входом.

Три определения «несколько основных» на одном main:

| Функция | Кого считает | Что возвращает |
|---|---|---|
| `select_primary` | `is_primary`, статус bound, не stale | минимальный `binding_key`, `ambiguous=True` |
| `metrics._groups` | `is_primary`, не stale, любой статус | список; расчёт останавливается |
| `free_cash_flow._ambiguous_primary` | `is_primary`, статус bound, stale не исключён | имя понятия |
| `ratios._primary` | `is_primary`, статус bound, stale не исключён | первая строка или `None`, если их не одна |

## 2. Модель плана

План — снимок разрешения. Каталог по-прежнему отвечает на вопрос «какие определения существуют». План отвечает на вопрос «что выбрано для этой метрики этой сборки».

Так устроены семантические слои, которые открыты ниже. MetricFlow хранит определения в YAML семантического графа и по запросу строит SQL, а не вторую копию метрик. LookML описывает измерения и меры, генератор Looker строит SQL запроса. Cube описывает меры в кубе и при запросе генерирует SQL. Берём это разделение: каталог не подменяется планом. Отход: у MetricFlow, Looker и Cube результат компиляции — SQL под один вопрос, его не передают одновременному расчёту, следу и аудиту как неизменяемый объект. Нам нужен именно объект: три потребителя уже расходятся, пока у них нет общего результата.

### Поля

Типы — в новом модуле `domain/resolved_plan.py`. Он ничего не импортирует из `metrics`, `free_cash_flow` и `semantic_input`: иначе цикл, потому что резолвер уже импортирует расчёт. Движок остаётся функцией рядом с `resolve_semantic_inputs` и только заполняет эти типы. Потребители импортируют типы, не движок.

Все классы `frozen=True`. Поля-коллекции — `tuple`, не `list`. Нет методов, которые меняют поля. `as_dict` возвращает новый словарь.

`ResolvedMetricPlan`:

| Поле | Тип | Смысл |
|---|---|---|
| `schema` | `str` | `resolved_metric_plan@1.0`. Конверт будущего контракта, не часть хеша. В `metricTrace` этого имени нет |
| `plan_id` | `str` | первые 16 hex того же SHA-256, что `content_sha256`. В хешируемое тело не входит |
| `content_sha256` | `str` | полный SHA-256 тела, 64 hex. Идентичность и аудит. В публичную модель пока не входит |
| `resolution_engine_version` | `str` | версия алгоритма движка. Входит в хеш. Смена алгоритма отличима от смены результата |
| `metric_id` | `str` | показатель |
| `variant` | `str \| None` | выбранный вариант (`pf`, `housing`, …) или `None`, если сработала база или формула без варианта |
| `variant_source` | `str` | как сейчас у резолвера: `variant:…`, `base:…`, `formula` |
| `catalog_version` | `str \| None` | `FinancialModelCatalog.version`, тот же id, что след уже пишет в `catalog_version`. Считает `catalog_version_for`: sha256 канонического JSON показателей, 16 hex |
| `semantic_model_version` | `str \| None` | SMV из `docs/semantic-model-version.md`. Записывается для воспроизводимости окружения. В хеш плана не входит: SMV меняется от правил и глоссария, которые выбор строки не делают |
| `build_key` | `str \| None` | id сборки книги. Отдельного `build_id` в коде нет |
| `model_id` | `str \| None` | книга |
| `status` | `str` | статус разрешения, не статус арифметики: `resolved`, `needs_input`, `missing_input` |
| `inputs` | `tuple[ResolvedInput, …]` | только подтверждённые входы, которые можно передать в арифметику |
| `diagnostic` | `tuple[DiagnosticCandidate, …]` | неподтверждённый кандидат для следа. В арифметику не входит |
| `rejected` | `tuple[RejectedAlternative, …]` | альтернативы, которые правила не выбрали |
| `fallbacks` | `tuple[AppliedFallback, …]` | применённые замены |
| `warnings` | `tuple[PlanWarning, …]` | предупреждения выбора (`interest_basis_fallback`, `icr_numerator`) |
| `needs_input` | `tuple[NeedsInput, …]` | вопросы выбора. Пусто, если их нет |
| `shield` | `ShieldDecision \| None` | базис щита FCFF, решённый один раз. У остальных метрик `None` |

`ResolvedInput`: `concept`, `role` (`all_of` \| `one_of`), `source` (`formula`, `variant:…`, `base:…`, `fallback`, `paid_interest`), `binding_key`, `row_key`, `missing` (`no_primary_binding` \| `stale_binding` \| `None`), `ambiguous: bool`, `confirmed: bool`. В собранном плане у каждого элемента `inputs` оба флага фиксированы: `ambiguous=false`, `confirmed=true`. Попадание в `inputs` и есть допуск к арифметике.

`DiagnosticCandidate`: `concept`, `role`, `source`, `binding_key`, `row_key`, `reason` (`ambiguous_primary_binding`). Это всегда неподтверждённый вариант. Отдельного «иногда считать» у него нет.

`RejectedAlternative`: `concept`, `binding_key \| None`, `row_key \| None`, `reason`. Причины закрытым списком: `not_selected_one_of`, `interest_order_skipped`, `not_min_binding_key`, `debt_service_present`, `shield_not_applied`.

`ShieldDecision`: `basis` и `reason`. `basis` — то, что сегодня возвращает `_basis`: `interest_included`, `candidate`, `interest_excluded`, `unknown`. `reason` — какая ветка `_basis` сработала (`statement_4100_with_4123`, `financing_without_4123`, `formula_candidate`, `no_basis`). Этих строк в коде ещё нет: их пишет движок, когда базис записывается в план. Второй вызов `_basis` их не пересчитывает.

`AppliedFallback`: `slot` (имя слота `interest_order`: `pf`, `icr`, `icr_ebit`, `corporate_covenant`, …), `replaced`, `chosen`, `warning_code \| None`.

`PlanWarning`: `code`, `params` как кортеж пар строк, чтобы канонический JSON был стабилен.

`NeedsInput`: `kind` (`concept`), `reason` (`ambiguous` \| `concept_unknown` \| `absent_in_book`), `subject`.

В план не входят значения ячеек, окно периодов, масштаб и `lineage_completeness`. Это исполнение и физический граф. DuckDB `EXPLAIN` показывает план и запрос не выполняет: в оценке строк стоит `~`. `EXPLAIN ANALYZE` уже выполняет запрос и добавляет фактические мощности и время. Число коэффициента и `scale_unconfirmed` остаются результатом расчёта. Отход: мы не ищем самый дешёвый оператор соединения. Выбор здесь семантический. Коэффициент по-прежнему считает `Decimal` в `domain/metrics.py`, не DuckDB.

### Неоднозначность: три списка, одно чтение

Раскол сегодняшнего main сохраняется. Меняется только то, что он записан тремя полями, а не двумя смыслами одного списка.

Несколько свежих bound-основных одного понятия:

- `status = needs_input`;
- `needs_input` — тот же вопрос, что сегодня возвращает расчёт: `{kind: concept, reason: ambiguous, subject}`. Список не расширяем, чтобы ответ расчёта не поехал;
- в `inputs` этого понятия нет;
- в `diagnostic` один кандидат: минимальный `binding_key`, как `select_primary`. След ставит по нему `integrity.reason = ambiguous_primary_binding` и не считает его подтверждённым семенем происхождения;
- остальные такие строки — в `rejected` с `reason: not_min_binding_key`. Их правило не выбрало.

Расчёт при `status != resolved` число не считает. Арифметика читает только `inputs` и только элементы с `confirmed=true`. Если кандидат по ошибке сборки всё же оказался в `inputs`, `ambiguous=true` и `confirmed=false` значат одно: в исполнитель он не передаётся. Это не второй способ прочитать тот же объект. Подтверждённый вход — `inputs`. Неподтверждённый показ для следа — `diagnostic`. Не выбранное правилом — `rejected`. Одно поле не означает «и посчитать, и только показать».

DuckDB по умолчанию показывает в `EXPLAIN` только физический план (`explain_output = physical_only`): дерево операторов, которое будут исполнять. `optimized_only` — другой вид того же запроса, не набор узлов исполнения. OpenLineage в `inputField` пишет колонки, которые пошли в выход, а не кандидатов, которых не взяли. Берём разделение «что исполнять» и «что показать»: `inputs` — исполняемое, `diagnostic` и `rejected` — нет. Отход: DuckDB и OpenLineage отвергнутый порядок и неподтверждённого кандидата в выдачу не кладут. Мы кладём их в `rejected` и `diagnostic`, потому что аудит спрашивает, почему строка не подтверждена. В `inputs` они от этого не становятся.

Правило строки одно — `select_primary`. `_groups`, `_ambiguous_primary` и оба `_primary` для входа метрики больше не решают. Расхождение `plugins/rules/ratios.py` названо в миграции: там первая bound-строка и нет фильтра stale.

`missing_input` — у нужного понятия нет свежей основной (`no_primary_binding` или только `stale_binding`). Вопрос `concept_unknown` или `absent_in_book` пишется в `needs_input`, как сегодня пишет `coverage_ratio`. Подтверждённых входов нет, `diagnostic` пуст.

### Неизменяемость и идентичность

План не меняют после построения. Новый факт — новый план, не правка старого.

W3C PROV называет сущностью вещь с фиксированными аспектами: сущность физическая, цифровая или концептуальная, аспекты фиксированы. Берём это: план — сущность разрешения, выбранные входы — то, из чего она получена (`wasDerivedFrom` в PROV связывает порождённую сущность с использованной). Отход: у PROV нет отношения «отвергнутый кандидат». `wasInvalidatedBy` означает, что сущность перестала быть текущей, а не что строка проиграла выбор. Отвергнутые альтернативы — отдельное поле, не перегрузка PROV.

Event Sourcing (Fowler) хранит изменения состоянием-журналом: по журналу видно, как состояние получилось, и состояние можно собрать заново прогоном событий. Берём вопрос аудита «как получилось это число» и запрет переписывать запись. Отход: журнал событий здесь не заводится. Прогон событий заново выполнил бы выбор, а его как раз нельзя повторять в потребителях. План — один снимок. Идентичность — хеш снимка, не номер в последовательности. Состояние «текущий выбор» рядом со снимком не хранится.

RFC 8785 (JCS) задаёт канонический JSON, чтобы хеш повторялся. Свойства объекта сортируются. Порядок элементов массива JCS менять запрещает: массив сканируется, объекты внутри сортируются, сам порядок массива сохраняется. `canonical_json` в `domain/book.py` устроен так же в этой части: `sort_keys=True` сортирует ключи и не сортирует списки. Отход от JCS: вторую канонизацию чисел по ECMAScript не вводим, в теле плана чисел нет. Отход от «массив не трогать»: `inputs`, `diagnostic`, `rejected`, `fallbacks`, `warnings` и `needs_input` для нас множества, а не последовательности. Перед хешем движок сортирует их сам, и только потом вызывает `canonical_json`. Иначе два одинаковых выбора в разном порядке списка дадут два хеша.

Порядок перед хешем, по возрастанию, отсутствующая строка — пустая:

| Список | Ключ |
|---|---|
| `inputs` | `concept`, `role`, `source`, `binding_key`, `row_key` |
| `diagnostic` | `concept`, `binding_key`, `row_key` |
| `rejected` | `reason`, `concept`, `binding_key`, `row_key` |
| `fallbacks` | `slot`, `replaced`, `chosen`, `warning_code` |
| `warnings` | `code`, затем пары `params` по имени |
| `needs_input` | `kind`, `reason`, `subject` |

Git хранит объект под контрольной суммой содержимого: ключ — хеш содержания, короткий вид — префикс этого же имени (`git rev-parse --short` сокращает имя объекта до уникального префикса). Берём пару «полный хеш и его префикс», а не два независимых идентификатора. Отход: Git в книге описывает SHA-1 и удлиняет короткий префикс, пока он не однозначен в базе объектов. У нас SHA-256, как у `catalog_version_for`, а `plan_id` фиксирован на 16 hex, как `catalog_version` и `build_key`. Полный дайджест остаётся на объекте домена, поэтому совпадение 16 hex не подменяет идентичность.

```text
content_sha256 = sha256(canonical_json(тело))
plan_id = content_sha256[:16]
```

Тело: `resolution_engine_version`, `metric_id`, `variant`, `variant_source`, `catalog_version`, `build_key`, `model_id`, `status`, `inputs`, `diagnostic`, `rejected`, `fallbacks`, `warnings`, `needs_input`, `shield`. Не входят: `plan_id`, `content_sha256`, `schema`, `semantic_model_version`, значения ячеек, флаги `graph_available`.

`resolution_engine_version` — константа движка, не версия HTTP. DuckDB `EXPLAIN (SQL)` прямо говорит: оптимизированный план может сильно отличаться от исходного запроса, например из‑за перестановки соединений или свёртки констант, а точное форматирование и порождённые алиасы не являются стабильным интерфейсом. OpenLineage кладёт в фасет `_producer` с версией производителя и `_schemaURL`. Берём версию алгоритма в хешируемое тело, чтобы смена правил выбора не выглядела тем же планом, что и прежний алгоритм на тех же строках. Отход: план FAS не сериализуется как SQL из `EXPLAIN (SQL)`. Это не SemVer публичного API и не URL производителя OpenLineage. Константу вводит PR движка. Пока алгоритм тот же, константа не растёт; вырос результат — хеш меняется и при прежней константе.

`content_sha256` живёт на объекте домена для идентичности и аудита. В публичную модель его пока не кладут: ни в `metricTrace`, ни в будущий контракт, пока этот контракт сам не решил иначе. `plan_id` в JSON `formula_origin` не кладётся, пока нет схемы аудита.

`catalog_version` не включает `interest_order` отдельным полем: `catalog_version_for` хеширует показатели. Исход порядка попадает в план через `fallbacks` и `rejected`. Два порядка, давшие один и тот же набор выбранных, диагностических и отвергнутых, получают один хеш. Это идентичность результата, не идентичность файла YAML.

## 3. Кто строит и кто читает

Строит одна функция домена, рабочее имя `resolve_metric_plan`, рядом с `resolve_semantic_inputs`. Она один раз вызывает те же функции, что сегодня вызывают оба прохода: `select_primary`, `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `shield_concepts`. Наружу потребителям эти функции для выбора входа метрики больше не торчат. Каталог она не копирует и не исполняет арифметику.

Почему домен, а не application. Контракт слоёв в `[tool.importlinter]`: `adapters`, затем `application`, затем `domain`. `finance_analysis.plugins` не импортирует адаптеры и application. Правила уже вызывают `coverage_ratio`. Если движок живёт в application, правило не сможет получить план, не нарушив lint-imports. Движок в домене это сохраняет.

Вызов снаружи — один раз на метрику и `build_key`. Для анализа его делает `Analyses` и передаёт тот же объект в расчёт, след и `origin_view`. Если запрошен только след, `metric_trace_view` вызывает ту же `resolve_metric_plan` один раз и передаёт план в `trace_metric`. Контекст полный: факты, `graph_links`, привязки, вариант, `interest_order`, `row_fallbacks`, `absent`, листы отчётности. `trace_metric`, `coverage_ratio`, `free_cash_flow` и `origin_view` движок не вызывают.

Щит FCFF решается здесь один раз. В план пишутся `shield.basis` и `shield.reason`. Если базис `interest_included` или `candidate`, подтверждённый `interest_paid` попадает в `inputs` с `source=paid_interest`. `free_cash_flow` получает эти входы и `_basis` не вызывает. Ветку базиса он не повторяет. Факты и `graph_links` у движка те же, что сегодня у `free_cash_flow`: без них щит не собрать, и отдельного «плана без графа» нет.

Потребители:

| Кто | Что читает | Чего больше не делает |
|---|---|---|
| Расчёт: `coverage_ratio`, `free_cash_flow`, затем `covenant_dscr` | `inputs` с `confirmed=true`, `fallbacks`, `warnings`, `status`, `needs_input`, для FCFF ещё `shield` | `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `_basis`, `_groups`, `_ambiguous_primary`. Своего плана не строит |
| След: `trace_metric`, `_step_for_resolved` | подтверждённые `inputs` и `diagnostic` | `resolve_semantic_inputs` и выбор привязки |
| Происхождение и цепь: `origin_view`, `FormulaOrigin`, `FormulaChain` | тот же экземпляр плана или его неизменяемый вид. Семена — подтверждённые `inputs`. Неподтверждённая строка в отчёте, как сегодня, берётся из `diagnostic` | второй вызов резолвера. `plan_id` в JSON `formula_origin` не пишется |
| Пояснение: `template_text` | `rejected.reason`, `diagnostic` и `warnings` | не выбирает строку. `narrate` по-прежнему не подставляет свои числа |
| Аудит: конверт `formula_origin` и `_primary` правил, когда речь о входе метрики | тот же план | свой поиск основной строки |

`lineage_completeness`, рёбра `excel:link` и три графа (`excel:`, `sem:`, `metric:`) остаются у следа. План их не заменяет. Схемы датасетов не сливаются: это уже запрещено `assert_graphs_not_collapsed`.

Та же граница у DuckDB: binder уже разрешил имена, физический план исполняется, к разбору запроса исполнение не возвращается. `EXPLAIN` показывает этот физический план и сам запрос не гоняет.

Spark `EXPLAIN EXTENDED` показывает четыре ступени: разобранный логический план, проанализированный, оптимизированный и физический. Проанализированный план уже подставил имена. Берём ступень, не конвейер: каталог — неразрешённое определение, план — привязанный результат для одной сборки, расчёт — исполнение. Отход: четыре плана не храним. Физический план Spark — операторы (`HashAggregate`, `Exchange`). Наш физический слой — `graph_links` и `cell_id`, он остаётся в следе. Отвергнутые альтернативы в дерево исполнения не входят: они лежат в `rejected` и `diagnostic`.

Что перестаёт быть вторым проходом:

- `coverage_ratio` и резолвер оба вызывают `dscr_denominator_plan`, `choose_one_of`, `confirm_paid_interest`, `interest_choice`;
- `free_cash_flow` и `shield_concepts` оба считают базис щита;
- `covenant_dscr` ещё раз вызывает `confirm_paid_interest`;
- `trace_metric` и `origin_view` по разу вызывают `resolve_semantic_inputs`;
- четыре определения «несколько основных».

`resolve_semantic_inputs` не становится вторым фасадом плана. Проекция в один кортеж `SemanticInput`, где неподтверждённый кандидат снова лежит рядом с входом, вернула бы два чтения. На шагах 2–4 старый вызов живёт только у того читателя, до которого шаг ещё не дошёл. Шаг 5 этот вызов удаляет.

### Хранение, журнал и запросы

План этих шагов — объект в процессе. Отдельной базы под него нет, и PostgreSQL в этот контур не возвращается.

С 0.4 FAS уже не хранит состояние в Postgres: `docs/design-v0.23.md` убрал Postgres, SQLAlchemy и Alembic. Запись идёт через `ObjectStorePort` (`application/ports.py`): локальный каталог или S3-совместимый MinIO. Wren читает Parquet оттуда же: `adapters/wren/query.py` при `wren_source = minio_file` отдаёт DuckDB источник `minio_file`, при локальном диске — `local_file`. Журнал книги — `application/journal.py`: события по номерам, запись `put_if_absent`, без своей СУБД. Результат анализа пишет Parquet и маркер `result.json` с `sha256` тем же `put_if_absent` (`application/analyses.py`). Коэффициент считает `Decimal` в `domain/metrics.py`. DuckDB суммы по Parquet не подменяет эту арифметику и не разрешает метрику.

Если позже план или аудит нужно сохранить или выбрать запросом, это тот же контур, не новая СУБД.

- Байты плана или строки Parquet пишутся через `put_if_absent`. Ключ содержит `content_sha256`. Повтор той же записи не создаёт второй объект. Условная запись MinIO `If-None-Match` не перезаписывает уже лежащий ключ: PUT проходит только если объект с таким ETag ещё не лежит. Для нового ключа по хешу объекта ещё нет; повтор с тем же ключом отвергается. Это и есть неизменяемость артефакта.
- Versioning бакета и Object Lock не включаем. Документация MinIO по retention: блокировка требует versioning, держит версию до истечения срока, а удаление без идентификатора версии оставляет delete marker. Это другой механизм, чем ключ по SHA-256. В текущем FAS его нет, и плану он не нужен.
- Срез по сохранённым планам, если он понадобится, читает DuckDB 2.0 (`pyproject.toml`, `duckdb==2.0.0`) через `read_parquet` по файлам в том же object store. DuckDB не становится системой записи. Источник правды — объект, положенный `put_if_absent`.
- Журнал решений книги не заменяется планом и никуда не переезжает. План не является лентой событий выбора.

## 4. Контракт и JSON Schema

Публичный API версионируется по SemVer 2.0.0. Мажор растёт, когда публичный контракт меняется несовместимо. Минор — когда добавление совместимо. Выпущенную версию не правят.

`meta_layer_graphs@2.0` (`domain/contracts/meta_layer_graphs.json`) описывает ответ следа. У корня `metricTrace` стоит `additionalProperties: false`. По справочнику JSON Schema такое значение отвергает имя, которого нет в `properties`. Свойство вне `required` можно опустить: поэтому схема 2.0 принимает тело без `graph_available`. Тело с новым именем схема 2.0 отвергает. Так PR 107 поднял схему с 1.0 до 2.0.

Решение ревью: `ResolvedMetricPlan` в `metricTrace` не публикуется. `meta_layer_graphs@2.0` не меняется. MAJOR этой схемы нет. Ответ следа остаётся годным для схемы 2.0: те же `concept`, `role`, `binding_key`, `row_key`, тот же `ambiguous_primary_binding`. Диагностический кандидат попадает в шаг следа как проекция поля `diagnostic`, без новых имён в JSON следа.

Будущий контракт плана отдельный: `$id` `https://fas.local/contracts/resolved_metric_plan@1.0.json`, `$schema` draft 2020-12, версия `1.0.0`. Это не схема следа и не этот PR. Файл схемы появится, когда план станет публичным документом. До того план — объект домена. `content_sha256` в эту публичную модель пока не входит. `formula_origin` схемой `meta_layer_graphs` не описан. `plan_id` попадёт в его JSON только вместе со схемой аудита. До схемы ключ не добавляется: внутри процесса `origin_view`, `FormulaOrigin` и `FormulaChain` получают тот же экземпляр плана или неизменяемый вид, и этого достаточно, чтобы не выбирать вход заново.

Закрытая схема плана тоже с `additionalProperties: false`. Новое имя в этом документе позже — MAJOR плана (`2.0.0`), не минор: клиент со схемой 1.0 новое имя отвергнет. Необязательное поле, которого нет в `required`, можно не присылать, но прислать неизвестное имя нельзя. `unevaluatedProperties` из того же справочника позволил бы расширять схему через `allOf`. Берём `additionalProperties: false`, как уже сделано у следа, чтобы расширение было явным мажором, а не тихим добавлением.

## 5. Миграция

Strangler Fig (Fowler): замена идёт швом, старое и новое живут вместе, переходный код удаляется, когда поведение переехало. Оптовая замена всех вызовов одним PR здесь не нужна и плохо проверяется. Шов уже есть: `resolve_semantic_inputs`.

Каждый PR маленький, сначала тест. На каждом шаге два утверждения: наблюдаемый результат тот же, и выбор не повторился. Второе проверяется так: план уже построен, `select_primary` подменён исключением, переключённый читатель не падает и не вызывает движок снова. Читатель, которого этот шаг ещё не переключил, подмену не проходит — он ещё на старом пути. Это не повод строить план внутри расчёта.

1. Типы и `resolve_metric_plan`. Снаружи никто не переключён. Тест: на фикстурах `tests/unit/test_semantic_input.py` подтверждённые `inputs` совпадают с сегодняшними не-ambiguous входами резолвера, `diagnostic` — с сегодняшним неоднозначным кандидатом минимального `binding_key`, `needs_input` — с остановкой `coverage_ratio`. Выбор вызывается только внутри движка.
2. `trace_metric` и `origin_view` принимают план и не вызывают резолвер. Шаги следа и семена `FormulaChain` те же. Неподтверждённая строка происхождения читается из `diagnostic`, не из `inputs`. Подмена `select_primary` после построения плана эти два читателя не ломает.
3. `coverage_ratio` и `free_cash_flow` принимают план. `free_cash_flow` не вызывает `_basis`: базис и причина уже в `shield`, входы щита уже в `inputs`. Своего плана функции не строят. Числа на синтетических книгах те же. Подмена выбора после построения плана их не ломает.
4. `covenant_dscr` и `_primary` правил читают план. В `plugins/rules/ratios.py` сегодня другое правило: `_primary` берёт первую bound-строку, если она ровно одна, stale не отфильтрован, минимальный `binding_key` не используется. `select_primary` берёт минимальный `binding_key` среди не-stale bound. Шаг переводит правило на план и не оставляет первый-в-списке как второй выбор. `plugins/rules/coverage.py` переводится тем же шагом: его `_primary` ходит в `_groups` и `_primaries`.
5. Удалить старые пути выбора у потребителей и переходный слой, если он ещё позволяет читателю выбрать самому. `resolve_semantic_inputs` снаружи больше не вход. Функции `select_primary`, `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `shield_concepts` остаются внутри движка.

Пунктир NCF в этих PR не переносится в план.

### Счётчики Packt и RVI не двигаются

Выбор входа не меняет статус привязки. Текущий инвариант fact-строк записан в `tests/contract/test_book_model_type.py`, словарь `_COUNTS`:

| Книга | bound | ambiguous | unknown | not_applicable |
|---|---:|---:|---:|---:|
| Packt | 11 | 2 | 80 | 4 |
| RVI | 11 | 6 | 212 | 9 |

Проверка каждого миграционного PR, который меняет код: этот контрактный тест и `golden_count` (`tests/unit/rule_inputs.py`) в `tests/unit/test_formulas.py`. Оба не двигаются. Счётчики из ранних абзацев `docs/design-v0.23.md` (Packt 9/2/82, RVI 10/6/213) — история, не текущий инвариант.

`golden_count` особенно важен на шаге 4: если первая bound-строка `ratios._primary` на Packt или RVI расходилась с `select_primary`, находки сдвинутся. Это отказ шага, не повод переписать ожидание. Снимок eval типа модели не переписывают. Auchan эти проверки не заменяют и в них не входят.

## 6. Что принято и какие риски остаются

Шесть пунктов ревью PR 108 закрыты так:

1. План не публикуется в `metricTrace`. `meta_layer_graphs@2.0` не меняется. Публичный контракт плана будет отдельным, не этим PR.
2. Раскол сохранён и разнесён по полям. `inputs` — только подтверждённые входы арифметики. `diagnostic` — неподтверждённый кандидат следа, минимальный `binding_key`. `rejected` — то, что правила не выбрали. Элемент с `confirmed=false` в арифметику не передаётся, даже если он по ошибке лежит в `inputs`.
3. Порядок PR: типы и `resolve_metric_plan`; след и `origin_view`; `coverage_ratio` и `free_cash_flow`; `covenant_dscr` и `_primary` правил; снятие старых путей. На каждом шаге тест результата и тест, что выбор не повторился. Расхождение `ratios._primary` названо выше.
4. `plan_id` — 16 hex, префикс полного SHA-256. `content_sha256` хранится на объекте домена и в публичную модель пока не входит. `resolution_engine_version` входит в хешируемое тело. Списки перед хешем сортируются: `canonical_json` ключи сортирует, массивы нет.
5. Базис щита FCFF решается один раз, в плане, с `basis` и `reason`. `free_cash_flow` получает готовые входы. Второго `_basis` нет. Контекст фактов и `graph_links` тот же, что у сегодняшнего расчёта.
6. `plan_id` не попадает в JSON `formula_origin`, пока нет схемы аудита. В процессе `origin_view`, `FormulaOrigin` и `FormulaChain` получают тот же план.

Риски реализации, не вопросы:

- Шаг 4 может вскрыть книгу, где первая bound-строка `ratios._primary` не совпала с не-stale минимумом `binding_key`. Ворота — неизменные `_COUNTS` и `golden_count`. Ожидание не переписывают.
- `confirm_paid_interest` пишет в переданный словарь `primaries`. Движок работает на копии, как `_with_confirmed_paid`. Список привязок вызывающего не меняется.
- Хеш разъедется, если в `params` попадёт не строка. В каноническое тело идут только строки.
- Пунктир NCF по-прежнему добавляет `trace_metric`, не план. Это не выбор входа метрики.
- Пока `content_sha256` не в публичном контракте, внешний аудитор видит только объект внутри процесса. Это сознательная отсрочка, не второй идентификатор.
- План, аудит и журнал не получают своей СУБД. Журнал книги остаётся `Journal` на `ObjectStorePort`. Сохранённый план, когда он понадобится, — объект по `content_sha256` через `put_if_absent` и, для среза, Parquet, который читает DuckDB. Versioning и Object Lock бакета не включаются.

## 7. Решения и источники

Каждая ссылка открыта при написании этого текста.

**Модель плана — результат, не каталог.** Взято у MetricFlow: определения метрик в YAML семантического графа, запрос компилируется в SQL (`--explain` / `--compile` показывает этот SQL, `--show-dataflow-plan` — dataflow-план). У LookML: модель описывает поля, генератор SQL строит запрос. У Cube: мера в кубе, SQL появляется в момент запроса. Зачем: каталог FAS уже есть (`FinancialModelCatalog`, `MetricExpression`); второй каталог продублировал бы правила. Отход: SQL этих систем не является общим неизменяемым объектом расчёта, следа и аудита.

- [About MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow)
- [MetricFlow commands](https://docs.getdbt.com/docs/build/metricflow-commands), флаги `--explain` и `--show-dataflow-plan`
- [What is LookML](https://cloud.google.com/looker/docs/what-is-lookml)
- [Cube, data modeling](https://cube.dev/docs/product/data-modeling/overview)

**Один план, исполнитель не выбирает. Три списка — три чтения.** Взято у DuckDB. Binder разрешает имена, logical planner строит дерево, генератор физического плана делает дерево `PhysicalOperator`, исполнение идёт по нему и к разбору не возвращается. `EXPLAIN` по умолчанию (`explain_output = physical_only`) показывает это дерево и запрос не выполняет. `optimized_only` — другой вид, не узлы исполнения. У Spark `EXPLAIN EXTENDED`: разобранный, проанализированный, оптимизированный и физический планы. Зачем: `inputs` — то, что можно считать; `diagnostic` — неподтверждённый показ для следа; `rejected` — что правило не выбрало. Один список с `confirmed=false` читался бы и как вход, и как диагноз. Отход: DuckDB отвергнутые порядки соединений в физический план не кладёт; мы храним их в `rejected` и `diagnostic`, но не в `inputs`. Четыре ступени Spark не храним. Физические операторы Spark и DuckDB не путаем с `graph_links`. Коэффициент считает `Decimal`, не оператор DuckDB.

- [DuckDB internals](https://duckdb.org/docs/2.0/internals/overview.html)
- [DuckDB EXPLAIN](https://duckdb.org/docs/2.0/guides/meta/explain.html)
- [DuckDB profiling](https://duckdb.org/docs/2.0/sql/statements/profiling.html) — `EXPLAIN` не исполняет, `EXPLAIN ANALYZE` исполняет
- [Spark SQL: EXPLAIN](https://spark.apache.org/docs/latest/sql-ref-syntax-qry-explain.html)

**Неизменяемость, полный хеш и короткий префикс.** Фиксированные аспекты сущности — PROV. Запись, которую не переписывают, — Event Sourcing. Git идентифицирует объект контрольной суммой содержания; короткий вид — префикс того же имени (`git rev-parse --short`). JCS сортирует ключи объектов и запрещает менять порядок элементов массива. Зачем: `content_sha256` — идентичность, `plan_id` — первые 16 hex того же дайджеста, не второй хеш. `resolution_engine_version` входит в тело, потому что DuckDB `EXPLAIN (SQL)` предупреждает: оптимизированный план может сильно отличаться от исходного запроса, а форматирование и порождённые алиасы не стабильный интерфейс. OpenLineage пишет версию производителя в `_producer`. Списки входов перед `canonical_json` сортируются: иначе порядок массива меняет хеш, хотя JCS сам массивы не сортирует. Отход: не журнал событий; план не сериализуется как SQL из `EXPLAIN (SQL)`; не SHA-1 и не удлиняемый префикс Git; не числовая канонизация JCS; SMV и значения ячеек в хеш не входят; `content_sha256` пока не в публичной модели.

- [PROV-DM](https://www.w3.org/TR/prov-dm/), разделы 2.1.1 и 5.1.1 (Entity), 5.2 (wasDerivedFrom)
- [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785), правило сортировки: порядок элементов массива не менять
- [Git objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects) — ключ есть контрольная сумма содержания
- [git rev-parse](https://git-scm.com/docs/git-rev-parse) — `--short` сокращает имя объекта до префикса
- [DuckDB profiling](https://duckdb.org/docs/2.0/sql/statements/profiling.html) — `EXPLAIN (SQL)`: оптимизированный план не стабильный интерфейс
- [Column Level Lineage Dataset Facet](https://openlineage.io/docs/spec/facets/dataset-facets/column_lineage_facet/) — `_producer` с версией и `_schemaURL`

**Происхождение.** OpenLineage пишет в фасет, какие входы питают выход. Потребитель не достраивает рёбра декартовым произведением общих списков. Фасет колонок перечисляет наблюдённые `inputField`. Фасет lineage задания, если он есть, главнее общего списка входов и выходов. PROV связывает порождённое с использованным. Зачем: след и аудит читают входы плана и не собирают их из каталога. Отход: OpenLineage описывает наблюдение уже выполненной работы и не отдаёт объект, по которому работу ещё надо выполнить. Отвергнутых входов в фасете нет.

- [Column Level Lineage Dataset Facet](https://openlineage.io/docs/spec/facets/dataset-facets/column_lineage_facet/)
- [Lineage Job Facet](https://openlineage.io/docs/spec/facets/job-facets/lineage/)
- [PROV-DM](https://www.w3.org/TR/prov-dm/)

**Пояснение с отвергнутыми альтернативами.** `EXPLAIN` DuckDB и `--explain` MetricFlow показывают выбранный план или SQL, не список проигравших. OpenLineage и PROV тоже фиксируют использованное. Зачем нам поле `rejected`: вопрос продукта — почему взят этот вход и почему не соседний. Это не поиск дешёвого соединения, поэтому причины закрытые (`not_selected_one_of`, `interest_order_skipped`, `not_min_binding_key`, `debt_service_present`, `shield_not_applied`), а не стоимости оптимизатора. Пояснение печатает эти причины через `template_text` и само не выбирает.

- [DuckDB EXPLAIN](https://duckdb.org/docs/2.0/guides/meta/explain.html)
- [MetricFlow commands](https://docs.getdbt.com/docs/build/metricflow-commands)

**Хранение и запросы — тот стек, который уже есть.** MinIO пишет объект условно: `If-None-Match` не даёт затереть уже лежащий ключ. DuckDB читает Parquet (`read_parquet`), в том числе каталогом и по glob, и не обязан копировать файл в свою таблицу: вид над `read_parquet` оставляет данные в файле. Зачем: журнал книги уже `put_if_absent` на `ObjectStorePort`, результаты анализа уже Parquet с `sha256`, Wren уже читает этот Parquet через `minio_file`. План, если его сохранят, идёт тем же путём, ключ содержит `content_sha256`. Срез, если он понадобится, — DuckDB по этому Parquet. Отход: Object Lock и versioning бакета не берём. У MinIO блокировка — WORM на версию объекта, ей нужен versioning, а удаление без версии оставляет delete marker. Неизменяемость плана — новый ключ на каждый хеш и отказ перезаписи, не срок удержания.

- [MinIO: conditional writes](https://www.min.io/blog/leading-the-way-minios-conditional-write-feature-for-modern-data-workloads) — `If-Match` и `If-None-Match`
- [MinIO: Object Locking and Immutability](https://www.min.io/docs/minio/linux/administration/object-management/object-retention.html) — WORM и versioning; в план не берём
- [DuckDB: Parquet](https://duckdb.org/docs/2.0/data/parquet/overview.html) — `read_parquet`, вид над файлом

**Версия контракта.** SemVer: несовместимое изменение публичного API — мажор. JSON Schema: `additionalProperties: false` отвергает лишнее имя, свойство вне `required` можно опустить. Зачем: план не вшивается в `metricTrace`, `meta_layer_graphs@2.0` не меняется, MAJOR этой схемы нет. Будущий документ плана — отдельная схема `resolved_metric_plan@1.0`. `plan_id` не появляется в JSON `formula_origin`, пока нет схемы аудита. Отход от `unevaluatedProperties`: расширение плана должно быть видно мажором, как уже сделано для следа в 2.0.

- [Semantic Versioning 2.0.0](https://semver.org/)
- [JSON Schema: object](https://json-schema.org/understanding-json-schema/reference/object)

**Аудит.** Берём у Event Sourcing сохранённую причину состояния, у OpenLineage — запрет собирать рёбра заново. Аудит читает семена плана в `FormulaOrigin` и `FormulaChain`. Отход тот же: один снимок, не лента событий выбора.

**Миграция.** Strangler Fig: короткие шаги, старый вызов живёт, пока тест не перевёл читателя, переходный код удаляется. Зачем: инвариант «одни строки» уже есть как сравнение двух проходов; его переносят на один объект, не переписывая коэффициенты. Отход: фига здесь не новый продукт рядом со старым сервисом, а один процесс и пять PR. Счётчики Packt и RVI — ворота, что поведение привязок не уехало.

- [Strangler Fig](https://martinfowler.com/bliki/StranglerFigApplication.html)

## Файлы, с которыми сверялся текст

- `src/finance_analysis/domain/semantic_input.py` — `resolve_semantic_inputs`, `SemanticInput`, `FormulaOrigin`, `FormulaChain`, `lineage_completeness`
- `src/finance_analysis/domain/binding_resolution.py` — `declared_concept`, `select_primary`
- `src/finance_analysis/domain/metrics.py` — `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `coverage_ratio`, `_primaries`, `_groups`
- `src/finance_analysis/domain/free_cash_flow.py` — `shield_concepts`, `_basis`, `_ambiguous_primary`, `free_cash_flow`
- `src/finance_analysis/domain/graphs.py` — `trace_metric`, `_step_for_resolved`, `check_metric_physical_trace`
- `src/finance_analysis/domain/formula_origin.py` — `origin_view`
- `src/finance_analysis/domain/covenant.py` — `covenant_dscr`, `select_ratio`
- `src/finance_analysis/domain/financial_catalog.py` — `catalog_version_for`
- `src/finance_analysis/domain/book.py` — `canonical_json`
- `src/finance_analysis/domain/contracts/meta_layer_graphs.json`
- `src/finance_analysis/application/analyses.py` — расчёт, `_formula_origin`, Parquet результата и `put_if_absent`
- `src/finance_analysis/application/journal.py` — журнал книги на object store
- `src/finance_analysis/application/ports.py` — `ObjectStorePort`
- `src/finance_analysis/adapters/wren/query.py` — DuckDB, `minio_file` и `local_file`
- `src/finance_analysis/application/service.py` — `metric_trace_view`
- `src/finance_analysis/application/explain.py`
- `src/finance_analysis/plugins/rules/coverage.py`, `plugins/rules/ratios.py`
- `tests/unit/test_semantic_input.py`
- `tests/contract/test_book_model_type.py`
- `docs/semantic-model-version.md`, `docs/meta-layer-graphs.md`, `docs/design-v0.23.md` — с 0.4 хранение без Postgres
- `pyproject.toml`, контракт `[tool.importlinter]`
