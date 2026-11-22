# Неизменяемый план разрешения метрики

Снято с `main` `b9e91b4` (слияние PR 107). Кода этот документ не меняет.

После единого резолвера в `domain/semantic_input.py` следующий шаг — одно семантическое исполнение метрики:

```text
каталог → движок разрешения → неизменяемый Resolved Metric Plan → расчёт
```

Тот же план читают след, пояснение и аудит. Расчёт, след, пояснение и аудит не выбирают вход заново. План — результат разрешения для одной метрики одной сборки, не второй каталог правил.

Цели: число совпадает с происхождением; видно, почему взят вход; видны отвергнутые варианты и причина; прогон воспроизводим; у плана есть версия и след для аудита.

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
| `schema` | `str` | `resolved_metric_plan@1.0`. Конверт контракта, не часть хеша |
| `plan_id` | `str` | 16 hex, см. ниже. В хешируемое тело не входит |
| `metric_id` | `str` | показатель |
| `variant` | `str \| None` | выбранный вариант (`pf`, `housing`, …) или `None`, если сработала база или формула без варианта |
| `variant_source` | `str` | как сейчас у резолвера: `variant:…`, `base:…`, `formula` |
| `catalog_version` | `str \| None` | `FinancialModelCatalog.version`, тот же id, что след уже пишет в `catalog_version`. Считает `catalog_version_for`: sha256 канонического JSON показателей, 16 hex |
| `semantic_model_version` | `str \| None` | SMV из `docs/semantic-model-version.md`. Записывается для воспроизводимости окружения. В хеш плана не входит: SMV меняется от правил и глоссария, которые выбор строки не делают |
| `build_key` | `str \| None` | id сборки книги. Отдельного `build_id` в коде нет |
| `model_id` | `str \| None` | книга |
| `status` | `str` | статус разрешения, не статус арифметики: `resolved`, `needs_input`, `missing_input` |
| `inputs` | `tuple[ResolvedInput, …]` | фактические входы |
| `rejected` | `tuple[RejectedAlternative, …]` | отвергнутые альтернативы |
| `fallbacks` | `tuple[AppliedFallback, …]` | применённые замены |
| `warnings` | `tuple[PlanWarning, …]` | предупреждения выбора (`interest_basis_fallback`, `icr_numerator`) |
| `needs_input` | `tuple[NeedsInput, …]` | вопросы выбора. Пусто, если их нет |

`ResolvedInput`: `concept`, `role` (`all_of` \| `one_of`), `source` (`formula`, `variant:…`, `base:…`, `fallback`, `paid_interest`), `binding_key`, `row_key`, `missing` (`no_primary_binding` \| `stale_binding` \| `None`), `ambiguous: bool`, `confirmed: bool`.

`RejectedAlternative`: `concept`, `binding_key \| None`, `row_key \| None`, `reason`. Причины закрытым списком: `not_selected_one_of`, `interest_order_skipped`, `not_min_binding_key`, `debt_service_present`, `shield_not_applied`.

`AppliedFallback`: `slot` (имя слота `interest_order`: `pf`, `icr`, `icr_ebit`, `corporate_covenant`, …), `replaced`, `chosen`, `warning_code \| None`.

`PlanWarning`: `code`, `params` как кортеж пар строк, чтобы канонический JSON был стабилен.

`NeedsInput`: `kind` (`concept`), `reason` (`ambiguous` \| `concept_unknown` \| `absent_in_book`), `subject`.

В план не входят значения ячеек, окно периодов, масштаб и `lineage_completeness`. Это исполнение и физический граф. PostgreSQL сначала строит план, исполнитель его выполняет; `EXPLAIN` без `ANALYZE` показывает выбранный план, `EXPLAIN ANALYZE` добавляет фактические времена и числа строк уже после исполнения. Число коэффициента и `scale_unconfirmed` остаются результатом расчёта. Отход от планировщика: мы не ищем самый дешёвый оператор. Выбор здесь семантический.

### Неоднозначность

Оба факта живут в одном плане. Потребитель их не вычисляет.

