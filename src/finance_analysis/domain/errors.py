"""Каталог ошибок FAS (§3.2)."""

from __future__ import annotations


class FasError(Exception):
    code = "invalid_argument"
    status = 400
    retryable = False
    title = "Некорректный запрос"

    def __init__(self, detail: str, *, extra: dict | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}


class InvalidArgument(FasError):
    code = "invalid_argument"
    status = 400
    title = "Некорректный аргумент"


class InvalidId(FasError):
    code = "invalid_id"
    status = 400
    title = "Идентификатор вне белого списка"


class NotFound(FasError):
    code = "not_found"
    status = 404
    title = "Не найдено"


class NotAcceptable(FasError):
    code = "not_acceptable"
    status = 406
    title = "Формат не поддерживается"


class BindingConflict(FasError):
    code = "binding_conflict"
    status = 409
    title = "Конфликт правки"


class RequestInProgress(FasError):
    code = "request_in_progress"
    status = 409
    retryable = True
    title = "Запрос ещё выполняется"


class UnsupportedBuilderShape(FasError):
    code = "unsupported_builder_shape"
    status = 409
    title = "Форма builder не поддерживается"


class BuilderUnstable(FasError):
    code = "builder_unstable"
    status = 409
    title = "Builder пересобрал книгу во время загрузки"


class PreconditionFailed(FasError):
    code = "precondition_failed"
    status = 412
    title = "Предусловие не выполнено"


class IdempotencyReused(FasError):
    code = "idempotency_key_reused"
    status = 422
    title = "Ключ идемпотентности уже использован"


class RateLimited(FasError):
    code = "rate_limited"
    status = 429
    retryable = True
    title = "Превышена квота"


class BookBusy(FasError):
    code = "book_busy"
    status = 429
    retryable = True
    title = "Книга занята"


class TooManyInflight(FasError):
    code = "too_many_inflight"
    status = 429
    retryable = True
    title = "Слишком много одновременных запросов"


class Overloaded(FasError):
    code = "overloaded"
    status = 503
    retryable = True
    title = "Перегрузка"


class DependencyUnavailable(FasError):
    code = "dependency_unavailable"
    status = 503
    retryable = True
    title = "Зависимость недоступна"


class DeadlineExceeded(FasError):
    code = "deadline_exceeded"
    status = 504
    retryable = True
    title = "Истек дедлайн"


class AlreadyExists(FasError):
    """Внутренняя ошибка хранилища: объект уже есть. Наружу не отдаётся как есть."""

    code = "already_exists"
    status = 409
    title = "Объект уже существует"


class StartupError(FasError):
    code = "dependency_unavailable"
    status = 503
    title = "Сервис не может стартовать"


class SemanticRejected(FasError):
    code = "schema_invalid"
    status = 409
    title = "Семантическая запись отклонена"

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail, extra={"guard_code": code})
        self.code = code
