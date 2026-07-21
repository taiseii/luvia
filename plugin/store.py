"""SQLite access. All state lives in the database file; nothing is cached in
the process — every tool call reconstructs from disk (cron runs arrive with no
chat memory)."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = Path.home() / ".hermes" / "luvia.db"

# Plugin-enforced selfie rate limits, computed in Python from logged history so
# the LLM never adjudicates its own quota. Trailing windows, same as pacing.
PROACTIVE_LIMIT = 1
PROACTIVE_WINDOW = timedelta(hours=72)
DEFAULT_REQUEST_LIMIT = 3
REQUEST_LIMIT_ENV = "LUVIA_SELFIE_REQUEST_LIMIT"
REQUEST_WINDOW = timedelta(hours=24)

SELFIE_TRIGGER_SOURCES = ("proactive", "request")


def _as_utc(dt: datetime, *, field: str) -> datetime:
    """Normalize an aware datetime to UTC; reject naive ones.

    Timestamps are stored and compared as UTC ISO 8601, so lexical string order
    matches chronological order only when every value carries the same offset. A
    naive datetime has no offset and would silently miscount across the window
    edge, so it is refused rather than guessed at."""
    if dt.tzinfo is None:
        raise ValueError(
            f"{field} must be a timezone-aware datetime, got naive {dt!r}"
        )
    return dt.astimezone(timezone.utc)


def _request_limit() -> float:
    """The on-request selfie ceiling, read from env on every call (a cron run
    reconstructs it with no chat memory, per ADR 0003).

    The proactive cap is deliberately not tunable. Only the *request* ceiling is:
    a positive int in `LUVIA_SELFIE_REQUEST_LIMIT` overrides the default, the
    sentinel `0` disables the check entirely (returns inf, so the request path
    never caps), and anything malformed — negative, non-int, empty — falls back
    to the default rather than fail open."""
    raw = os.environ.get(REQUEST_LIMIT_ENV)
    if raw is None:
        return DEFAULT_REQUEST_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REQUEST_LIMIT
    if value < 0:
        return DEFAULT_REQUEST_LIMIT
    if value == 0:
        return float("inf")
    return value


def db_path() -> Path:
    return Path(os.environ.get("LUVIA_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def log_selfie(
    conn: sqlite3.Connection,
    user_id: int,
    trigger_source: str,
    at: datetime,
) -> None:
    """Record one generated selfie for the learner at UTC time `at`.

    `trigger_source` is 'proactive' or 'request'. The row is what later quota
    reads fold over; a selfie is only logged once it has actually been produced
    (a failed generation must not consume quota). An unknown source is refused —
    a typo must never slip past a window count as an uncounted selfie."""
    if trigger_source not in SELFIE_TRIGGER_SOURCES:
        raise ValueError(
            f"unknown trigger_source {trigger_source!r};"
            f" expected one of {SELFIE_TRIGGER_SOURCES}"
        )
    at = _as_utc(at, field="selfie timestamp")
    conn.execute(
        "INSERT INTO selfie_log (user_id, trigger_source, created_at)"
        " VALUES (?, ?, ?)",
        (user_id, trigger_source, at.isoformat()),
    )
    conn.commit()


def _selfies_in_window(
    conn: sqlite3.Connection,
    user_id: int,
    trigger_source: str,
    since: datetime,
) -> int:
    """Count the learner's selfies of one source strictly newer than `since`.

    A row exactly on the window edge has aged out (strict >), so the allowance
    it consumed is restored at the boundary."""
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM selfie_log WHERE user_id = ? AND trigger_source = ?"
        " AND created_at > ?",
        (user_id, trigger_source, since.isoformat()),
    ).fetchone()
    return count


def selfie_allowance(
    conn: sqlite3.Connection,
    user_id: int,
    now: datetime,
) -> dict:
    """Remaining selfies the learner may take per source, from logged history alone.

    Proactive <= 1 per rolling 72h (a fixed hard bound). On-request <= a
    configurable ceiling per rolling 24h (default 3, tunable via env — see
    `_request_limit`); when the ceiling is disabled the request value is `inf`.
    Recomputed from the SQLite file on every call — a cron run reconstructs it
    with no chat memory. Never negative even if history somehow exceeds a limit."""
    now = _as_utc(now, field="now")
    proactive_used = _selfies_in_window(
        conn, user_id, "proactive", now - PROACTIVE_WINDOW
    )
    request_used = _selfies_in_window(
        conn, user_id, "request", now - REQUEST_WINDOW
    )
    return {
        "proactive": max(0, PROACTIVE_LIMIT - proactive_used),
        "request": max(0, _request_limit() - request_used),
    }
