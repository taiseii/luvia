from plugin import store
from plugin.profiles import load_method_profiles


def _new_user():
    from plugin.tools import luvia_setup

    return luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")[
        "user_id"
    ]


def _load_profiles():
    conn = store.connect()
    load_method_profiles(conn)
    conn.close()


def test_set_method_persists_active_profile_across_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    _load_profiles()
    user_id = _new_user()

    from plugin.tools import luvia_set_method

    luvia_set_method(user_id=user_id, method_profile_id="communicative_hybrid")

    # Fresh call reads the choice back from SQLite alone.
    conn = store.connect()
    (metadata_json,) = conn.execute(
        "SELECT metadata_json FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    import json

    assert json.loads(metadata_json)["active_method"] == "communicative_hybrid"


def test_set_method_rejects_unknown_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    _load_profiles()
    user_id = _new_user()

    import pytest

    from plugin.tools import luvia_set_method

    with pytest.raises(ValueError):
        luvia_set_method(user_id=user_id, method_profile_id="nonexistent")

    # Rejection leaves no active_method behind.
    conn = store.connect()
    (metadata_json,) = conn.execute(
        "SELECT metadata_json FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    import json

    assert "active_method" not in json.loads(metadata_json)


def test_set_method_preserves_onboarding_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    _load_profiles()

    from plugin.tools import luvia_set_method, luvia_setup

    user_id = luvia_setup(
        name="Taisei",
        telegram_user_id="tg-1",
        target_lang="nl",
        interests=["cycling"],
        contexts=["work"],
    )["user_id"]

    luvia_set_method(user_id=user_id, method_profile_id="frequency_srs")

    conn = store.connect()
    (metadata_json,) = conn.execute(
        "SELECT metadata_json FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    import json

    metadata = json.loads(metadata_json)
    assert metadata["active_method"] == "frequency_srs"
    assert metadata["interests"] == ["cycling"]   # onboarding context intact
    assert metadata["contexts"] == ["work"]


def test_new_session_stamps_active_method(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    _load_profiles()
    user_id = _new_user()

    from plugin.tools import luvia_pick_items, luvia_set_method

    luvia_set_method(user_id=user_id, method_profile_id="communicative_hybrid")
    result = luvia_pick_items(user_id=user_id, mode="review", lang="nl")

    conn = store.connect()
    (profile_id,) = conn.execute(
        "SELECT method_profile_id FROM sessions WHERE id = ?",
        (result["session_id"],),
    ).fetchone()
    conn.close()
    assert profile_id == "communicative_hybrid"


def test_session_falls_back_to_default_without_active_method(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    user_id = _new_user()  # never calls luvia_set_method

    from plugin.tools import luvia_pick_items

    result = luvia_pick_items(user_id=user_id, mode="review", lang="nl")

    conn = store.connect()
    (profile_id,) = conn.execute(
        "SELECT method_profile_id FROM sessions WHERE id = ?",
        (result["session_id"],),
    ).fetchone()
    conn.close()
    assert profile_id == "default"
