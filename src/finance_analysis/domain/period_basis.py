"""Способ показа периода у fact-строки (§5.5.2).

У строки, которая не `ytd` и не `ltm`, способ показа — `period`.
`ytd` ставится по заголовку или по формуле этой же строки, которая
прибавляет предыдущую ячейку и сбрасывается в начале года. Явный заголовок
сильнее формулы: формула его не отменяет. Форма ряда основанием не служит.
`unknown` здесь не ставится: это обычный исход для строки без признака,
и каскад считает его сильнее `ytd`.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal

from finance_analysis.domain.glossary import label_features, label_scan

_YTD = ("нарастающим итогом", "накопленным итогом", "с начала года")
_LTM = ("last 12 months", "за 12 месяцев")
_LTM_WORD = re.compile(r"(?<!\w)ltm(?!\w)")
_GRAIN_MONTHS = {"year": 12, "model_year": 12, "half": 6, "half_year": 6, "quarter": 3, "month": 1}


def classify_period_basis(
    row: dict,
    *,
    calendar: dict | None,
    links: list[dict] | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> tuple[str, str]:
    """Возвращает способ показа и источник: `label`, `header`, `formula` или `default`.

    `row` — fact-строка. `calendar` сопоставляет `(axis_id, period_id)` с зерном,
    датами и текстом заголовка колонки.     `links` — рёбра графа формул. `series` — значения строки, чтобы заголовок
    колонки читался только там, где есть число. `facts` добавляет в карту
    ячейку введённого числа: у неё есть `cell_id`, но нет формулы.
    """

    label = str(row.get("label") or "")
    if _label_ltm(label):
        return "ltm", "label"
    row_header = _row_header(row)
    columns = _column_headers(series, calendar)
    # Согласованные колонки LTM сильнее заголовка раздела. Заголовок сильнее формулы.
    if _columns_agree(columns, _phrase_ltm):
        return "ltm", "header"
    if _header_ytd(row) or _columns_agree(columns, _phrase_ytd):
        return "ytd", "header"
    if _phrase_ltm(row_header):
        return "ltm", "header"
    if _label_forces_period(label):
        return "period", "default"
    if _ltm_formula(row, links, calendar, series, facts):
        return "ltm", "formula"
    if _ytd_formula(row, links, calendar, series, facts):
        return "ytd", "formula"
    return "period", "default"


def basis_of(binding: dict) -> tuple[str, str]:
    """Читает способ показа из `evidence` или из `evidence_json` привязки."""

    evidence = binding.get("evidence")
    if not isinstance(evidence, dict):
        raw = binding.get("evidence_json")
        if isinstance(raw, str) and raw:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = {}
            evidence = loaded if isinstance(loaded, dict) else {}
        else:
            evidence = {}
    return str(evidence.get("period_basis") or "period"), str(evidence.get("period_basis_source") or "")


def restate_series(totals: dict[tuple, Decimal], binding: dict, periods: list[dict], aligned: dict) -> dict[tuple, Decimal]:
    """Переводит нарастающий итог в значение за период.

    Вычитание делается только если способ показа поставлен по заголовку или
    по формуле этой же строки. В начале года ряд не вычитается из прошлого
    года: формула в этот момент сбрасывается. Если предыдущий период того же
    года пуст, текущий период из ряда убирается, а не вычитается из более
    раннего значения. Строка `ltm` и строка `period` возвращаются как есть.
    Ряд без такого источника не пересчитывается.
    """

    basis, source = basis_of(binding)
    if basis != "ytd" or source not in {"header", "formula"}:
        return totals
    result = dict(totals)
    by_axis: dict[str, list[dict]] = {}
    for period in periods:
        by_axis.setdefault(str(period.get("axis_id") or ""), []).append(period)
    for items in by_axis.values():
        ordered = sorted(items, key=lambda item: item.get("period_index") or 0)
        previous_year = None
        previous_raw = None
        previous_present = False
        for period in ordered:
            own = (period.get("axis_id"), period.get("period_id"))
            key = aligned.get(own, own)
            year = _year_of(period)
            present = key in totals
            same_year = year is not None and year == previous_year
            if present and same_year and previous_present and previous_raw is not None:
                result[key] = totals[key] - previous_raw
            elif present and same_year and not previous_present:
                result.pop(key, None)
            if year is not None:
                previous_year = year
            if present:
                previous_raw = totals[key]
                previous_present = True
            else:
                previous_raw = None
                previous_present = False
    return result


def keys_for_basis(keys: list, binding: dict) -> list:
    """Оставляет конец окна у строки `ltm`, чтобы четыре квартала не складывались."""

    if keys and basis_of(binding)[0] == "ltm":
        return [keys[-1]]
    return list(keys)


def grain_span(grain: str | None) -> int | None:
    """Длина одного периода в месяцах. Неизвестный grain длину не имеет."""

    return _GRAIN_MONTHS.get(str(grain or "").lower())


def covered_months(series: dict, calendar: dict | None) -> tuple[str | None, int]:
    """Возвращает зерно строки и число покрытых месяцев.

    Зерно одно на все периоды, где у строки есть значение. Смешанное зерно
    или отсутствие дат дают пустое зерно: такие строки шаг покрытия не сравнивает.
    Месяц считается по `period_start` и `period_end`, включая оба конца.
    """

    if not calendar:
        return None, 0
    grains: set[str] = set()
    months: set[tuple[int, int]] = set()
    for key in series:
        meta = calendar.get(key)
        if not meta:
            continue
        grain = str(meta.get("grain") or "").lower()
        if grain:
            grains.add(grain)
        start = _as_date(meta.get("period_start"))
        end = _as_date(meta.get("period_end"))
        if start is None or end is None or end < start:
            continue
        months |= _month_span(start, end)
    if len(grains) != 1 or not months:
        return None, 0
    return next(iter(grains)), len(months)


def _label_forces_period(label: str) -> bool:
    """Хвост «за квартал» или «за период» оставляет `period`. Формула его не отменяет.

    Хвост «за год» таким запретом не является: нарастающий итог по формуле
    при нём сохраняется.
    """

    feature = label_features(label).period
    if not feature or _phrase_ltm(feature):
        return False
    folded = label_scan(feature)
    tails = {label_scan(item) for item in ("за кв.", "за кв", "за квартал", "за период")}
    return folded in tails


def _label_ltm(label: str) -> bool:
    feature = label_features(label).period
    if feature and _phrase_ltm(feature):
        return True
    return _phrase_ltm(label)


def _phrase_ltm(text: str) -> bool:
    folded = label_scan(text)
    if any(phrase in folded for phrase in _LTM):
        return True
    return _LTM_WORD.search(folded) is not None


def _phrase_ytd(text: str) -> bool:
    """Фраза нарастающего итога заканчивает заголовок. Дальше допустимо только «за год».

    Скобки и слова «указан» или «указаны» перед фразой заголовок не отменяют.
    Продолжение вроде «проекта» фразу не включает.
    """

    folded = label_scan(text)
    for phrase in _YTD:
        start = 0
        while True:
            index = folded.find(phrase, start)
            if index < 0:
                break
            before = index == 0 or not folded[index - 1].isalnum()
            after = _ytd_tail(folded[index + len(phrase) :])
            if before and after in {"", "за год"}:
                return True
            start = index + len(phrase)
    return False


def _ytd_tail(text: str) -> str:
    """Хвост заголовка без скобок и знаков препинания."""

    cleaned = re.sub(r"[()\[\]«»\"'.,;:]", "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def apply_block_titles(rows: list[dict]) -> None:
    """Пишет заголовок блока в путь fact-строк под ним до следующего заголовка.

    Заголовок стоит отдельной строкой: объединённая ячейка над блоком, текст
    в столбце A или B, первые строки листа. Если в нём есть фраза нарастающего
    итога, она доходит до способа показа каждой fact-строки ниже. Следующий
    заголовок блока эту фразу закрывает. Привязка по `binding_key` не меняется.
    """

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("sheet") or ""), []).append(row)
    for sheet_rows in grouped.values():
        sheet_rows.sort(key=lambda item: int(item.get("row_num") or item.get("row") or 0))
        current: str | None = None
        block_id: str | None = None
        for row in sheet_rows:
            if _is_block_title(row) and not _intermediate_heading(row, block_id):
                label = str(row.get("label") or "")
                if _phrase_ytd(label):
                    current = label
                    block_id = str(row.get("block_id") or "") or None
                else:
                    current = None
                    block_id = None
                continue
            if row.get("kind") != "fact" or not current or _phrase_ytd(_row_header(row)):
                continue
            path = _path(row)
            if any(_phrase_ytd(part) for part in path):
                continue
            extended = [*path, current]
            row["label_path"] = extended
            row["label_path_json"] = json.dumps(extended, ensure_ascii=False)
            if not row.get("parent_label"):
                row["parent_label"] = current


def _is_block_title(row: dict) -> bool:
    """Строка без чисел с подписью открывает или закрывает блок."""

    if row.get("kind") == "fact":
        return False
    return bool(str(row.get("label") or "").strip())


def _intermediate_heading(row: dict, block_id: str | None) -> bool:
    """Промежуточный итог внутри блока не закрывает заголовок блока.

    Свой `label_path` строки на это не влияет: заголовок действует до следующего
    заголовка блока. Вложенный заголовок — это отступ, непустой путь или тот же
    `block_id`, что у открытого блока.
    """

    if _phrase_ytd(str(row.get("label") or "")):
        return False
    if int(row.get("indent") or 0) > 0 or _path(row):
        return True
    own = str(row.get("block_id") or "") or None
    return bool(block_id) and own == block_id


def _header_ytd(row: dict) -> bool:
    """Фраза нарастающего итога ищется в каждой части пути, а не в склеенной строке.

    Хвост после фразы допускается только пустым или «за год». Склейка
    «за год › следующий заголовок» этот хвост ломает, хотя часть пути фразу содержит.
    """

    return any(_phrase_ytd(part) for part in _header_parts(row))


def _header_parts(row: dict) -> list[str]:
    raw = [row.get("sheet"), row.get("parent_label"), *_path(row)]
    parts: list[str] = []
    for item in raw:
        if not item:
            continue
        parts.extend(piece.strip() for piece in str(item).split("›") if piece.strip())
    return parts


def _row_header(row: dict) -> str:
    """Заголовок листа и раздела. Колонка сюда не входит: она относится только к себе."""

    parts = [row.get("sheet"), row.get("parent_label")]
    parts.extend(_path(row))
    return " ".join(str(part) for part in parts if part)


def _column_headers(series: dict | None, calendar: dict | None) -> list[str]:
    headers = []
    for key in series or {}:
        meta = (calendar or {}).get(key) or {}
        headers.append(str(meta.get("header_text") or ""))
    return headers


def _columns_agree(headers: list[str], phrase) -> bool:
    """Способ показа колонки ставится строке, только если все числовые колонки совпали."""

    if not headers or any(not text for text in headers):
        return False
    return all(phrase(text) for text in headers)


def _path(row: dict) -> list[str]:
    path = row.get("label_path")
    if isinstance(path, list):
        return [str(item) for item in path]
    raw = row.get("label_path_json")
    if not isinstance(raw, str) or not raw:
        return []
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return []


def _ltm_formula(
    row: dict,
    links: list[dict] | None,
    calendar: dict | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> bool:
    """Скользящая сумма последних четырёх кварталов или двенадцати месяцев.

    Полное окно требуется с той колонки, где уже есть четыре квартала или
    двенадцать месяцев. Более ранние колонки могут складывать более короткий
    префикс той же строки или одной строки-источника. Хотя бы одно полное окно
    переходит через границу года и не сбрасывается в январе.
    """

    if not links or not calendar:
        return False
    grain, keys = _period_keys(series, calendar)
    width = {"quarter": 4, "month": 12}.get(grain or "")
    if not width or not keys:
        return False
    located = _located(links, facts)
    by_period = _formulas_by_period(links, str(row.get("row_key") or ""))
    crossed = False
    for axis, period_id in keys:
        order = _axis_order(calendar, axis)
        ids = [item[1] for item in order]
        if str(period_id) not in ids:
            return False
        index = ids.index(str(period_id))
        if index + 1 < width:
            expected = ids[: index + 1]
        else:
            expected = ids[index + 1 - width : index + 1]
        formulas = by_period.get(str(period_id)) or []
        if not any(_matches_window(formula, located, expected) for formula in formulas):
            return False
        if len(expected) < width:
            continue
        years = {_year_of(meta) for _index, pid, meta in order if pid in expected}
        years.discard(None)
        if len(years) >= 2:
            crossed = True
    return crossed


def _ytd_formula(
    row: dict,
    links: list[dict] | None,
    calendar: dict | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> bool:
    """Нарастающий итог по формуле этой строки или одной строки-источника.

    Либо каждый период после первого в году прибавляет предыдущую ячейку, либо
    колонка квартала k складывает первые k периодов одной строки-источника и
    в следующем году начинается заново. Номер квартала может стоять в заголовке
    колонки: ветка IF или CHOOSE, либо растущий диапазон SUM. Одной такой ячейки
    мало. Копирование предыдущей ячейки без сложения — перенос остатка или
    штопор, а не нарастающий итог.
    """

    if not links or not calendar:
        return False
    grain, keys = _period_keys(series, calendar)
    if not grain or not keys:
        return False
    row_key = str(row.get("row_key") or "")
    located = _located(links, facts)
    by_period = _formulas_by_period(links, row_key)
    if _copies_previous(by_period, row_key, located, calendar):
        return False
    if _running_add(by_period, row_key, located, calendar, keys):
        return True
    return _prefix_sum(by_period, located, calendar, keys)


def _running_add(by_period, row_key: str, located: dict, calendar: dict, keys: set[tuple]) -> bool:
    """Каждый период после первого в году прибавляет предыдущую ячейку этой строки."""

    wanted = {(str(axis), str(period_id)) for axis, period_id in keys}
    by_axis: dict[str, list[tuple[int, str, dict]]] = {}
    for (axis, period_id), meta in calendar.items():
        if (str(axis), str(period_id)) not in wanted:
            continue
        by_axis.setdefault(str(axis), []).append((int(meta.get("period_index") or 0), str(period_id), meta))
    qualified = False
    for items in by_axis.values():
        items.sort()
        order = [period_id for _index, period_id, _meta in items]
        previous = {period_id: order[index - 1] for index, period_id in enumerate(order) if index}
        years: dict[object, list[str]] = {}
        for _index, period_id, meta in items:
            year = _year_of(meta)
            if year is None:
                continue
            years.setdefault(year, []).append(period_id)
        for period_ids in years.values():
            if len(period_ids) < 2:
                continue
            flags = [
                _adds_previous(by_period.get(period_id) or [], row_key, previous.get(period_id), located)
                for period_id in period_ids
            ]
            if flags[0] or not all(flags[1:]):
                return False
            qualified = True
    return qualified


def _prefix_sum(by_period: dict, located: dict, calendar: dict, keys: set[tuple]) -> bool:
    """Сумма с начала года по одной строке. Следующий год эту сумму не продолжает.

    Если в новом году есть число, его формула должна начинаться в этом году.
    Ссылка на прошлый год оставляет строку `period`.
    """

    by_axis: dict[str, list[str]] = {}
    for axis, period_id in keys:
        by_axis.setdefault(str(axis), []).append(str(period_id))
    qualified = False
    for axis, period_ids in by_axis.items():
        order = _axis_order(calendar, axis)
        years: dict[object, list[str]] = {}
        for period_id in period_ids:
            meta = next((meta for _index, pid, meta in order if pid == period_id), None)
            year = _year_of(meta) if meta else None
            if year is None:
                return False
            years.setdefault(year, []).append(period_id)
        for year, ids in years.items():
            year_ids = [pid for _index, pid, meta in order if _year_of(meta) == year]
            grew = False
            for period_id in ids:
                if period_id not in year_ids:
                    return False
                prefix = year_ids[: year_ids.index(period_id) + 1]
                formulas = by_period.get(period_id) or []
                matched = any(_covers_prefix(formula, located, prefix, calendar) for formula in formulas)
                if len(prefix) < 2:
                    if formulas and not matched:
                        return False
                    continue
                if not matched:
                    return False
                grew = True
            if grew:
                qualified = True
            elif len(ids) >= 2:
                return False
    return qualified


def _covers_prefix(formula: dict, located: dict, prefix: list[str], calendar: dict) -> bool:
    """Колонка k складывает первые k периодов одной строки-источника.

    IF и CHOOSE, в том числе «ЕСЛИ» и «ВЫБОР», смотрят ветку номера квартала.
    Номер квартала может стоять в ячейке другой строки. Источник может быть
    на другом листе: периоды сравниваются по дате, а не по тексту ключа.
    Голая ссылка первого квартала — сумма из одного периода.
    """

    text = str(formula.get("formula") or "")
    if _is_choice(text):
        branch = _branch_for_quarter(text, len(prefix))
        refs = _branch_cells(branch, str(formula.get("cell") or "")) if branch else []
        if refs and _periods_are_prefix(refs, located, prefix, calendar):
            return True
        if refs:
            return False
    if len(prefix) > 1 and not _sums_formula(formula) and not _is_choice(text):
        return False
    return _periods_are_prefix(list(formula.get("refs") or []), located, prefix, calendar)


def _periods_are_prefix(refs: list[str], located: dict, prefix: list[str], calendar: dict) -> bool:
    by_row: dict[str, list[str]] = {}
    current = _slot(calendar, prefix[-1])
    for ref in refs:
        target = located.get(ref)
        if target is None:
            continue
        row_key, period_id = target
        by_row.setdefault(str(row_key), []).append(str(period_id))
    wanted = sorted(_slot(calendar, period_id) for period_id in prefix)
    matched = [row for row, periods in by_row.items() if sorted(_slot(calendar, period_id) for period_id in periods) == wanted]
    if len(matched) != 1:
        return False
    for row, periods in by_row.items():
        if row in matched:
            continue
        if any(_slot(calendar, period_id) != current for period_id in periods):
            return False
    return True


def _slot(calendar: dict, period_id: str) -> tuple:
    """Период для сравнения между листами: дата конца, иначе сам ключ."""

    for (_axis, pid), meta in (calendar or {}).items():
        if str(pid) != str(period_id):
            continue
        end = _as_date((meta or {}).get("period_end"))
        if end is not None:
            return ("end", end)
    return ("id", str(period_id))


def _is_choice(text: str) -> bool:
    folded = text.casefold().replace("ё", "е")
    return any(token in folded for token in ("if(", "choose(", "если(", "выбор("))


def _branch_for_quarter(text: str, quarter: int) -> str | None:
    """Ветка IF или CHOOSE для квартала с номером `quarter` внутри года."""

    body = text.strip()
    if body.startswith("="):
        body = body[1:].strip()
    choose = _call_args(body, "CHOOSE") or _call_args(body, "ВЫБОР")
    if choose is not None:
        if quarter < 1 or len(choose) <= quarter or not (_CELL_FIND.search(choose[0]) or _R1C1_FIND.search(choose[0])):
            return None
        return choose[quarter]
    return _if_branch(body, quarter)


def _if_branch(text: str, quarter: int) -> str | None:
    args = _call_args(text, "IF") or _call_args(text, "ЕСЛИ")
    if not args or len(args) < 2:
        return None
    number = _compared_number(args[0])
    if number == quarter:
        return args[1]
    if len(args) < 3:
        return None
    nested = _if_branch(args[2], quarter)
    if nested is not None:
        return nested
    if number is not None and quarter == number + 1 and _call_args(args[2], "IF") is None:
        return args[2]
    return None


def _compared_number(condition: str) -> int | None:
    """Номер квартала в условии: `=1` или `="1"`."""

    match = re.search(r'=\s*"(\d+)"|=\s*(\d+)\b', condition)
    if match is None:
        return None
    return int(next(group for group in match.groups() if group is not None))


def _call_args(text: str, name: str) -> list[str] | None:
    match = re.match(rf"(?i){name}\s*\(", text.strip())
    if match is None:
        return None
    depth = 1
    args: list[str] = []
    buf: list[str] = []
    for char in text[match.end() :]:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(buf).strip())
                return args
            buf.append(char)
        elif char in {",", ";"} and depth == 1:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    return None


_CELL_FIND = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[^'\s!=+()*/,;]+)!)?"
    r"\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)"
)
_R1C1_FIND = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[^'\s!=+()*/,;]+)!)?"
    r"R(?P<row>\d+)C(?P<col>\d+)",
    re.IGNORECASE,
)
_RANGE_FIND = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[^'\s!=+()*/,;]+)!)?"
    r"\$?(?P<c1>[A-Za-z]{1,3})\$?(?P<r1>\d+)\s*:\s*"
    r"\$?(?P<c2>[A-Za-z]{1,3})\$?(?P<r2>\d+)"
)


def _branch_cells(branch: str, origin: str) -> list[str]:
    """Адреса ячеек ветки. Диапазон раскрывается, лист берётся из формулы."""

    default_sheet = origin.split("!", 1)[0] if "!" in origin else ""
    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for match in _RANGE_FIND.finditer(branch):
        covered.append((match.start(), match.end()))
        found.extend(_range_cells(match, default_sheet))
    for match in _R1C1_FIND.finditer(branch):
        if any(start <= match.start() < end for start, end in covered):
            continue
        covered.append((match.start(), match.end()))
        sheet = _sheet_of(match.group("sheet"), default_sheet)
        found.append(f"{sheet}!{_col_letters(int(match.group('col')))}{match.group('row')}")
    for match in _CELL_FIND.finditer(branch):
        if any(start <= match.start() < end for start, end in covered):
            continue
        found.append(_cell_id(match.group("sheet"), match.group("col"), match.group("row"), default_sheet))
    return found


def _range_cells(match: re.Match[str], default_sheet: str) -> list[str]:
    sheet = _sheet_of(match.group("sheet"), default_sheet)
    c1, c2 = sorted((_col_index(match.group("c1")), _col_index(match.group("c2"))))
    r1, r2 = sorted((int(match.group("r1")), int(match.group("r2"))))
    if c2 - c1 > 64 or r2 - r1 > 64:
        return []
    return [f"{sheet}!{_col_letters(col)}{row}" for row in range(r1, r2 + 1) for col in range(c1, c2 + 1)]


def _cell_id(sheet: str | None, col: str, row: str, default_sheet: str) -> str:
    return f"{_sheet_of(sheet, default_sheet)}!{col.lstrip('$').upper()}{row.lstrip('$')}"


def _sheet_of(sheet: str | None, default_sheet: str) -> str:
    if not sheet:
        return default_sheet
    return sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet


def _col_index(letters: str) -> int:
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - 64
    return number


def _col_letters(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _matches_window(formula: dict, located: dict, expected: list[str]) -> bool:
    """Ссылки формулы — ровно эти периоды одной строки, без посторонних ячеек."""

    if not _sums_formula(formula):
        return False
    rows: set[str] = set()
    periods: list[str] = []
    for ref in formula["refs"]:
        target = located.get(ref)
        if target is None:
            return False
        rows.add(str(target[0]))
        periods.append(str(target[1]))
    if len(rows) != 1:
        return False
    return sorted(periods) == sorted(expected)


def _axis_order(calendar: dict, axis: str) -> list[tuple[int, str, dict]]:
    items = []
    for (found, period_id), meta in calendar.items():
        if str(found) != str(axis):
            continue
        items.append((int(meta.get("period_index") or 0), str(period_id), meta))
    items.sort()
    return items


def _adds_previous(formulas: list[dict], row_key: str, prior: str | None, located: dict) -> bool:
    """Формула прибавляет предыдущую ячейку. Голая ссылка на неё сложением не считается."""

    if not prior:
        return False
    for formula in formulas:
        if not _sums_formula(formula):
            continue
        if any(located.get(ref) == (row_key, prior) for ref in formula["refs"]):
            return True
    return False


def _copies_previous(by_period: dict, row_key: str, located: dict, calendar: dict) -> bool:
    """Копирование предыдущей ячейки без сложения — остаток или штопор."""

    by_axis: dict[str, list[str]] = {}
    ranked = sorted(calendar.items(), key=lambda item: (str(item[0][0]), int(item[1].get("period_index") or 0)))
    for (axis, period_id), _meta in ranked:
        by_axis.setdefault(str(axis), []).append(str(period_id))
    previous: dict[str, str] = {}
    for period_ids in by_axis.values():
        for index, period_id in enumerate(period_ids):
            if index:
                previous[period_id] = period_ids[index - 1]
    for period_id, formulas in by_period.items():
        prior = previous.get(str(period_id))
        if not prior:
            continue
        for formula in formulas:
            if _sums_formula(formula):
                continue
            if any(located.get(ref) == (row_key, prior) for ref in formula["refs"]):
                return True
    return False


def _period_keys(series: dict | None, calendar: dict | None) -> tuple[str | None, set[tuple]]:
    """Зерно и ключи колонок, в которых у строки есть число. Смешанное зерно пусто."""

    if not series or not calendar:
        return None, set()
    grouped: dict[str, set[tuple]] = {}
    for key in series:
        meta = calendar.get(key) or {}
        grain = str(meta.get("grain") or "").lower()
        if not grain:
            return None, set()
        grouped.setdefault(grain, set()).add(key)
    if len(grouped) != 1:
        return None, set()
    grain, keys = next(iter(grouped.items()))
    return grain, keys


def _formulas_by_period(links: list[dict], row_key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for formula in _formulas(links, row_key).values():
        grouped.setdefault(str(formula.get("period_id") or ""), []).append(formula)
    return grouped


def _formulas(links: list[dict], row_key: str) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for link in links:
        if str(link.get("row_key") or "") != row_key:
            continue
        cell = str(link.get("cell") or "")
        item = found.setdefault(
            cell,
            {
                "formula": link.get("formula"),
                "formula_class": link.get("formula_class"),
                "period_id": link.get("period_id"),
                "cell": cell,
                "refs": set(),
            },
        )
        if link.get("ref_cell"):
            item["refs"].add(str(link["ref_cell"]))
    return found


def _located(links: list[dict] | None, facts: list[dict] | None = None) -> dict[str, tuple[str, str]]:
    """Ячейка → строка и период. Введённое число берётся из факта, формула — из связи."""

    found: dict[str, tuple[str, str]] = {}
    for fact in facts or []:
        cell = fact.get("cell_id")
        row_key = fact.get("row_key")
        period_id = fact.get("period_id")
        if cell and row_key and period_id:
            found[str(cell)] = (str(row_key), str(period_id))
    for link in links or []:
        cell = link.get("cell")
        row_key = link.get("row_key")
        period_id = link.get("period_id")
        if cell and row_key and period_id:
            found[str(cell)] = (str(row_key), str(period_id))
    return found


def _sums_formula(formula: dict) -> bool:
    text = str(formula.get("formula") or "").casefold()
    kind = str(formula.get("formula_class") or "").casefold()
    return "sum" in kind or "sum" in text or "+" in text


def _year_of(period: dict) -> int | None:
    year = period.get("calendar_year")
    if isinstance(year, int):
        return year
    start = _as_date(period.get("period_start"))
    if start is not None:
        return start.year
    return None


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _month_span(start: date, end: date) -> set[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    year, month = start.year, start.month
    last = (end.year, end.month)
    while (year, month) <= last:
        months.add((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months
