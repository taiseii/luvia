import sqlite3
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _seed_learner_item(db_path):
    from plugin.tools import luvia_setup

    user_id = luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")[
        "user_id"
    ]
    conn = sqlite3.connect(db_path)
    item_id = conn.execute(
        "INSERT INTO content_items (lang, item_type, surface)"
        " VALUES ('nl', 'lemma', 'het huis')"
    ).lastrowid
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id) VALUES (?, ?)",
        (user_id, item_id),
    )
    conn.commit()
    conn.close()
    return user_id, item_id


def test_record_without_session_id_attaches_to_current_burst(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id = _seed_learner_item(db_path)

    from plugin.tools import luvia_record_result

    first = luvia_record_result(
        user_id=user_id, item_id=item_id, lang="nl", mode="review",
        grade="good", mechanism="flashcard", now=NOW,
    )
    second = luvia_record_result(
        user_id=user_id, item_id=item_id, lang="nl", mode="review",
        grade="good", mechanism="flashcard", now=NOW + timedelta(minutes=10),
    )

    assert first["session_id"] == second["session_id"]

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM session_events WHERE session_id = ?",
        (first["session_id"],),
    ).fetchone()[0] == 2


def test_record_after_gap_opens_new_burst(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id = _seed_learner_item(db_path)

    from plugin.tools import luvia_record_result

    first = luvia_record_result(
        user_id=user_id, item_id=item_id, lang="nl", mode="review",
        grade="good", mechanism="flashcard", now=NOW,
    )
    second = luvia_record_result(
        user_id=user_id, item_id=item_id, lang="nl", mode="review",
        grade="good", mechanism="flashcard", now=NOW + timedelta(minutes=31),
    )

    assert first["session_id"] != second["session_id"]
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2
