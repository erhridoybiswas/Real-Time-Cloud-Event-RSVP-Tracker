"""
Database layer.

Design notes
------------
* SQLite is used for the local/student deployment. The same schema and the
  same `transaction()` contract map 1:1 onto PostgreSQL (`SELECT ... FOR UPDATE`).
* `isolation_level=None` puts the driver in autocommit mode so that WE control
  transaction boundaries explicitly. This is what lets us use BEGIN IMMEDIATE.
* `BEGIN IMMEDIATE` acquires a RESERVED write lock at the *start* of the
  transaction. That serialises all writers, which is exactly what makes the
  "check capacity, then insert" sequence safe against race conditions.
"""
import os
import sqlite3
from contextlib import contextmanager

from .config import Config

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'ATTENDEE'
                          CHECK (role IN ('ATTENDEE','ORGANIZER','ADMIN')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organizer_id          INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_name            TEXT    NOT NULL,
    description           TEXT    DEFAULT '',
    event_type            TEXT    DEFAULT 'GENERAL',
    event_date            TEXT    NOT NULL,
    start_time            TEXT    NOT NULL,
    end_time              TEXT    NOT NULL,
    venue                 TEXT    DEFAULT '',
    online_link           TEXT    DEFAULT '',
    maximum_capacity      INTEGER NOT NULL CHECK (maximum_capacity > 0),
    registration_deadline TEXT,
    status                TEXT    NOT NULL DEFAULT 'DRAFT'
                                  CHECK (status IN ('DRAFT','PUBLISHED','FULL','COMPLETED','CANCELLED')),
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rsvps (
    rsvp_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    status       TEXT    NOT NULL CHECK (status IN ('GOING','MAYBE','NOT_GOING')),
    responded_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, user_id)          -- one active RSVP per user per event
);

CREATE TABLE IF NOT EXISTS waitlist (
    waitlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    joined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    status      TEXT    NOT NULL DEFAULT 'WAITING'
                        CHECK (status IN ('WAITING','PROMOTED','CANCELLED')),
    UNIQUE (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS invites (
    invite_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS announcements (
    announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    event_id        INTEGER REFERENCES events(event_id)          ON DELETE CASCADE,
    type            TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    read            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id   INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes tuned for the hot paths -----------------------------------------
CREATE INDEX IF NOT EXISTS idx_events_status_date   ON events(status, event_date);
CREATE INDEX IF NOT EXISTS idx_events_organizer     ON events(organizer_id);
CREATE INDEX IF NOT EXISTS idx_rsvps_event_status   ON rsvps(event_id, status);
CREATE INDEX IF NOT EXISTS idx_rsvps_user           ON rsvps(user_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_event       ON waitlist(event_id, status, joined_at);
CREATE INDEX IF NOT EXISTS idx_notif_user_read      ON notifications(user_id, read);
CREATE INDEX IF NOT EXISTS idx_ann_event            ON announcements(event_id, created_at);
"""


# --------------------------------------------------------------------------
# Connection handling
# --------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Open a tuned SQLite connection (one per call — cheap and thread-safe)."""
    db_path = Config.DATABASE_PATH
    directory = os.path.dirname(os.path.abspath(db_path))
    if directory:
        os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(
        db_path,
        timeout=30.0,
        isolation_level=None,      # autocommit; we manage transactions ourselves
        check_same_thread=False,   # SSE + threaded dev server
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")     # readers never block the writer
    conn.execute("PRAGMA busy_timeout = 30000")   # wait up to 30s for the lock
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction():
    """
    Explicit write transaction.

    `BEGIN IMMEDIATE` grabs the RESERVED lock immediately, so two concurrent
    "is the event full?" checks can never both succeed. This is the SQLite
    equivalent of PostgreSQL's `SELECT ... FOR UPDATE` on the event row.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Convenience helpers (read paths + trivial writes)
# --------------------------------------------------------------------------
def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    """Run a single write statement inside its own transaction."""
    with transaction() as conn:
        cursor = conn.execute(sql, params)
        return cursor.lastrowid


def init_db() -> None:
    """Create tables/indexes if they do not exist."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def healthcheck() -> bool:
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except sqlite3.Error:
        return False