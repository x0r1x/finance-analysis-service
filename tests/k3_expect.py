"""Общая проверка книги К3. Файла в репозитории нет, имя клиента не пишется.

Ожидаемый тип — corporate. primary из соседнего файла должен совпасть с ним,
и вывод должен быть уверенным с этой одной меткой. Неуверенный лидер
с тем же именем не проходит.
"""

from __future__ import annotations


def assert_confident_primary(got, primary: str) -> None:
    assert primary == "corporate"
    assert got.confident is True
    assert got.primary == primary
    assert got.labels == (primary,)
