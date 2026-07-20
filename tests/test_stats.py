import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _new_user():
    from plugin.tools import luvia_setup

    return luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")[
        "user_id"
    ]


def _content_item(conn, surface, lang="nl"):
    return conn.execute(
        "INSERT INTO content_items (lang, item_type, surface) VALUES (?, 'lemma', ?)",
        (lang, surface),
    ).lastrowid


def _track_item(conn, user_id, item_id, status, due_at):
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id, status, due_at)"
        " VALUES (?, ?, ?, ?)",
        (user_id, item_id, status, due_at),
    )


def _session(conn, user_id, started_at, lang="nl", mode="review"):
    return conn.execute(
        "INSERT INTO sessions (user_id, lang, mode, method_profile_id, started_at)"
        " VALUES (?, ?, ?, 'default', ?)",
        (user_id, lang, mode, started_at),
    ).lastrowid


def _event(conn, session_id, index, grade, created_at, item_id=None):
    conn.execute(
        "INSERT INTO session_events (session_id, event_index, mechanism, item_id,"
        " grade, created_at) VALUES (?, ?, 'flashcard', ?, ?, ?)",
        (session_id, index, item_id, grade, created_at),
    )


def test_stats_fresh_learner(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    # A small unencountered corpus the sweep has not reached yet.
    for surface in ("het huis", "de kat", "de hond"):
        _content_item(conn, surface)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_stats

    stats = luvia_stats(user_id=user_id, lang="nl", now=NOW)

    assert stats["recall"]["rate"] is None          # no genuine reviews yet
    assert stats["recall"]["reviews"] == 0
    assert stats["sweep"] == {"swept": 0, "remaining": 3}
    assert stats["band"]["position"] == 50          # starting band, no history
    assert stats["band"]["daily_new_intake"] == 7   # round(50 / 7)
    assert stats["due"] == {"due_now": 0, "tracked": 0}


def test_stats_mid_sweep(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    yesterday = (NOW - timedelta(days=1)).isoformat()
    session_id = _session(conn, user_id, started_at=yesterday)
    far = (NOW + timedelta(days=30)).isoformat()  # fast-tracked ~30 days out
    for i, surface in enumerate(("ik", "jij", "hij")):
        item_id = _content_item(conn, surface)
        _track_item(conn, user_id, item_id, status="review", due_at=far)
        _event(conn, session_id, i, grade="already_knew", created_at=yesterday,
               item_id=item_id)
    # Two words still ahead of the sweep.
    for surface in ("de tafel", "de stoel"):
        _content_item(conn, surface)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_stats

    stats = luvia_stats(user_id=user_id, lang="nl", now=NOW)

    # already_knew sweeps carry no recall signal — excluded like the pacing band.
    assert stats["recall"]["rate"] is None
    assert stats["recall"]["reviews"] == 0
    assert stats["sweep"] == {"swept": 3, "remaining": 2}
    assert stats["band"]["position"] == 50          # sweeps never ratchet the band
    assert stats["due"]["due_now"] == 0             # all fast-tracked well ahead
    assert stats["due"]["tracked"] == 3


def _seed_completed_strong_week(conn, user_id):
    """Six perfect-recall reviews across a completed week -> +10 ratchet."""
    session_id = _session(conn, user_id, started_at=(NOW - timedelta(days=8)).isoformat())
    for i in range(6):
        ts = (NOW - timedelta(days=8 + i)).isoformat()
        _event(conn, session_id, i, grade="good", created_at=ts)


def test_stats_ratcheted_band(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    _seed_completed_strong_week(conn, user_id)
    # A current-week slip that colours recall but does not ratchet the band.
    recent = (NOW - timedelta(hours=1)).isoformat()
    current = _session(conn, user_id, started_at=recent)
    _event(conn, current, 0, grade="again", created_at=recent)
    # Three items due for review right now.
    past = (NOW - timedelta(days=1)).isoformat()
    for surface in ("lopen", "eten", "drinken"):
        item_id = _content_item(conn, surface)
        _track_item(conn, user_id, item_id, status="review", due_at=past)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_stats

    stats = luvia_stats(user_id=user_id, lang="nl", now=NOW)

    assert stats["band"]["position"] == 60          # strong completed week: +10
    assert stats["band"]["daily_new_intake"] == 9   # round(60 / 7)
    # 6 correct across 7 genuine reviews (already_knew never counted).
    assert stats["recall"]["reviews"] == 7
    assert stats["recall"]["correct"] == 6
    assert stats["recall"]["rate"] == pytest.approx(6 / 7)
    assert stats["due"] == {"due_now": 3, "tracked": 3}
