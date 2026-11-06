"""Общая проверка локального оракула К3. Файла в репозитории нет, имя клиента не пишется.

Оракул воспроизводит ранее записанный вердикт corporate и не доказывает тип независимо.
primary из соседнего файла должен совпасть, и вывод должен быть уверенным с этой одной
меткой. Неуверенный лидер с тем же именем не проходит. Ожидание из вывода infer не собирают.
"""

from __future__ import annotations


def assert_confident_primary(got, primary: str) -> None:
    assert primary == "corporate"
    assert got.confident is True
    assert got.primary == primary
    assert got.labels == (primary,)
