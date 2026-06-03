import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATABASE_PATH


def _ensure_db_dir() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
    }
    if "source_name" not in columns:
        conn.execute(
            "ALTER TABLE analyses ADD COLUMN source_name TEXT NOT NULL DEFAULT ''"
        )
        rows = conn.execute(
            "SELECT id, source_type, source_label, clean_text FROM analyses"
        ).fetchall()
        from ingest.source import derive_source_name

        for row in rows:
            name = derive_source_name(
                source_type=row["source_type"],
                source_label=row["source_label"],
                text=row["clean_text"] or "",
            )
            conn.execute(
                "UPDATE analyses SET source_name = ? WHERE id = ?",
                (name, row["id"]),
            )


DEFAULT_WEBSITES: list[tuple[str, str]] = [
    ("Stratechery", "https://stratechery.com"),
    ("Clouded Judgement", "https://cloudedjudgement.substack.com"),
    ("Fabricated Knowledge", "https://www.fabricatedknowledge.com"),
    ("Big Technology", "https://www.bigtechnology.com"),
    ("Platformer", "https://www.platformer.news"),
    ("Import AI", "https://importai.substack.com"),
    ("SemiAnalysis", "https://semianalysis.com"),
    ("The Diff", "https://www.thediff.co"),
    ("Tae Kim Newsletter", "https://tanjimb.substack.com"),
    ("Newcomer", "https://www.newcomer.co"),
]


def _seed_websites(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM websites").fetchone()[0]
    if count:
        return
    now = datetime.now(timezone.utc).isoformat()
    for name, url in DEFAULT_WEBSITES:
        conn.execute(
            "INSERT INTO websites (name, url, created_at) VALUES (?, ?, ?)",
            (name, url, now),
        )


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                clean_text TEXT NOT NULL,
                detected_tickers TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'done'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _migrate(conn)
        _seed_websites(conn)
        conn.commit()


def tickers_from_analysis(analysis: dict[str, Any]) -> list[str]:
    """Tickers shown in Stocks Mentioned (company_opinions only)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for co in analysis.get("company_opinions", []):
        t = str(co.get("ticker", "")).strip().upper()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def save_analysis(
    *,
    source_type: str,
    source_label: str,
    source_name: str,
    title: str,
    clean_text: str,
    detected_tickers: list[str],
    analysis: dict[str, Any],
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analyses (
                created_at, source_type, source_label, source_name, title,
                clean_text, detected_tickers, analysis_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done')
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                source_type,
                source_label,
                source_name,
                title,
                clean_text,
                json.dumps(detected_tickers),
                json.dumps(analysis),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_analysis(
    analysis_id: int,
    *,
    source_type: str,
    source_label: str,
    source_name: str,
    title: str,
    clean_text: str,
    detected_tickers: list[str],
    analysis: dict[str, Any],
) -> int:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE analyses SET
                created_at = ?,
                source_type = ?,
                source_label = ?,
                source_name = ?,
                title = ?,
                clean_text = ?,
                detected_tickers = ?,
                analysis_json = ?,
                status = 'done'
            WHERE id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                source_type,
                source_label,
                source_name,
                title,
                clean_text,
                json.dumps(detected_tickers),
                json.dumps(analysis),
                analysis_id,
            ),
        )
        conn.commit()
    return analysis_id


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    analysis = json.loads(row["analysis_json"])
    tickers = tickers_from_analysis(analysis)
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source_type": row["source_type"],
        "source_label": row["source_label"],
        "source_name": row["source_name"] or "",
        "title": row["title"],
        "detected_tickers": tickers,
        "analysis": analysis,
    }


def list_analyses(
    limit: int = 100,
    *,
    source_name: str | None = None,
    ticker: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT id, created_at, source_type, source_label, source_name, title,
               detected_tickers, analysis_json
        FROM analyses
    """
    params: list[Any] = []
    clauses: list[str] = []

    if source_name:
        clauses.append("source_name = ?")
        params.append(source_name)
    if ticker:
        ticker = ticker.upper()
        clauses.append("analysis_json LIKE ?")
        params.append(f'%"ticker": "{ticker}"%')

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    results = [_row_to_summary(row) for row in rows]
    if ticker:
        results = [r for r in results if ticker in r["detected_tickers"]]
    return results


def list_source_names() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT source_name FROM analyses
            WHERE source_name != ''
            ORDER BY source_name COLLATE NOCASE
            """
        ).fetchall()
    return [row[0] for row in rows]


def list_websites() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, url, created_at FROM websites
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "url": row["url"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def add_website(name: str, url: str) -> int:
    name = name.strip()
    url = url.strip()
    if not name or not url:
        raise ValueError("Name and URL are required.")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    with _connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO websites (name, url, created_at)
                VALUES (?, ?, ?)
                """,
                (name, url, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A source named “{name}” already exists.") from exc
        return int(cursor.lastrowid)


def delete_website(website_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM websites WHERE id = ?", (website_id,))
        conn.commit()
        return cursor.rowcount > 0


def list_filter_source_names() -> list[str]:
    names = {row["name"] for row in list_websites()}
    names.update(list_source_names())
    return sorted(names, key=str.lower)


def list_tickers() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT analysis_json FROM analyses").fetchall()

    seen: set[str] = set()
    for row in rows:
        analysis = json.loads(row["analysis_json"])
        for t in tickers_from_analysis(analysis):
            seen.add(t)
    return sorted(seen)


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

    analysis = json.loads(row["analysis_json"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source_type": row["source_type"],
        "source_label": row["source_label"],
        "source_name": row["source_name"] or "",
        "title": row["title"],
        "clean_text": row["clean_text"],
        "detected_tickers": tickers_from_analysis(analysis),
        "analysis": analysis,
    }
