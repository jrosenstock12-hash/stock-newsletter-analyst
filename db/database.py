import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                title TEXT NOT NULL,
                clean_text TEXT NOT NULL,
                detected_tickers TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'done'
            )
            """
        )
        conn.commit()


def save_analysis(
    *,
    source_type: str,
    source_label: str,
    title: str,
    clean_text: str,
    detected_tickers: list[str],
    analysis: dict[str, Any],
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (
                created_at, source_type, source_label, title,
                clean_text, detected_tickers, analysis_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'done')
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                source_type,
                source_label,
                title,
                clean_text,
                json.dumps(detected_tickers),
                json.dumps(analysis),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_analyses(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, source_type, source_label, title,
                   detected_tickers, analysis_json
            FROM analyses
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []
    for row in rows:
        analysis = json.loads(row["analysis_json"])
        results.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "source_type": row["source_type"],
                "source_label": row["source_label"],
                "title": row["title"],
                "detected_tickers": json.loads(row["detected_tickers"]),
                "analysis": analysis,
            }
        )
    return results


def delete_analyses(analysis_ids: list[int]) -> int:
    if not analysis_ids:
        return 0
    placeholders = ",".join("?" * len(analysis_ids))
    with _connect() as conn:
        cursor = conn.execute(
            f"DELETE FROM analyses WHERE id IN ({placeholders})",
            analysis_ids,
        )
        conn.commit()
        return cursor.rowcount


def get_analysis(analysis_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source_type": row["source_type"],
        "source_label": row["source_label"],
        "title": row["title"],
        "clean_text": row["clean_text"],
        "detected_tickers": json.loads(row["detected_tickers"]),
        "analysis": json.loads(row["analysis_json"]),
    }
