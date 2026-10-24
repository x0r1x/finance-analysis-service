"""Построение ключей object store только из проверенных идентификаторов."""

from __future__ import annotations

from finance_analysis.domain.ids import build_key as check_build
from finance_analysis.domain.ids import dataset_name
from finance_analysis.domain.ids import derive_key as check_derive
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.domain.ids import ulid as check_ulid

PROJECTION = {"dim_row", "dim_period", "fact_observation", "graph_links"}
DERIVED = {"row_semantics", "period_semantics", "bindings", "coverage"}
RESULT_FILES = {"result.json", "run.parquet", "findings.parquet"}


def book(job_id: str) -> str:
    return f"books/{check_job(job_id)}"


def head_key(job_id: str) -> str:
    return f"{book(job_id)}/_head.json"


def manifest_key(job_id: str, build: str) -> str:
    return f"{book(job_id)}/{check_build(build)}/manifest.json"


def build_index_key(job_id: str, build: str) -> str:
    return f"{book(job_id)}/_builds/{check_build(build)}.json"


def projection_key(job_id: str, build: str, attempt: str, dataset: str) -> str:
    name = dataset_name(dataset)
    if name not in PROJECTION:
        from finance_analysis.domain.errors import InvalidId

        raise InvalidId(f"набор {dataset} не проекция")
    return f"{book(job_id)}/{check_build(build)}/a/{check_ulid(attempt)}/projection/{name}.parquet"


def derived_file(job_id: str, build: str, derive: str, attempt: str, dataset: str) -> str:
    name = dataset_name(dataset)
    if name not in DERIVED:
        from finance_analysis.domain.errors import InvalidId

        raise InvalidId(f"набор {dataset} не derived")
    return (
        f"{book(job_id)}/{check_build(build)}/derived/{check_derive(derive)}"
        f"/a/{check_ulid(attempt)}/{name}.parquet"
    )


def derived_done(job_id: str, build: str, derive: str) -> str:
    return f"{book(job_id)}/{check_build(build)}/derived/{check_derive(derive)}/_done.json"


def result_rel(analysis_id: str, name: str) -> str:
    """Путь файла результата относительно папки сборки (так его перечисляет result.json)."""

    if name not in RESULT_FILES:
        from finance_analysis.domain.errors import InvalidId

        raise InvalidId(f"файл результата {name} вне белого списка")
    return f"results/{check_ulid(analysis_id)}/{name}"


def result_key(job_id: str, build: str, analysis_id: str, name: str) -> str:
    return f"{book(job_id)}/{check_build(build)}/{result_rel(analysis_id, name)}"


def report_index_key(job_id: str, analysis_id: str) -> str:
    return f"{book(job_id)}/_reports/{check_ulid(analysis_id)}.json"


def report_index_prefix(job_id: str) -> str:
    return f"{book(job_id)}/_reports/"


def log_key(job_id: str, seq: int) -> str:
    if seq < 1 or seq > 10**20:
        from finance_analysis.domain.errors import InvalidId

        raise InvalidId("номер журнала вне диапазона")
    return f"{book(job_id)}/_state/log/{seq:020d}.json"


def operation_key(op_id: str) -> str:
    return f"operations/{check_ulid(op_id)}/op.json"


def operation_event_key(op_id: str, seq: int) -> str:
    return f"operations/{check_ulid(op_id)}/events/{seq:06d}.json"
