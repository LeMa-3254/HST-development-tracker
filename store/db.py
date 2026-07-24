from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any

from models import Item

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db


def init_db(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.commit()


def upsert_items(db: sqlite3.Connection, items: list[Item]) -> None:
    rows = [item.to_db_row() for item in items]
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(":" + column for column in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    db.executemany(
        f"""
        INSERT INTO items ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {updates}
        """,
        rows,
    )
    db.commit()


def log_run(
    db: sqlite3.Connection,
    *,
    counts: dict[str, Any],
    errors: list[str] | None = None,
    token_usage: dict[str, Any] | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO runs (counts_json, errors_json, token_usage_json)
        VALUES (?, ?, ?)
        """,
        (
            json.dumps(counts, sort_keys=True),
            json.dumps(errors or [], sort_keys=True),
            json.dumps(token_usage or {}, sort_keys=True),
        ),
    )
    db.commit()


def included_items(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        db.execute(
            """
            SELECT *
            FROM items
            WHERE status = 'included'
            ORDER BY COALESCE(published_date, fetched_date) DESC, title ASC
            """
        )
    )


def included_items_between(db: sqlite3.Connection, *, start_date: str, end_date: str) -> list[sqlite3.Row]:
    return list(
        db.execute(
            """
            SELECT *
            FROM items
            WHERE status = 'included'
              AND COALESCE(published_date, fetched_date) BETWEEN ? AND ?
            ORDER BY COALESCE(published_date, fetched_date) DESC, title ASC
            """,
            (start_date, end_date),
        )
    )


def upsert_weekly_summary(
    db: sqlite3.Connection,
    *,
    week_start: str,
    week_end: str,
    synthesis_md: str,
    item_ids: list[str],
) -> None:
    db.execute(
        """
        INSERT INTO weekly_summaries (week_start, week_end, synthesis_md, item_ids, generated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(week_start) DO UPDATE SET
          week_end = excluded.week_end,
          synthesis_md = excluded.synthesis_md,
          item_ids = excluded.item_ids,
          generated_at = excluded.generated_at
        """,
        (week_start, week_end, synthesis_md, json.dumps(item_ids, sort_keys=True)),
    )
    db.commit()


def latest_weekly_summary(db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT *
        FROM weekly_summaries
        ORDER BY week_start DESC
        LIMIT 1
        """
    ).fetchone()


def weekly_summaries(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        db.execute(
            """
            SELECT *
            FROM weekly_summaries
            ORDER BY week_start DESC
            """
        )
    )


def _upsert_section(
    db: sqlite3.Connection,
    table: str,
    *,
    week_start: str,
    week_end: str,
    payload: dict[str, Any],
) -> None:
    db.execute(
        f"""
        INSERT INTO {table} (week_start, week_end, payload_json, generated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(week_start) DO UPDATE SET
          week_end = excluded.week_end,
          payload_json = excluded.payload_json,
          generated_at = excluded.generated_at
        """,
        (week_start, week_end, json.dumps(payload, sort_keys=True)),
    )
    db.commit()


def _latest_section(db: sqlite3.Connection, table: str) -> dict[str, Any] | None:
    row = db.execute(
        f"SELECT * FROM {table} ORDER BY week_start DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {"week_start": row["week_start"], "week_end": row["week_end"],
            "generated_at": row["generated_at"], "payload": payload}


def upsert_material_requirements(db: sqlite3.Connection, *, week_start: str, week_end: str, payload: dict[str, Any]) -> None:
    _upsert_section(db, "material_requirements", week_start=week_start, week_end=week_end, payload=payload)


def latest_material_requirements(db: sqlite3.Connection) -> dict[str, Any] | None:
    return _latest_section(db, "material_requirements")


def upsert_notable_products(db: sqlite3.Connection, *, week_start: str, week_end: str, payload: dict[str, Any]) -> None:
    _upsert_section(db, "notable_products", week_start=week_start, week_end=week_end, payload=payload)


def latest_notable_products(db: sqlite3.Connection) -> dict[str, Any] | None:
    return _latest_section(db, "notable_products")


def upsert_regulatory_watch(db: sqlite3.Connection, *, week_start: str, week_end: str, payload: dict[str, Any]) -> None:
    _upsert_section(db, "regulatory_watch", week_start=week_start, week_end=week_end, payload=payload)


def latest_regulatory_watch(db: sqlite3.Connection) -> dict[str, Any] | None:
    return _latest_section(db, "regulatory_watch")


def recent_embedding_memory(db: sqlite3.Connection, *, window_days: int) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
    rows = db.execute(
        """
        SELECT id, embedding
        FROM items
        WHERE status = 'included'
          AND embedding IS NOT NULL
          AND COALESCE(published_date, fetched_date) >= ?
        """,
        (cutoff,),
    )
    memory: list[dict[str, Any]] = []
    for row in rows:
        try:
            embedding = json.loads(row["embedding"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(embedding, list):
            memory.append({"id": row["id"], "embedding": embedding})
    return memory
