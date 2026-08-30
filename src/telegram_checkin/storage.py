from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .models import CheckResult, CheckStatus

_COMPLETED_STATUSES = (CheckStatus.SUCCESS.value, CheckStatus.ALREADY.value)


class AttemptStore:
    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY,
                    target TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS attempts_target_date ON attempts(target, local_date)"
            )

    def completed_on(self, target: str, local_date: date) -> bool:
        placeholders = ", ".join("?" for _ in _COMPLETED_STATUSES)
        query = f"""
            SELECT 1 FROM attempts
            WHERE target = ? AND local_date = ? AND status IN ({placeholders})
            LIMIT 1
        """
        with self._connect() as connection:
            row = connection.execute(
                query, (target, local_date.isoformat(), *_COMPLETED_STATUSES)
            ).fetchone()
        return row is not None

    def record(self, result: CheckResult, local_date: date) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO attempts(target, local_date, status, detail, attempted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.target,
                    local_date.isoformat(),
                    result.status.value,
                    result.detail,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection
