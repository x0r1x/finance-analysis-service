"""Анализы, сравнение, отчёт и находки."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from finance_analysis.application.report import REPORT_FORMATS, choose_format
from finance_analysis.domain.ids import job_id as check_job


def register(app, settings, *, actor, limited, svc, support, calc, findings_read) -> None:
    @app.post("/v1/books/{job_id}/analyses")
    async def run_analysis(job_id: str, request: Request):
        return await calc(job_id, request, svc().analyses.run, prefer_async=True)

    @app.post("/v1/books/{job_id}:compare")
    async def compare(job_id: str, request: Request):
        return await calc(job_id, request, svc().compare.run, prefer_async=True)

    @app.get("/v1/books/{job_id}/analyses")
    async def list_analyses(
        job_id: str,
        request: Request,
        type: str | None = None,
        status: str | None = None,
        page_size: int = 50,
        page_token: str | None = None,
    ):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                return await svc().analyses.history(
                    checked, kind=type, status=status, page_size=page_size, page_token=page_token
                )
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/analyses/{analysis_id}")
    async def get_analysis(job_id: str, analysis_id: str, request: Request):
        checked = check_job(job_id)
        who = actor(request)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                return await svc().analyses.result(checked, analysis_id)
        finally:
            app.state.inflight -= 1

    @app.get("/v1/books/{job_id}/analyses/{analysis_id}/report")
    async def get_report(job_id: str, analysis_id: str, request: Request, format: str | None = None):
        checked = check_job(job_id)
        who = actor(request)
        fmt = choose_format(format, request.headers.get("accept"), REPORT_FORMATS)
        await limited(request, who)
        try:
            async with support().user_inflight(who):
                body, media = await svc().analyses.report(checked, analysis_id, fmt)
        finally:
            app.state.inflight -= 1
        return Response(content=body, media_type=media)

    @app.get("/v1/books/{job_id}/findings")
    async def list_findings(job_id: str, request: Request):
        async def read(checked, who, query):
            return await svc().analyses.findings(checked, who, query, wait_sec=settings.load_sync_sec)

        return await findings_read(job_id, request, read)

    @app.get("/v1/books/{job_id}/findings/{fingerprint}")
    async def explain_finding(job_id: str, fingerprint: str, request: Request):
        async def read(checked, who, query):
            return await svc().analyses.finding(checked, fingerprint, who, query, wait_sec=settings.load_sync_sec)

        return await findings_read(job_id, request, read)
