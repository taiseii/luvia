"""Selfie quota helpers: window-driven reads over the selfie_log table.

Mirrors the trailing-window style of test_pacing / test_plan_today. Every verdict
is recomputed from the SQLite file alone — a cron run arrives with no chat memory,
so the fixtures drive selfie_log rows across time and assert the quota at its edges.
"""

from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _connect(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    from plugin import store

    conn = store.connect()
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'Taisei')")
    conn.commit()
    return conn


def test_log_selfie_writes_a_row(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    store.log_selfie(conn, user_id=1, trigger_source="request", at=NOW)

    rows = conn.execute(
        "SELECT user_id, trigger_source, created_at FROM selfie_log"
    ).fetchall()
    assert rows == [(1, "request", NOW.isoformat())]


def test_fresh_learner_has_full_allowance(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)

    assert store.selfie_allowance(conn, user_id=1, now=NOW) == {
        "proactive": 1,
        "request": 3,
    }


def test_proactive_capped_within_rolling_72h(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    # One proactive selfie just inside the 72h window blocks the next.
    store.log_selfie(conn, 1, "proactive", NOW - timedelta(hours=71))

    assert store.selfie_allowance(conn, 1, NOW)["proactive"] == 0


def test_proactive_allowance_restored_at_72h_edge(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    # A proactive selfie exactly 72h ago has aged out of the trailing window.
    store.log_selfie(conn, 1, "proactive", NOW - timedelta(hours=72))

    assert store.selfie_allowance(conn, 1, NOW)["proactive"] == 1


def test_request_capped_at_three_within_rolling_24h(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    for hours in (1, 5, 23):
        store.log_selfie(conn, 1, "request", NOW - timedelta(hours=hours))

    assert store.selfie_allowance(conn, 1, NOW)["request"] == 0


def test_request_allowance_counts_only_the_trailing_24h(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    store.log_selfie(conn, 1, "request", NOW - timedelta(hours=2))
    store.log_selfie(conn, 1, "request", NOW - timedelta(hours=10))
    # Exactly 24h ago: aged out at the edge, does not consume allowance.
    store.log_selfie(conn, 1, "request", NOW - timedelta(hours=24))

    assert store.selfie_allowance(conn, 1, NOW)["request"] == 1


def test_sources_are_counted_independently(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    store.log_selfie(conn, 1, "proactive", NOW - timedelta(hours=1))

    allowance = store.selfie_allowance(conn, 1, NOW)
    assert allowance["proactive"] == 0  # proactive spent
    assert allowance["request"] == 3    # request untouched


def test_allowance_is_per_learner(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'Ana')")
    conn.commit()
    store.log_selfie(conn, 1, "proactive", NOW - timedelta(hours=1))

    # Learner 2's window is untouched by learner 1's history.
    assert store.selfie_allowance(conn, 2, NOW)["proactive"] == 1


def test_quota_recomputes_from_the_database_file(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    store.log_selfie(conn, 1, "request", NOW - timedelta(hours=1))
    conn.close()

    # A fresh connection (cron run, no chat memory) reads the same verdict from disk.
    conn2 = store.connect()
    assert store.selfie_allowance(conn2, 1, NOW)["request"] == 2