Несколько свежих bound-основных одного понятия, которое входит в вход метрики:

- `status = needs_input`;
- `needs_input` содержит `{kind: concept, reason: ambiguous, subject: <понятие>}`;
- в `inputs` кандидат с минимальным `binding_key`, `ambiguous=true`, `confirmed=false`, `source` тот, который дал резолвер;
- остальные такие строки — в `rejected` с `reason: not_min_binding_key`;
- след по-прежнему ставит `integrity.reason = ambiguous_primary_binding` по этому кандидату и не считает его подтверждённым входом происхождения (`confirmed: false`).

Расчёт при `status != resolved` число не считает и возвращает тот же `needs_input`, который уже лежит в плане. Это сохраняет нынешний раскол «расчёт молчит, след показывает кандидата», но раскол записан один раз. Правило строки — `select_primary`. `_groups`, `_ambiguous_primary` и оба `_primary` в правилах для входа метрики больше не решают.

`missing_input` — у нужного понятия нет свежей основной (`no_primary_binding` или только `stale_binding`). Вопрос `concept_unknown` или `absent_in_book` пишется в `needs_input`, как сегодня пишет `coverage_ratio`.

### Неизменяемость и идентичность

План не меняют после построения. Новый факт — новый план, не правка старого.

W3C PROV называет сущностью вещь с фиксированными аспектами: сущность физическая, цифровая или концептуальная, аспекты фиксированы. Берём это: план — сущность разрешения, выбранные входы — то, из чего она получена (`wasDerivedFrom` в PROV связывает порождённую сущность с использованной). Отход: у PROV нет отношения «отвергнутый кандидат». `wasInvalidatedBy` означает, что сущность перестала быть текущей, а не что строка проиграла выбор. Отвергнутые альтернативы — отдельное поле, не перегрузка PROV.

Event Sourcing (Fowler) хранит изменения состоянием-журналом: по журналу видно, как состояние получилось, и состояние можно собрать заново прогоном событий. Берём вопрос аудита «как получилось это число» и запрет переписывать запись. Отход: журнал событий здесь не заводится. Прогон событий заново выполнил бы выбор, а его как раз нельзя повторять в потребителях. План — один снимок. Идентичность — хеш снимка, не номер в последовательности. Состояние «текущий выбор» рядом со снимком не хранится.

RFC 8785 (JCS) задаёт канонический JSON, чтобы хеш повторялся. Отход: в сервисе уже есть `canonical_json` в `domain/book.py` (`sort_keys`, разделители `,` и `:`). Им считается `catalog_version_for`. Вторую канонизацию не вводим. JCS ещё нормирует числа по ECMAScript; в теле плана чисел нет, только строки, логические значения и списки. Появится число с плавающей точкой — решение о JCS открывается снова.

```text
plan_id = sha256(canonical_json(тело))[:16]
```

Тело: `metric_id`, `variant`, `variant_source`, `catalog_version`, `build_key`, `model_id`, `status`, `inputs`, `rejected`, `fallbacks`, `warnings`, `needs_input`. Не входят: `plan_id`, `schema`, `semantic_model_version`, значения ячеек, флаги `graph_available`.

Ширина 16 hex — как у `catalog_version` и `build_key`. Это рекомендация, её можно сменить, пока плана нет в публичном ответе (вопрос 4).

`catalog_version` не включает `interest_order` отдельным полем: `catalog_version_for` хеширует показатели. Исход порядка попадает в план через `fallbacks` и `rejected`. Два порядка, давшие один и тот же набор выбранных и отвергнутых, получают один `plan_id`. Это идентичность результата, не идентичность файла YAML.

## 3. Кто строит и кто читает

