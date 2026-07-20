import sqlite3
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _new_user(target_lang="nl"):
    from plugin.tools import luvia_setup

    return luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang=target_lang)[
        "user_id"
    ]


def _add_content(conn, surface, lang="nl", frequency_rank=None):
    return conn.execute(
        "INSERT INTO content_items (lang, item_type, surface, frequency_rank)"
        " VALUES (?, 'lemma', ?, ?)",
        (lang, surface, frequency_rank),
    ).lastrowid


def _add_learner_item(conn, user_id, item_id, due_at, status="review"):
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id, status, due_at)"
        " VALUES (?, ?, ?, ?)",
        (user_id, item_id, status, due_at),
    )


def test_review_mode_returns_due_items_capped_at_batch_size(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    past = (NOW - timedelta(days=1)).isoformat()
    for surface in ("het huis", "de kat", "de hond"):
        item_id = _add_content(conn, surface)
        _add_learner_item(conn, user_id, item_id, due_at=past)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_pick_items

    batch = luvia_pick_items(user_id=user_id, mode="review", lang="nl",
                             batch_size=2, now=NOW)

    assert len(batch["items"]) == 2
    assert {i["source"] for i in batch["items"]} == {"due"}


def test_new_intake_excludes_items_learner_has_state_for(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    # One item the learner already has state for; it must never be offered as new.
    seen = _add_content(conn, "het huis")
    _add_learner_item(conn, user_id, seen, due_at=None, status="known")
    fresh = {_add_content(conn, s) for s in ("de kat", "de hond", "de vis")}
    conn.commit()
    conn.close()

    from plugin.tools import luvia_pick_items

    batch = luvia_pick_items(user_id=user_id, mode="ambient", lang="nl", now=NOW)

    new_ids = {i["item_id"] for i in batch["items"] if i["source"] == "new"}
    assert seen not in new_ids
    assert new_ids <= fresh
    assert len(new_ids) == 3  # all three fresh items, under the band/batch cap


def test_ambient_mixes_due_and_new_without_duplicates(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    past = (NOW - timedelta(days=1)).isoformat()
    for surface in ("het huis", "de kat"):
        _add_learner_item(conn, user_id, _add_content(conn, surface), due_at=past)
    for surface in ("de hond", "de vis", "de boom"):
        _add_content(conn, surface)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_pick_items

    batch = luvia_pick_items(user_id=user_id, mode="ambient", lang="nl", now=NOW)

    sources = [i["source"] for i in batch["items"]]
    assert sources.count("due") == 2
    assert sources.count("new") == 3  # fills remaining micro-batch slots from band
    ids = [i["item_id"] for i in batch["items"]]
    assert len(ids) == len(set(ids))  # no item offered twice in a batch


def test_ambient_new_intake_governed_by_band(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    conn = sqlite3.connect(db_path)
    for surface in ("de kat", "de hond", "de vis", "de boom", "de tafel", "de stoel"):
        _add_content(conn, surface)
    conn.commit()
    conn.close()

    from plugin.tools import luvia_pick_items

    batch = luvia_pick_items(user_id=user_id, mode="ambient", lang="nl", now=NOW)

    # Starting band 50 -> ~7 new/day, capped by the ambient micro-batch size (5).
    new_ids = [i for i in batch["items"] if i["source"] == "new"]
    assert len(new_ids) == 5


def test_activity_within_gap_shares_one_session(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    from plugin.tools import luvia_pick_items

    first = luvia_pick_items(user_id=user_id, mode="review", lang="nl", now=NOW)
    second = luvia_pick_items(
        user_id=user_id, mode="review", lang="nl", now=NOW + timedelta(minutes=20)
    )

    assert first["session_id"] == second["session_id"]

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, mode FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchall()
    assert rows == [(first["session_id"], "review")]


def test_activity_after_gap_opens_new_session(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()

    from plugin.tools import luvia_pick_items

    first = luvia_pick_items(user_id=user_id, mode="review", lang="nl", now=NOW)
    later = NOW + timedelta(minutes=31)
    second = luvia_pick_items(user_id=user_id, mode="review", lang="nl", now=later)

    assert first["session_id"] != second["session_id"]

    conn = sqlite3.connect(db_path)
    # Old burst is closed at its last activity; the new one is still open.
    ended_first = conn.execute(
        "SELECT ended_at FROM sessions WHERE id = ?", (first["session_id"],)
    ).fetchone()[0]
    ended_second = conn.execute(
        "SELECT ended_at FROM sessions WHERE id = ?", (second["session_id"],)
    ).fetchone()[0]
    assert ended_first == NOW.isoformat()
    assert ended_second is None
    assert conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()[0] == 2
