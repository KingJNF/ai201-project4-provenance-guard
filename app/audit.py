import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "provenance.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the audit_log table if it doesn't exist."""
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id    TEXT NOT NULL,
            creator_id    TEXT,
            timestamp     TEXT NOT NULL,
            event_type    TEXT NOT NULL,
            attribution   TEXT,
            confidence    REAL,
            signals       TEXT,
            status        TEXT,
            detail        TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_entry(content_id, creator_id, event_type, attribution=None,
                confidence=None, signals=None, status=None, detail=None):
    """Write one structured entry to the audit log."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO audit_log
            (content_id, creator_id, timestamp, event_type,
             attribution, confidence, signals, status, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            content_id,
            creator_id,
            utc_now(),
            event_type,
            attribution,
            confidence,
            json.dumps(signals) if signals is not None else None,
            status,
            detail,
        ),
    )
    conn.commit()
    conn.close()


def get_log(limit=50):
    """Return the most recent audit entries, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()

    entries = []
    for r in rows:
        entries.append({
            "content_id": r["content_id"],
            "creator_id": r["creator_id"],
            "timestamp": r["timestamp"],
            "event_type": r["event_type"],
            "attribution": r["attribution"],
            "confidence": r["confidence"],
            "signals": json.loads(r["signals"]) if r["signals"] else None,
            "status": r["status"],
            "detail": r["detail"],
        })
    return entries

def get_classification(content_id):
    """Fetch the most recent classification entry for a content_id."""
    conn = _connect()
    row = conn.execute(
        """SELECT * FROM audit_log
           WHERE content_id = ? AND event_type = 'classification'
           ORDER BY id DESC LIMIT 1""",
        (content_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "content_id": row["content_id"],
        "creator_id": row["creator_id"],
        "attribution": row["attribution"],
        "confidence": row["confidence"],
        "signals": json.loads(row["signals"]) if row["signals"] else None,
        "status": row["status"],
    }


def update_status(content_id, new_status):
    """Update the status on all rows for a given content_id."""
    conn = _connect()
    conn.execute(
        "UPDATE audit_log SET status = ? WHERE content_id = ?",
        (new_status, content_id),
    )
    conn.commit()
    conn.close()