Строит одна функция домена, рабочее имя `resolve_metric_plan`, рядом с `resolve_semantic_inputs`. Она один раз вызывает те же функции, что сегодня вызывают оба прохода: `select_primary`, `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `shield_concepts`. Наружу потребителям эти функции для выбора входа метрики больше не торчат. Каталог она не копирует и не исполняет арифметику.

Почему домен, а не application. Контракт слоёв в `[tool.importlinter]`: `adapters`, затем `application`, затем `domain`. `finance_analysis.plugins` не импортирует адаптеры и application. Правила уже вызывают `coverage_ratio`. Если движок живёт в application, правило не сможет получить план, не нарушив lint-imports. Движок в домене это сохраняет.

Вызов снаружи — один раз на метрику анализа, из `Analyses`, с теми же аргументами, что сегодня уходят в расчёт и в `origin_view`: выражения, вариант, `interest_order`, `row_fallbacks`, `absent`, привязки этой `build_key`, факты, ссылки, листы отчётности. След (`metric_trace_view`) получает уже построенный план или строит его той же функцией, если анализа не было. Второй движок не появляется.

Потребители:

| Кто | Что читает | Чего больше не делает |
|---|---|---|
| Расчёт: `coverage_ratio`, `free_cash_flow`, затем `covenant_dscr` | `inputs`, `fallbacks`, `warnings`, `status`, `needs_input` | `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `_basis` как второй выбор, `_groups`, `_ambiguous_primary` |
| След: `trace_metric`, `_step_for_resolved` | `inputs` и флаг `ambiguous` | `resolve_semantic_inputs` |
| Происхождение и цепь: `origin_view`, `FormulaOrigin`, `FormulaChain` | те же `inputs` как семена | второй вызов резолвера |
| Пояснение: `template_text` | `reason` и `warnings` плана, если фраза про выбор входа | не выбирает строку. `narrate` по-прежнему не подставляет свои числа |
| Аудит: конверт `formula_origin` и `_primary` правил покрытия и коэффициентов, когда речь о входе метрики | план | свой поиск основной строки для того же понятия |

`lineage_completeness`, рёбра `excel:link` и три графа (`excel:`, `sem:`, `metric:`) остаются у следа. План их не заменяет. Схемы датасетов не сливаются: это уже запрещено `assert_graphs_not_collapsed`.

Spark `EXPLAIN EXTENDED` показывает четыре ступени: разобранный логический план, проанализированный, оптимизированный и физический. Проанализированный план уже подставил имена. Берём ступень, не конвейер: каталог — неразрешённое определение, план — привязанный результат для одной сборки, расчёт — исполнение. Отход: четыре плана не храним. Физический план Spark — операторы (`HashAggregate`, `Exchange`). Наш физический слой — `graph_links` и `cell_id`, он остаётся в следе.

PostgreSQL: планировщик перебирает пути, выбирает один и строит дерево плана для исполнителя. Исполнитель план заново не составляет. `EXPLAIN` показывает выбранный план. Берём границу «один план, исполнитель не выбирает». Отход записан в разделе про отвергнутые альтернативы: планировщик отвергнутые пути в дерево исполнителя не кладёт.

Что перестаёт быть вторым проходом:

- `coverage_ratio` и резолвер оба вызывают `dscr_denominator_plan`, `choose_one_of`, `confirm_paid_interest`, `interest_choice`;
- `free_cash_flow` и `shield_concepts` оба считают базис щита;
- `covenant_dscr` ещё раз вызывает `confirm_paid_interest`;
- `trace_metric` и `origin_view` по разу вызывают `resolve_semantic_inputs`;
- четыре определения «несколько основных».

`resolve_semantic_inputs` после переключения становится чтением плана в кортеж `SemanticInput`, чтобы старые тесты следа не выдумывали второй выбор. Когда читателей кортежа не останется, функция уходит. Это не второй движок.

## 4. Контракт и JSON Schema

Публичный API версионируется по SemVer 2.0.0. Мажор растёт, когда публичный контракт меняется несовместимо. Минор — когда добавление совместимо. Выпущенную версию не правят.

`meta_layer_graphs@2.0` (`domain/contracts/meta_layer_graphs.json`) описывает ответ следа. У корня `metricTrace` стоит `additionalProperties: false`. По справочнику JSON Schema такое значение отвергает имя, которого нет в `properties`. Свойство вне `required` можно опустить: поэтому схема 2.0 принимает тело без `graph_available`. Тело с новым именем схема 2.0 отвергает. Так PR 107 поднял схему с 1.0 до 2.0.

