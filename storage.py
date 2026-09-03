"""
Simple SQLite storage for everything the bot collects during the day.
Each row is one 'item' — a message, event, or livestream detection —
tagged with a category so the daily digest can group them.
"""

import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = "reports.db"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_name TEXT,
            channel_name TEXT,
            category TEXT,
            author TEXT,
            content TEXT,
            url TEXT,
            created_at TEXT,
            sent INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


@contextmanager
def get_conn(path=DB_PATH):
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def add_item(guild_name, channel_name, category, author, content, url, path=DB_PATH):
    with get_conn(path) as conn:
        conn.execute(
            """
            INSERT INTO items (guild_name, channel_name, category, author, content, url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_name,
                channel_name,
                category,
                author,
                content,
                url,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def get_unsent_items(path=DB_PATH):
    with get_conn(path) as conn:
        cur = conn.execute(
            """
            SELECT id, guild_name, channel_name, category, author, content, url, created_at
            FROM items
            WHERE sent = 0
            ORDER BY category, guild_name, created_at
            """
        )
        return cur.fetchall()


def mark_all_sent(ids, path=DB_PATH):
    if not ids:
        return
    with get_conn(path) as conn:
        conn.executemany("UPDATE items SET sent = 1 WHERE id = ?", [(i,) for i in ids])
        conn.commit()
