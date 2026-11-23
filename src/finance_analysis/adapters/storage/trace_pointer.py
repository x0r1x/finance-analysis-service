"""Указатель хвоста в DuckDB. Слот анализа резервируется под замком. PostgreSQL нет."""

from __future__ import annotations

import threading
from pathlib import Path

from finance_analysis.domain.trace_limit import TRACE_LIMIT, TraceLimitError

_TABLE = """
CREATE TABLE IF NOT EXISTS trace_pointer (
    analysis_id VARCHAR NOT NULL,
    execution_id VARCHAR NOT NULL,
    object_key VARCHAR NOT NULL,
    evidence_complete BOOLEAN NOT NULL,
    dropped_cell_count INTEGER NOT NULL,
    retained_until VARCHAR,
    state VARCHAR NOT NULL DEFAULT 'committed',
    PRIMARY KEY (analysis_id, execution_id)
)
"""
_COLUMNS = """
analysis_id, execution_id, object_key, evidence_complete,
dropped_cell_count, retained_until, state
"""


class DuckDBTracePointer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def reserve(
        self,
        analysis_id: str,
        execution_id: str,
        *,
        object_key: str,
        evidence_complete: bool,
        dropped_cell_count: int,
        retained_until: str | None,
    ) -> str:
        """Один слот на execution_id. Повтор того же идентификатора новый слот не занимает."""

        with self._lock(analysis_id):
            existing = self.get(analysis_id, execution_id)
            if existing is not None:
                return str(existing.get("state") or "committed")
            if self.count(analysis_id) >= TRACE_LIMIT:
                raise TraceLimitError(f"следов больше {TRACE_LIMIT}")
            self.put(
                {
                    "analysis_id": analysis_id,
                    "execution_id": execution_id,
                    "object_key": object_key,
                    "evidence_complete": evidence_complete,
                    "dropped_cell_count": dropped_cell_count,
                    "retained_until": retained_until,
                    "state": "pending",
                }
            )
            return "reserved"

    def commit(self, row: dict) -> None:
        self.put({**row, "state": "committed"})

    def put(self, row: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO trace_pointer ({_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row["analysis_id"],
                    row["execution_id"],
                    row["object_key"],
                    bool(row["evidence_complete"]),
                    int(row["dropped_cell_count"]),
                    row.get("retained_until"),
                    row.get("state") or "committed",
                ],
            )

    def get(self, analysis_id: str, execution_id: str) -> dict | None:
        with self._connect() as conn:
            result = conn.execute(
                f"""
                SELECT {_COLUMNS}
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
        return self._list("WHERE analysis_id = ? ORDER BY execution_id", [analysis_id])

    def list_all(self) -> list[dict]:
        return self._list("ORDER BY analysis_id, execution_id", [])

    def delete(self, analysis_id: str, execution_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM trace_pointer WHERE analysis_id = ? AND execution_id = ?",
                [analysis_id, execution_id],
            )

    def _list(self, clause: str, params: list) -> list[dict]:
        with self._connect() as conn:
            result = conn.execute(f"SELECT {_COLUMNS} FROM trace_pointer {clause}", params)
            names = [item[0] for item in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    def _lock(self, analysis_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(analysis_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[analysis_id] = lock
            return lock

    def _connect(self):
        import duckdb

        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.path))
        conn.execute(_TABLE)
        columns = {row[0] for row in conn.execute("DESCRIBE trace_pointer").fetchall()}
        if "state" not in columns:
            conn.execute("ALTER TABLE trace_pointer ADD COLUMN state VARCHAR DEFAULT 'committed'")
        return conn


def _row(result) -> dict | None:
    row = result.fetchone()
    if row is None:
        return None
    names = [item[0] for item in result.description]
    return dict(zip(names, row, strict=True))
