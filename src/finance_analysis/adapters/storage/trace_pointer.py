"""Указатель хвоста в DuckDB. Слот анализа резервируется под замком. PostgreSQL нет.

DuckDB 2.0 пускает одного писателя на файл
(https://duckdb.org/docs/2.0/connect/concurrency.html). API и worker — разные
процессы с одним `trace_pointer.duckdb`, поэтому резерв держит `flock`
(https://man7.org/linux/man-pages/man2/flock.2.html) на соседнем файле и
замок процесса для двух экземпляров в одном процессе. Это один хост с общим
`FAS_DATA_DIR`. Реплики без общего каталога этот файл не делят.
"""

from __future__ import annotations

import fcntl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from finance_analysis.domain.trace_limit import TRACE_LIMIT, TraceLimitError

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_GUARD = threading.Lock()

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

        with _exclusive(self.path):
            existing = self._get(analysis_id, execution_id)
            if existing is not None:
                return str(existing.get("state") or "committed")
            if self._count(analysis_id) >= TRACE_LIMIT:
                raise TraceLimitError(f"следов больше {TRACE_LIMIT}")
            self._put(
                {
                    "analysis_id": analysis_id,
                    "execution_id": execution_id,
                    "object_key": object_key,
                    "evidence_complete": evidence_complete,
                    "dropped_cell_count": dropped_cell_count,
                    "retained_until": retained_until,
                    "state": "pending_object",
                }
            )
            return "reserved"

    def commit(self, row: dict) -> None:
        self.put({**row, "state": "committed"})

    def set_state(self, analysis_id: str, execution_id: str, state: str) -> None:
        with _exclusive(self.path):
            row = self._get(analysis_id, execution_id)
            if row is None:
                return
            row["state"] = state
            self._put(row)

    def put(self, row: dict) -> None:
        with _exclusive(self.path):
            self._put(row)

    def get(self, analysis_id: str, execution_id: str) -> dict | None:
        with _exclusive(self.path):
            return self._get(analysis_id, execution_id)

    def count(self, analysis_id: str) -> int:
        with _exclusive(self.path):
            return self._count(analysis_id)

    def list_analysis(self, analysis_id: str) -> list[dict]:
        with _exclusive(self.path):
            return self._list("WHERE analysis_id = ? ORDER BY execution_id", [analysis_id])

    def list_all(self) -> list[dict]:
        with _exclusive(self.path):
            return self._list("ORDER BY analysis_id, execution_id", [])

    def delete(self, analysis_id: str, execution_id: str) -> None:
        with _exclusive(self.path), self._connect() as conn:
            conn.execute(
                "DELETE FROM trace_pointer WHERE analysis_id = ? AND execution_id = ?",
                [analysis_id, execution_id],
            )

    def _put(self, row: dict) -> None:
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

    def _get(self, analysis_id: str, execution_id: str) -> dict | None:
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

    def _count(self, analysis_id: str) -> int:
        with self._connect() as conn:
            found = conn.execute(
                "SELECT count(*) FROM trace_pointer WHERE analysis_id = ?",
                [analysis_id],
            ).fetchone()
        return int(found[0])

    def _list(self, clause: str, params: list) -> list[dict]:
        with self._connect() as conn:
            result = conn.execute(f"SELECT {_COLUMNS} FROM trace_pointer {clause}", params)
            names = [item[0] for item in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    def _connect(self):
        import duckdb

        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.path))
        conn.execute(_TABLE)
        columns = {row[0] for row in conn.execute("DESCRIBE trace_pointer").fetchall()}
        if "state" not in columns:
            conn.execute("ALTER TABLE trace_pointer ADD COLUMN state VARCHAR DEFAULT 'committed'")
        return conn


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    key = str(path.expanduser().absolute())
    with _THREAD_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock, lock_path.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _row(result) -> dict | None:
    row = result.fetchone()
    if row is None:
        return None
    names = [item[0] for item in result.description]
    return dict(zip(names, row, strict=True))
