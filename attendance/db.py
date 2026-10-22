import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS maid (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    monthly_salary REAL NOT NULL,
    paid_leaves_per_month INTEGER NOT NULL DEFAULT 2,
    active INTEGER NOT NULL DEFAULT 1
);
-- Other spellings of a maid's name (for example Devanagari) so voice commands find her.
CREATE TABLE IF NOT EXISTS maid_alias (
    maid_id INTEGER NOT NULL REFERENCES maid(id),
    alias TEXT NOT NULL,
    PRIMARY KEY (maid_id, alias)
);
-- One row per maid per day; status is 'present' or 'leave'.
CREATE TABLE IF NOT EXISTS attendance (
    maid_id INTEGER NOT NULL REFERENCES maid(id),
    day TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('present', 'leave')),
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (maid_id, day)
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def open_db(path):
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