Следствие: поля плана (`plan_id`, `rejected`, `fallbacks`) в ответ `metricTrace` не кладутся. Иначе это MAJOR, схема `meta_layer_graphs@3.0`. Пока план не вшит в след, MAJOR для `meta_layer_graphs` не нужен. Ответ следа остаётся годным для схемы 2.0. След — проекция выбранных входов: те же `concept`, `role`, `binding_key`, `row_key`, тот же `ambiguous_primary_binding`.

Отдельный документ, когда он станет публичным: `$id` `https://fas.local/contracts/resolved_metric_plan@1.0.json`, `$schema` draft 2020-12, как у графов. Версия контракта `1.0.0`. Файл схемы — отдельный PR, не этот. До публикации план — объект домена. `formula_origin` схемой `meta_layer_graphs` не описан и сегодня. Новое поле в его JSON — не MAJOR 2.0, но это новый публичный ключ без схемы. Пока ключ не добавляется (вопрос 6).

Закрытая схема плана тоже с `additionalProperties: false`. Новое имя в этом документе позже — MAJOR плана (`2.0.0`), не минор: клиент со схемой 1.0 новое имя отвергнет. Необязательное поле, которого нет в `required`, можно не присылать, но прислать неизвестное имя нельзя. `unevaluatedProperties` из того же справочника позволил бы расширять схему через `allOf`. Берём `additionalProperties: false`, как уже сделано у следа, чтобы расширение было явным мажором, а не тихим добавлением.

## 5. Миграция

Strangler Fig (Fowler): замена идёт швом, старое и новое живут вместе, переходный код удаляется, когда поведение переехало. Оптовая замена всех вызовов одним PR здесь не нужна и плохо проверяется. Шов уже есть: `resolve_semantic_inputs`.

Каждый PR маленький, сначала тест. Инвариант один: расчёт и происхождение читают один план и называют одни строки.

1. Типы и `resolve_metric_plan`. Снаружи никто не переключён. Тест: на тех же книжных фикстурах, что `tests/unit/test_semantic_input.py`, план даёт те же понятия, роли, `source`, `binding_key` и `row_key`, что `resolve_semantic_inputs`, и те же `needs_input`, что `coverage_ratio`, когда расчёт останавливается.
2. `trace_metric` и `origin_view` принимают план и не вызывают резолвер. Тест инварианта: один план подан в след, в `origin_view` и в расчёт. Понятия и `binding_key` шагов следа, семян `FormulaChain` и входов расчёта совпадают. После построения плана подмена `select_primary` исключением не ломает эти три вызова. Так проверяется, что выбор не повторился.
3. `coverage_ratio` и `free_cash_flow` читают план. Пока аргумента нет, функция один раз строит план сама и считает по нему. Это переходный шов, не второй контракт. Тест шага 2 остаётся зелёным, числа на синтетических книгах те же.
4. `covenant_dscr` и `_primary` в `plugins/rules/coverage.py` и `plugins/rules/ratios.py` для входа метрики читают план. До этого PR они ещё выбирают сами. Это сознательная очередь, не забытый вызов.
5. Удалить переходный аргумент «плана нет — построй внутри», публичный выбор из расчёта и прямой вызов `resolve_semantic_inputs` из следа и происхождения. Функции `select_primary`, `choose_one_of`, `dscr_denominator_plan`, `interest_choice`, `confirm_paid_interest`, `shield_concepts` остаются внутри движка.

Пунктир NCF в этих PR не переносится в план.

### Счётчики Packt и RVI не двигаются

Выбор входа не меняет статус привязки. Текущий инвариант fact-строк записан в `tests/contract/test_book_model_type.py`, словарь `_COUNTS`:

| Книга | bound | ambiguous | unknown | not_applicable |
|---|---:|---:|---:|---:|
| Packt | 11 | 2 | 80 | 4 |
| RVI | 11 | 6 | 212 | 9 |

