"""Представления книги: семантика, привязка, вопросы, покрытие, решения."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from finance_analysis.domain.ids import job_id as check_job


def register(app, settings, *, svc, book_get, read, op_headers) -> None:
    @app.get("/v1/books/{job_id}/semantics")
    async def book_semantics(job_id: str, request: Request):
        return await book_get(
            job_id,
            request,
            lambda checked, who: svc().semantics_view(checked, who, wait_sec=settings.load_sync_sec),
        )

    @app.get("/v1/books/{job_id}/mapping")
    async def book_mapping(job_id: str, request: Request):
        return await book_get(
            job_id,
            request,
            lambda checked, who: svc().mapping_view(checked, who, wait_sec=settings.load_sync_sec),
        )

    @app.get("/v1/books/{job_id}/questions")
    async def book_questions(job_id: str, request: Request):
        return await book_get(
            job_id,
            request,
            lambda checked, who: svc().questions_view(checked, who, wait_sec=settings.load_sync_sec),
        )

    @app.get("/v1/books/{job_id}/coverage")
    async def book_coverage(job_id: str, request: Request):
        return await book_get(
            job_id,
            request,
            lambda checked, who: svc().coverage_view(checked, who, wait_sec=settings.load_sync_sec),
        )

    @app.get("/v1/books/{job_id}/decisions")
    async def book_decisions(
        job_id: str,
        request: Request,
        page_size: int = 50,
        page_token: str | None = None,
    ):
        checked = check_job(job_id)
        return await read(
            request,
            lambda _who: svc().list_decisions(checked, page_size=page_size, page_token=page_token),
        )

    @app.post("/v1/books/{job_id}/mapping:infer")
    async def mapping_infer(job_id: str, request: Request):
        checked = check_job(job_id)
        result = await read(request, lambda who: svc().infer_mapping(checked, who))
        return JSONResponse(result.operation, status_code=202, headers=op_headers(result))
