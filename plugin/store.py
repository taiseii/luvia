"""SQLite access. All state lives in the database file; nothing is cached in
the process — every tool call reconstructs from disk (cron runs arrive with no
chat memory)."""

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = Path.home() / ".hermes" / "luvia.db"


def db_path() -> Path:
    return Path(os.environ.get("LUVIA_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn
