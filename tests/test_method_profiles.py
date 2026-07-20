import yaml

from plugin import store
from plugin.profiles import load_method_profiles


def test_load_ships_both_phase1_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()

    loaded = load_method_profiles(conn)

    assert set(loaded) == {"frequency_srs", "communicative_hybrid"}
    rows = dict(conn.execute("SELECT id, label FROM method_profiles").fetchall())
    assert rows == {
        "frequency_srs": "Frequency SRS",
        "communicative_hybrid": "Communicative Hybrid",
    }


def test_communicative_hybrid_declares_informal_mix_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()
    load_method_profiles(conn)

    (config_yaml,) = conn.execute(
        "SELECT config_yaml FROM method_profiles WHERE id = 'communicative_hybrid'"
    ).fetchone()
    config = yaml.safe_load(config_yaml)

    assert config["register"] == "informal"
    assert config["language_mix"] == "adaptive"
    # Only the input signals are declared; the mixing logic that turns them into a
    # Dutch ratio is out of scope for this profile.
    assert isinstance(config["language_mix_signals"], list)
    assert config["language_mix_signals"]


def test_frequency_srs_config_is_valid_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()
    load_method_profiles(conn)

    (config_yaml,) = conn.execute(
        "SELECT config_yaml FROM method_profiles WHERE id = 'frequency_srs'"
    ).fetchone()
    config = yaml.safe_load(config_yaml)

    assert "mechanism_weights" in config
    assert config["mechanism_weights"]["retrieval"] > 0


def test_second_load_does_not_duplicate_or_bump_version(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()

    load_method_profiles(conn)
    before = conn.execute(
        "SELECT id, version FROM method_profiles ORDER BY id"
    ).fetchall()

    load_method_profiles(conn)
    after = conn.execute(
        "SELECT id, version FROM method_profiles ORDER BY id"
    ).fetchall()

    assert conn.execute("SELECT COUNT(*) FROM method_profiles").fetchone()[0] == 2
    assert before == after  # no duplicate rows, no spurious version bump
