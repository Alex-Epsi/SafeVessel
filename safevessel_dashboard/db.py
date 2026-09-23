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
        # Migration douce : ajoute les colonnes si elles n'existent pas deja
        # (une base creee avant cette version n'a que les 6 colonnes de base).
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        if "duration_ms" not in existing_cols:
            conn.execute("ALTER TABLE events ADD COLUMN duration_ms INTEGER")
        if "escalade" not in existing_cols:
            conn.execute("ALTER TABLE events ADD COLUMN escalade INTEGER")
        conn.commit()


def log_event(event_type: str, incident: str, level: str, details: str,
              duration_ms: int = None, escalade: bool = None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    esc_val = None if escalade is None else (1 if escalade else 0)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO events (ts, event_type, incident, level, details, duration_ms, escalade) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, event_type, incident, level, details, duration_ms, esc_val),
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


def fetch_stats():
    """Agrege le journal pour la page Historique : nombre d'incidents par
    type, duree moyenne de resolution, taux d'escalade, et une chronologie
    par heure. Ne casse pas si la base est vide (renvoie des listes vides)."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        by_type = conn.execute(
            """
            SELECT
                incident,
                SUM(CASE WHEN event_type = 'DETECTION' THEN 1 ELSE 0 END) AS detections,
                AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END) AS avg_duration_ms,
                SUM(CASE WHEN escalade = 1 THEN 1 ELSE 0 END) AS escalade_count,
                SUM(CASE WHEN event_type = 'RESOLUTION' THEN 1 ELSE 0 END) AS resolutions
            FROM events
            WHERE event_type = 'DETECTION' OR event_type = 'RESOLUTION'
            GROUP BY incident
            HAVING incident IS NOT NULL AND incident != '-'
            ORDER BY detections DESC
            """
        ).fetchall()

        timeline = conn.execute(
            """
            SELECT strftime('%Y-%m-%d %H:00', ts) AS bucket, COUNT(*) AS count
            FROM events
            WHERE event_type = 'DETECTION'
            GROUP BY bucket
            ORDER BY bucket ASC
            """
        ).fetchall()

        totals = conn.execute(
            """
            SELECT
                SUM(CASE WHEN event_type = 'DETECTION' THEN 1 ELSE 0 END) AS total_detections,
                AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END) AS avg_duration_ms,
                SUM(CASE WHEN escalade = 1 THEN 1 ELSE 0 END) AS total_escalades,
                SUM(CASE WHEN event_type = 'RESOLUTION' THEN 1 ELSE 0 END) AS total_resolutions
            FROM events
            """
        ).fetchone()

    def round_or_none(v):
        return round(v) if v is not None else None

    return {
        "by_type": [
            {
                "incident": r["incident"],
                "detections": r["detections"] or 0,
                "avg_duration_ms": round_or_none(r["avg_duration_ms"]),
                "escalade_count": r["escalade_count"] or 0,
                "resolutions": r["resolutions"] or 0,
            }
            for r in by_type
        ],
        "timeline": [{"bucket": r["bucket"], "count": r["count"]} for r in timeline],
        "totals": {
            "detections": totals["total_detections"] or 0,
            "avg_duration_ms": round_or_none(totals["avg_duration_ms"]),
            "escalades": totals["total_escalades"] or 0,
            "resolutions": totals["total_resolutions"] or 0,
        },
    }
