"""Маршруты чтения Financial Model Catalog (фаза 3)."""

from __future__ import annotations

from fastapi import Request

from finance_analysis.domain.errors import NotFound


def register(app, *, svc, read) -> None:
    @app.get("/v1/metrics")
    async def list_metrics(request: Request):
        return await read(request, lambda _who: svc().financial_model_catalog())

    @app.get("/v1/metrics/{metric_id}")
    async def get_metric(metric_id: str, request: Request):
        async def load(_who):
            body = svc().financial_model_indicator(metric_id)
            if body is None:
                raise NotFound("показатель не найден")
            return body

        return await read(request, load)