Проверка миграционного PR: этот контрактный тест. Счётчики из ранних абзацев `docs/design-v0.23.md` (Packt 9/2/82, RVI 10/6/213) — история, не текущий инвариант.

Находки формул на тех же книгах держит `golden_count` (`tests/unit/rule_inputs.py`) в `tests/unit/test_formulas.py`. Их тоже не двигают: план меняет, кто читает уже выбранные семена, а не разметку формул. Снимок eval типа модели не переписывают. Если счётчик сдвинулся, это отказ миграции, не повод обновить ожидание. Auchan эти проверки не заменяют и в них не входят.

## 6. Риски и вопросы

Риски, которые не требуют отдельного решения, но их легко пропустить:

- Переходный шов «расчёт сам строит план» снова два входа, если шаг 5 не сделать. Тест с подменой `select_primary` обязателен и на шаге 3.
- `confirm_paid_interest` сегодня пишет в словарь `primaries`. Движок работает на копии, как уже делает `_with_confirmed_paid`. Список привязок вызывающего не меняется.
- Щит FCFF зависит от фактов и `graph_links`. План, собранный без них, потеряет `interest_paid`. В движок идут те же аргументы, что в `free_cash_flow`.
- `catalog_version` не фиксирует `interest_order`. Фиксирует тело плана. Это записано в модели нарочно.
- Хеш разъедется, если в `params` предупреждения попадёт нестроковое значение. В каноническое тело идут только строки.

Вопросы к решению. Рекомендация указана, пока ответа нет, документ держит её.

1. Публиковать план в HTTP-ответе следа сразу? Это MAJOR `meta_layer_graphs@3.0`, потому что закрытая схема 2.0 новое имя отвергнет. Рекомендация: не публиковать, схему 2.0 не менять, план остаётся объектом домена, пока не назван потребитель документа.
2. При нескольких основных сохранять ли нынешний раскол внутри плана (расчёт не считает, след показывает минимальный `binding_key` как неподтверждённый)? Рекомендация: сохранить, иначе сдвинется текст следа и тесты PR 107 без выигрыша в числе.
3. `covenant_dscr` и правила в первый переключающий PR или после `coverage_ratio` и `free_cash_flow`? Рекомендация: тип один, ковенант и правила — шаг 4. Раньше их переключать нельзя: они должны читать уже принятый план расчёта.
4. `plan_id` — 16 hex или полный sha256? Рекомендация: 16 hex, как `catalog_version` и `build_key`.
5. Базис щита FCFF остаётся частью плана, а не вторым проходом `free_cash_flow`? Рекомендация: да, это выбор входа `interest_paid`, не арифметика `(1 − t)`.
6. Класть ли `plan_id` в JSON `formula_origin`, у которого нет схемы? Рекомендация: нет, пока нет своей схемы. В одном процессе аудит и расчёт делят объект.

## 7. Решения и источники

Каждая ссылка открыта при написании этого текста.

**Модель плана — результат, не каталог.** Взято у MetricFlow: определения метрик в YAML семантического графа, запрос компилируется в SQL (`--explain` / `--compile` показывает этот SQL, `--show-dataflow-plan` — dataflow-план). У LookML: модель описывает поля, генератор SQL строит запрос. У Cube: мера в кубе, SQL появляется в момент запроса. Зачем: каталог FAS уже есть (`FinancialModelCatalog`, `MetricExpression`); второй каталог продублировал бы правила. Отход: SQL этих систем не является общим неизменяемым объектом расчёта, следа и аудита.

