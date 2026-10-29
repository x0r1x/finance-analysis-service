"""Счётчики, которые увеличивает сценарий, а не HTTP-адаптер."""

from prometheus_client import Counter, Gauge

BUILDER_INCONSISTENT = Counter(
    "fas_builder_inconsistent_total",
    "Публикации builder, не прошедшие проверку согласованности",
)
GLOSSARY_UNKNOWN_SHARE = Gauge("fas_glossary_unknown_share", "Доля unknown за последний месяц покрытия")
GLOSSARY_AUTO_ROLLBACK = Gauge("fas_glossary_auto_rollback_rate", "Доля авто-меток, отвергнутых за 30 дней")
GLOSSARY_REVIEW_OPEN = Gauge("fas_glossary_review_open", "Открытые предложения глоссария")
