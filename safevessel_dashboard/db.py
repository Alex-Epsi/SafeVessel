"""
Journal des evenements SafeVessel, stocke dans un fichier SQLite local.
Persiste entre les redemarrages du Raspberry Pi -> repond a l'axe maintenabilite.
"""
import csv
import io
import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get(
    "SAFEVESSEL_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "safevessel_logs.db"),
)

_lock = threading.Lock()


def init_db():
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                incident TEXT,
                level TEXT,
                details TEXT
            )
            """
        )
        conn.commit()


def log_event(event_type: str, incident: str, level: str, details: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO events (ts, event_type, incident, level, details) VALUES (?, ?, ?, ?, ?)",
            (ts, event_type, incident, level, details),
        )
        conn.commit()


def fetch_events(limit: int = 200):
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts, event_type, incident, level, details FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_events():
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM events")
        conn.commit()


def export_csv() -> str:
    events = fetch_events(limit=1_000_000)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["ts", "event_type", "incident", "level", "details"])
    writer.writeheader()
    for e in reversed(events):  # ordre chronologique dans l'export
        writer.writerow(e)
    return buf.getvalue()
