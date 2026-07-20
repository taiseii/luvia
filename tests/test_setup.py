import json
import sqlite3


def test_setup_creates_database_and_learner(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))

    from plugin.tools import luvia_setup

    result = luvia_setup(
        name="Taisei",
        telegram_user_id="tg-1",
        target_lang="nl",
        interests=["climbing", "techno"],
        contexts=["borrel", "office chat"],
        level="A2",
    )

    assert result["created"] is True
    user_id = result["user_id"]

    conn = sqlite3.connect(db_path)
    name, metadata_json = conn.execute(
        "SELECT name, metadata_json FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    assert name == "Taisei"
    metadata = json.loads(metadata_json)
    assert metadata["interests"] == ["climbing", "techno"]
    assert metadata["contexts"] == ["borrel", "office chat"]
    assert metadata["levels"]["nl"] == "A2"
    assert conn.execute(
        "SELECT name FROM languages WHERE code = 'nl'"
    ).fetchone() is not None


def test_setup_rerun_updates_learner_without_duplicating(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))

    from plugin.tools import luvia_setup

    first = luvia_setup(name="Taisei", telegram_user_id="tg-1", interests=["climbing"])
    second = luvia_setup(
        name="Taisei", telegram_user_id="tg-1", interests=["climbing", "techno"]
    )

    assert second["created"] is False
    assert second["user_id"] == first["user_id"]

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    metadata = json.loads(
        conn.execute("SELECT metadata_json FROM users").fetchone()[0]
    )
    assert metadata["interests"] == ["climbing", "techno"]


def test_setup_ships_full_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))

    from plugin.tools import luvia_setup

    luvia_setup(name="Taisei", telegram_user_id="tg-1")

    conn = sqlite3.connect(tmp_path / "luvia.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert tables >= {
        "users",
        "languages",
        "content_items",
        "item_tags",
        "learner_items",
        "articles",
        "sessions",
        "session_events",
        "method_profiles",
        "experiments",
        "experiment_arms",
    }


def test_state_survives_fresh_module_load(tmp_path, monkeypatch):
    """Cron runs arrive with no chat memory: a fresh process must see the
    learner purely from the SQLite file."""
    import importlib
    import sys

    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))

    from plugin.tools import luvia_setup

    first = luvia_setup(name="Taisei", telegram_user_id="tg-1")

    for module in ("plugin.tools", "plugin.store"):
        importlib.reload(sys.modules[module])
    from plugin.tools import luvia_setup as fresh_setup

    second = fresh_setup(name="Taisei", telegram_user_id="tg-1")
    assert second["created"] is False
    assert second["user_id"] == first["user_id"]
