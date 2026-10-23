"""Strong ETag `/summary` формы summary-2.

Формат как у builder (`api/etag.py::strong_etag`): quoted
`summary-2:<content>:<ctx_mtime_ns>:<ctx_size>:<graph_mtime_ns>:<graph_size>`.
Фикстура подставляет детерминированные mtime вместо stat.
"""

from __future__ import annotations

SCHEMA_ID = "summary-2"


def strong_etag(
    *,
    content_sha256: str,
    context_mtime_ns: int,
    context_size: int,
    graph_mtime_ns: int,
    graph_size: int,
) -> str:
    body = ":".join(
        [
            SCHEMA_ID,
            content_sha256,
            str(context_mtime_ns),
            str(context_size),
            str(graph_mtime_ns),
            str(graph_size),
        ]
    )
    return f'"{body}"'
