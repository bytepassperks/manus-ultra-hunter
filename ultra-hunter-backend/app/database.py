"""SQLite database module for storing monitoring state and alerts."""
import aiosqlite
import os
import json
from datetime import datetime
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "/data/app.db")

async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    """Initialize database tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'webpage',
                check_interval_seconds INTEGER NOT NULL DEFAULT 60,
                last_checked_at TEXT,
                last_hash TEXT,
                last_content TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                error_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                detection_type TEXT NOT NULL,
                title TEXT,
                url TEXT,
                content TEXT,
                raw_text TEXT,
                detected_fields TEXT,
                priority TEXT DEFAULT 'LOW',
                summary TEXT,
                action TEXT,
                detected_rewards TEXT,
                notified INTEGER NOT NULL DEFAULT 0,
                notified_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS content_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                content TEXT,
                items_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE INDEX IF NOT EXISTS idx_detections_source ON detections(source_id);
            CREATE INDEX IF NOT EXISTS idx_detections_priority ON detections(priority);
            CREATE INDEX IF NOT EXISTS idx_detections_notified ON detections(notified);
            CREATE INDEX IF NOT EXISTS idx_snapshots_source ON content_snapshots(source_id);
        """)
        await db.commit()
    finally:
        await db.close()


async def get_setting(key: str) -> Optional[str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_setting(key: str, value: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.utcnow().isoformat())
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_settings() -> dict:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        await db.close()


async def get_source(source_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_source_by_name(name: str) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM sources WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_all_sources(active_only: bool = False) -> list:
    db = await get_db()
    try:
        query = "SELECT * FROM sources"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def upsert_source(name: str, url: str, source_type: str = "webpage",
                        check_interval: int = 60, is_active: bool = True) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO sources (name, url, source_type, check_interval_seconds, is_active, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   url = excluded.url,
                   source_type = excluded.source_type,
                   check_interval_seconds = excluded.check_interval_seconds,
                   is_active = excluded.is_active,
                   updated_at = excluded.updated_at""",
            (name, url, source_type, check_interval, 1 if is_active else 0,
             datetime.utcnow().isoformat())
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def update_source_check(source_id: int, content_hash: str,
                              content: Optional[str] = None, error: Optional[str] = None):
    db = await get_db()
    try:
        now = datetime.utcnow().isoformat()
        if error:
            await db.execute(
                """UPDATE sources SET last_checked_at = ?, error_count = error_count + 1,
                   last_error = ?, updated_at = ? WHERE id = ?""",
                (now, error, now, source_id)
            )
        else:
            await db.execute(
                """UPDATE sources SET last_checked_at = ?, last_hash = ?, last_content = ?,
                   error_count = 0, last_error = NULL, updated_at = ? WHERE id = ?""",
                (now, content_hash, content, now, source_id)
            )
        await db.commit()
    finally:
        await db.close()


async def add_detection(source_id: int, detection_type: str, title: str,
                        url: str, content: str, raw_text: str = "",
                        detected_fields: dict = None, priority: str = "LOW",
                        summary: str = "", action: str = "",
                        detected_rewards: str = "") -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO detections (source_id, detection_type, title, url, content,
               raw_text, detected_fields, priority, summary, action, detected_rewards)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_id, detection_type, title, url, content, raw_text,
             json.dumps(detected_fields or {}), priority, summary, action, detected_rewards)
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_detections(limit: int = 50, offset: int = 0,
                         priority: Optional[str] = None,
                         source_id: Optional[int] = None) -> list:
    db = await get_db()
    try:
        query = "SELECT d.*, s.name as source_name FROM detections d LEFT JOIN sources s ON d.source_id = s.id"
        params = []
        conditions = []
        if priority:
            conditions.append("d.priority = ?")
            params.append(priority)
        if source_id:
            conditions.append("d.source_id = ?")
            params.append(source_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY d.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def mark_detection_notified(detection_id: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE detections SET notified = 1, notified_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), detection_id)
        )
        await db.commit()
    finally:
        await db.close()


async def get_unnotified_detections(priority: Optional[str] = None) -> list:
    db = await get_db()
    try:
        query = """SELECT d.*, s.name as source_name FROM detections d
                   LEFT JOIN sources s ON d.source_id = s.id
                   WHERE d.notified = 0"""
        params = []
        if priority:
            query += " AND d.priority = ?"
            params.append(priority)
        query += " ORDER BY d.created_at ASC"
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def save_snapshot(source_id: int, content_hash: str,
                        content: str, items_json: str = "[]"):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO content_snapshots (source_id, content_hash, content, items_json) VALUES (?, ?, ?, ?)",
            (source_id, content_hash, content, items_json)
        )
        await db.commit()
    finally:
        await db.close()


async def get_latest_snapshot(source_id: int) -> Optional[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM content_snapshots WHERE source_id = ? ORDER BY created_at DESC LIMIT 1",
            (source_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_detection_stats() -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT priority, COUNT(*) as count FROM detections
               GROUP BY priority"""
        )
        rows = await cursor.fetchall()
        stats = {row["priority"]: row["count"] for row in rows}

        cursor = await db.execute("SELECT COUNT(*) as total FROM detections")
        total_row = await cursor.fetchone()
        stats["total"] = total_row["total"]

        cursor = await db.execute(
            "SELECT COUNT(*) as unnotified FROM detections WHERE notified = 0"
        )
        unnotified_row = await cursor.fetchone()
        stats["unnotified"] = unnotified_row["unnotified"]

        return stats
    finally:
        await db.close()


async def delete_source(source_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM content_snapshots WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM detections WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        await db.commit()
    finally:
        await db.close()


async def seed_default_sources():
    """Seed default Manus monitoring sources."""
    default_sources = [
        ("Manus Live Events", "https://manus.im/live-events/", "webpage", 30),
        ("Manus Campaigns", "https://manus.im/campaign/", "webpage", 30),
        ("Manus Help", "https://manus.im/help/", "webpage", 180),
        ("Manus Blog", "https://manus.im/blog/", "webpage", 180),
        ("Manus Homepage", "https://manus.im/", "webpage", 120),
        ("Manus Academy Challenges", "https://academy.manus.im/challenges", "webpage", 60),
        ("Manus Events Hub", "https://events.manus.im/", "webpage", 60),
        ("Manus Twitter/X", "https://x.com/manusai", "social", 60),
        ("BuildClub Announcements", "https://buildclub.ai/events", "partner", 120),
    ]
    for name, url, stype, interval in default_sources:
        await upsert_source(name, url, stype, interval)