- [About MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow)
- [MetricFlow commands](https://docs.getdbt.com/docs/build/metricflow-commands), флаги `--explain` и `--show-dataflow-plan`
- [What is LookML](https://cloud.google.com/looker/docs/what-is-lookml)
- [Cube, data modeling](https://cube.dev/docs/product/data-modeling/overview)

**Один план, исполнитель не выбирает. Логический вид и привязанный план.** Взято у планировщика PostgreSQL: он выбирает один путь и отдаёт дерево исполнителя. `EXPLAIN` показывает этот план. У Spark `EXPLAIN EXTENDED`: разобранный, проанализированный, оптимизированный и физический планы; проанализированный уже разрешает имена. Зачем: сегодня расчёт и резолвер оба выбирают. Отход: отвергнутые пути PostgreSQL в план исполнителя не входят; четыре ступени Spark не храним; физические операторы Spark не путаем с `graph_links`.

- [PostgreSQL: Planner/Optimizer](https://www.postgresql.org/docs/current/planner-optimizer.html)
- [PostgreSQL: EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
- [Spark SQL: EXPLAIN](https://spark.apache.org/docs/latest/sql-ref-syntax-qry-explain.html)

**Неизменяемость и хеш.** Фиксированные аспекты сущности — PROV. Вопрос «как получилось» без переписывания записи — Event Sourcing. Канонический JSON для повторяемого хеша — тема RFC 8785. Зачем: потребители не должны собрать другой вход из тех же привязок. Отход: не журнал событий и не прогон выбора заново; не JCS, а существующий `canonical_json`; SMV и значения ячеек в хеш не входят.

- [PROV-DM](https://www.w3.org/TR/prov-dm/), разделы 2.1.1 и 5.1.1 (Entity), 5.2 (wasDerivedFrom)
- [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [RFC 8785, JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)

**Происхождение.** OpenLineage пишет в фасет, какие входы питают выход. Потребитель не достраивает рёбра декартовым произведением общих списков. Фасет колонок перечисляет наблюдённые `inputField`. Фасет lineage задания, если он есть, главнее общего списка входов и выходов. PROV связывает порождённое с использованным. Зачем: след и аудит читают входы плана и не собирают их из каталога. Отход: OpenLineage описывает наблюдение уже выполненной работы и не отдаёт объект, по которому работу ещё надо выполнить. Отвергнутых входов в фасете нет.

- [Column Level Lineage Dataset Facet](https://openlineage.io/docs/spec/facets/dataset-facets/column_lineage_facet/)
- [Lineage Job Facet](https://openlineage.io/docs/spec/facets/job-facets/lineage/)
- [PROV-DM](https://www.w3.org/TR/prov-dm/)

**Пояснение с отвергнутыми альтернативами.** `EXPLAIN` PostgreSQL и `--explain` MetricFlow показывают выбранный план или SQL, не список проигравших. OpenLineage и PROV тоже фиксируют использованное. Зачем нам поле `rejected`: вопрос продукта — почему взят этот вход и почему не соседний. Это не поиск дешёвого соединения, поэтому причины закрытые (`not_selected_one_of`, `interest_order_skipped`, `not_min_binding_key`, `debt_service_present`, `shield_not_applied`), а не стоимости планировщика. Пояснение печатает эти причины через `template_text` и само не выбирает.

- [PostgreSQL: EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
- [MetricFlow commands](https://docs.getdbt.com/docs/build/metricflow-commands)

**Версия контракта.** SemVer: несовместимое изменение публичного API — мажор. JSON Schema: `additionalProperties: false` отвергает лишнее имя, свойство вне `required` можно опустить. Зачем: план не вшивается в `metricTrace`, MAJOR `meta_layer_graphs` не требуется. Своя схема с 1.0.0, когда документ станет публичным. Отход от `unevaluatedProperties`: расширение плана должно быть видно мажором, как уже сделано для следа в 2.0.

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
- `src/finance_analysis/application/analyses.py` — расчёт и `_formula_origin`
- `src/finance_analysis/application/service.py` — `metric_trace_view`
- `src/finance_analysis/application/explain.py`
- `src/finance_analysis/plugins/rules/coverage.py`, `plugins/rules/ratios.py`
- `tests/unit/test_semantic_input.py`
- `tests/contract/test_book_model_type.py`
- `docs/semantic-model-version.md`, `docs/meta-layer-graphs.md`
- `pyproject.toml`, контракт `[tool.importlinter]`
