"""Указатель хвоста в DuckDB. PostgreSQL нет."""

from __future__ import annotations

from pathlib import Path

_TABLE = """
CREATE TABLE IF NOT EXISTS trace_pointer (
    analysis_id VARCHAR NOT NULL,
    execution_id VARCHAR NOT NULL,
    object_key VARCHAR NOT NULL,
    evidence_complete BOOLEAN NOT NULL,
    dropped_cell_count INTEGER NOT NULL,
    retained_until VARCHAR,
    PRIMARY KEY (analysis_id, execution_id)
)
"""


class DuckDBTracePointer:
    def __init__(self, path: Path) -> None:
        self.path = path

    def put(self, row: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trace_pointer
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    row["analysis_id"],
                    row["execution_id"],
                    row["object_key"],
                    bool(row["evidence_complete"]),
                    int(row["dropped_cell_count"]),
                    row.get("retained_until"),
                ],
            )

    def get(self, analysis_id: str, execution_id: str) -> dict | None:
        with self._connect() as conn:
            result = conn.execute(
                """
                SELECT analysis_id, execution_id, object_key, evidence_complete,
                       dropped_cell_count, retained_until
                FROM trace_pointer
                WHERE analysis_id = ? AND execution_id = ?
                """,
                [analysis_id, execution_id],
            )
            return _row(result)

    def count(self, analysis_id: str) -> int:
        with self._connect() as conn:
            found = conn.execute(
                "SELECT count(*) FROM trace_pointer WHERE analysis_id = ?",
                [analysis_id],
            ).fetchone()
        return int(found[0])

    def list_analysis(self, analysis_id: str) -> list[dict]:
        with self._connect() as conn:
            result = conn.execute(
                """
                SELECT analysis_id, execution_id, object_key, evidence_complete,
                       dropped_cell_count, retained_until
                FROM trace_pointer
                WHERE analysis_id = ?
                ORDER BY execution_id
                """,
                [analysis_id],
            )
            names = [item[0] for item in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    def delete(self, analysis_id: str, execution_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM trace_pointer WHERE analysis_id = ? AND execution_id = ?",
                [analysis_id, execution_id],
            )

    def _connect(self):
        import duckdb

        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.path))
        conn.execute(_TABLE)
        return conn


def _row(result) -> dict | None:
    row = result.fetchone()
    if row is None:
        return None
    names = [item[0] for item in result.description]
    return dict(zip(names, row, strict=True))
