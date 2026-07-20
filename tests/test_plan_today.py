import sqlite3
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _new_user():
    from plugin.tools import luvia_setup

    return luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")[
        "user_id"
    ]


def _add_due_item(conn, user_id, surface, due_at):
    item_id = conn.execute(
        "INSERT INTO content_items (lang, item_type, surface)"
        " VALUES ('nl', 'lemma', ?)",
        (surface,),
    ).lastrowid
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id, status, due_at)"
        " VALUES (?, ?, 'review', ?)",
        (user_id, item_id, due_at),
    )
    return item_id


def test_plan_today_fresh_learner_uses_starting_band(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    past = (NOW - timedelta(days=1)).isoformat()
    for surface in ("het huis", "de kat", "de hond"):
        _add_due_item(conn, user_id, surface, due_at=past)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_plan_today

    plan = luvia_plan_today(user_id=user_id, lang="nl", now=NOW)

    assert plan["band"] == 50               # no history -> starting band
    assert plan["new_intake"] == 7          # round(50 / 7), guaranteed allotment
    assert plan["due_load"] == 3            # three items due, under the ceiling
    assert plan["overflow"] == 0
    assert plan["mode_balance"] == {"review": 3, "ambient": 7}


def _seed_week_of_events(conn, user_id, grade, days_ago_start=8, count=6):
    """Insert `count` events on consecutive days inside one completed week."""
    session_id = conn.execute(
        "INSERT INTO sessions (user_id, lang, mode, method_profile_id, started_at)"
        " VALUES (?, 'nl', 'review', 'default', ?)",
        (user_id, (NOW - timedelta(days=days_ago_start)).isoformat()),
    ).lastrowid
    for i in range(count):
        ts = (NOW - timedelta(days=days_ago_start + i)).isoformat()
        conn.execute(
            "INSERT INTO session_events (session_id, event_index, mechanism, grade,"
            " created_at) VALUES (?, ?, 'flashcard', ?, ?)",
            (session_id, i, grade, ts),
        )


def test_sweeps_excluded_from_band_consumption(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    # A full completed week of nothing but fast-track sweeps.
    _seed_week_of_events(conn, user_id, grade="already_knew")
    conn.commit()
    conn.close()

    from plugin.tools import luvia_plan_today

    plan = luvia_plan_today(user_id=user_id, lang="nl", now=NOW)

    # Sweeps look like activity but carry no recall signal: band holds at start.
    assert plan["band"] == 50


def test_genuine_strong_week_ratchets_band_up(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    _seed_week_of_events(conn, user_id, grade="good")
    conn.commit()
    conn.close()

    from plugin.tools import luvia_plan_today

    plan = luvia_plan_today(user_id=user_id, lang="nl", now=NOW)

    # Perfect recall over an active week: +10.
    assert plan["band"] == 60
