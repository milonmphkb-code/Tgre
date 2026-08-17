"""
SQLite database layer.
Handles all persistence: sources, destinations, posts (dup check), settings, logs, stats.
Uses plain sqlite3 with a small connection-per-call pattern (fine for this bot's throughput).
"""
import sqlite3
import json
import time
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_url TEXT NOT NULL UNIQUE,
    channel_id INTEGER,               -- resolved Telegram channel id (filled after first sync)
    channel_name TEXT,
    destination_id INTEGER,           -- FK -> destinations.id
    is_active INTEGER NOT NULL DEFAULT 1,
    delay_seconds INTEGER NOT NULL DEFAULT 0,
    personal_data_filter INTEGER NOT NULL DEFAULT 1,
    keyword_mode TEXT NOT NULL DEFAULT 'none',   -- none | whitelist | blacklist
    keywords TEXT NOT NULL DEFAULT '[]',          -- JSON list
    word_remove TEXT NOT NULL DEFAULT '[]',        -- JSON list
    word_replace TEXT NOT NULL DEFAULT '{}',       -- JSON dict {old: new}
    line_remove TEXT NOT NULL DEFAULT '[]',        -- JSON list of substrings; matching lines removed
    footer TEXT NOT NULL DEFAULT '',
    hashtags TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL UNIQUE,   -- Telegram chat id of destination channel (bot must be admin there)
    channel_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    source_post_id INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    destination_post_id INTEGER,
    status TEXT NOT NULL,          -- posted | skipped | duplicate | filtered | failed
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_hash ON posts(content_hash);
CREATE INDEX IF NOT EXISTS idx_posts_source_post ON posts(source_id, source_post_id);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,      -- INFO | ERROR
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- Sources ----------

def add_source(channel_url: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sources (channel_url, created_at) VALUES (?, ?)",
            (channel_url, int(time.time())),
        )
        return cur.lastrowid


def remove_source(source_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM posts WHERE source_id = ?", (source_id,))


def list_sources():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM sources ORDER BY id").fetchall()


def get_source(source_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()


def get_source_by_channel_id(channel_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sources WHERE channel_id = ?", (channel_id,)
        ).fetchone()


def update_source_channel_info(source_id: int, channel_id: int, channel_name: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET channel_id = ?, channel_name = ? WHERE id = ?",
            (channel_id, channel_name, source_id),
        )


def set_source_active(source_id: int, active: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET is_active = ? WHERE id = ?", (1 if active else 0, source_id)
        )


def set_source_destination(source_id: int, destination_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET destination_id = ? WHERE id = ?", (destination_id, source_id)
        )


def set_source_delay(source_id: int, seconds: int):
    with get_conn() as conn:
        conn.execute("UPDATE sources SET delay_seconds = ? WHERE id = ?", (seconds, source_id))


def set_source_field_json(source_id: int, field: str, value):
    assert field in {"keywords", "word_remove", "word_replace", "line_remove"}
    with get_conn() as conn:
        conn.execute(
            f"UPDATE sources SET {field} = ? WHERE id = ?",
            (json.dumps(value, ensure_ascii=False), source_id),
        )


def set_source_keyword_mode(source_id: int, mode: str):
    assert mode in {"none", "whitelist", "blacklist"}
    with get_conn() as conn:
        conn.execute("UPDATE sources SET keyword_mode = ? WHERE id = ?", (mode, source_id))


def set_source_footer(source_id: int, footer: str):
    with get_conn() as conn:
        conn.execute("UPDATE sources SET footer = ? WHERE id = ?", (footer, source_id))


def set_source_hashtags(source_id: int, hashtags: str):
    with get_conn() as conn:
        conn.execute("UPDATE sources SET hashtags = ? WHERE id = ?", (hashtags, source_id))


def set_personal_data_filter(source_id: int, enabled: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sources SET personal_data_filter = ? WHERE id = ?",
            (1 if enabled else 0, source_id),
        )


# ---------- Destinations ----------

def add_destination(channel_id: int, channel_name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO destinations (channel_id, channel_name, created_at) "
            "VALUES (?, ?, ?)",
            (channel_id, channel_name, int(time.time())),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM destinations WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return row["id"]


def list_destinations():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM destinations ORDER BY id").fetchall()


def get_destination(destination_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM destinations WHERE id = ?", (destination_id,)
        ).fetchone()


# ---------- Posts / duplicate check ----------

def is_duplicate(content_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM posts WHERE content_hash = ? AND status = 'posted' LIMIT 1",
            (content_hash,),
        ).fetchone()
        return row is not None


def was_already_processed(source_id: int, source_post_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM posts WHERE source_id = ? AND source_post_id = ? LIMIT 1",
            (source_id, source_post_id),
        ).fetchone()
        return row is not None


def record_post(source_id, source_post_id, content_hash, destination_post_id, status):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO posts (source_id, source_post_id, content_hash, "
            "destination_post_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, source_post_id, content_hash, destination_post_id, status, int(time.time())),
        )


# ---------- Logs ----------

def add_log(level: str, message: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (level, message, created_at) VALUES (?, ?, ?)",
            (level, message, int(time.time())),
        )


def recent_logs(limit: int = 20):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


# ---------- Global pause state ----------

def set_state(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_state(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


# ---------- Stats ----------

def get_stats():
    with get_conn() as conn:
        total_sources = conn.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"]
        total_detected = conn.execute("SELECT COUNT(*) c FROM posts").fetchone()["c"]
        total_posted = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'posted'"
        ).fetchone()["c"]
        total_skipped = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'skipped'"
        ).fetchone()["c"]
        total_duplicate = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'duplicate'"
        ).fetchone()["c"]
        total_filtered = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'filtered'"
        ).fetchone()["c"]
        total_errors = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'failed'"
        ).fetchone()["c"]
        day_ago = int(time.time()) - 86400
        today_posts = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'posted' AND created_at >= ?",
            (day_ago,),
        ).fetchone()["c"]
        week_ago = int(time.time()) - 7 * 86400
        week_posts = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status = 'posted' AND created_at >= ?",
            (week_ago,),
        ).fetchone()["c"]
        return {
            "total_sources": total_sources,
            "total_detected": total_detected,
            "total_posted": total_posted,
            "total_skipped": total_skipped,
            "total_duplicate": total_duplicate,
            "total_filtered": total_filtered,
            "total_errors": total_errors,
            "today_posts": today_posts,
            "week_posts": week_posts,
        }
