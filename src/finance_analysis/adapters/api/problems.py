"""problem+json, RFC 9457. Один каталог с capabilities."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from finance_analysis.domain.errors import FasError


def problem_response(exc: FasError, request_id: str) -> JSONResponse:
    body = {
        "type": f"urn:fas:problem:{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": request_id,
        "code": exc.code,
        "retryable": exc.retryable,
    }
    for key, value in exc.extra.items():
        if key not in body:
            body[key] = value
    headers = {"X-Request-Id": request_id}
    if exc.retryable:
        headers["Retry-After"] = str(exc.extra.get("retry_after", 1))
    return JSONResponse(body, status_code=exc.status, media_type="application/problem+json", headers=headers)
