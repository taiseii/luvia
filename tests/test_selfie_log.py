"""Selfie quota helpers: window-driven reads over the selfie_log table.

Mirrors the trailing-window style of test_pacing / test_plan_today. Every verdict
is recomputed from the SQLite file alone — a cron run arrives with no chat memory,
so the fixtures drive selfie_log rows across time and assert the quota at its edges.
"""

from datetime import datetime, timedelta, timezone

import pytest

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


def test_non_utc_offset_input_is_counted_by_real_instant(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    tz_plus2 = timezone(timedelta(hours=2))

    # 2026-07-19T11:00+02:00 == 2026-07-19T09:00Z, which is 25h before NOW: OUTSIDE
    # the 24h window. Its lexical string "2026-07-19T11..." sorts AFTER the window
    # boundary "2026-07-19T10:00+00:00", so a raw-string compare would miscount it
    # as inside. The real instant is what must decide.
    outside = datetime(2026, 7, 19, 11, 0, tzinfo=tz_plus2)
    store.log_selfie(conn, 1, "request", outside)
    assert store.selfie_allowance(conn, 1, NOW)["request"] == 3

    # 2026-07-20T11:30+02:00 == 2026-07-20T09:30Z, 30 min before NOW: INSIDE.
    inside = datetime(2026, 7, 20, 11, 30, tzinfo=tz_plus2)
    store.log_selfie(conn, 1, "request", inside)
    assert store.selfie_allowance(conn, 1, NOW)["request"] == 2


def test_non_utc_now_is_evaluated_by_real_instant(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    store.log_selfie(conn, 1, "proactive", NOW - timedelta(hours=1))

    # Same instant as NOW, expressed at +02:00. The proactive spent an hour ago
    # must still register regardless of the offset carried by `now`.
    now_plus2 = NOW.astimezone(timezone(timedelta(hours=2)))
    assert store.selfie_allowance(conn, 1, now_plus2)["proactive"] == 0


def test_naive_timestamp_is_rejected(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    naive = datetime(2026, 7, 20, 10, 0)  # no tzinfo

    with pytest.raises(ValueError):
        store.log_selfie(conn, 1, "request", naive)
    # Nothing was written: a rejected timestamp consumes no quota.
    assert conn.execute("SELECT COUNT(*) FROM selfie_log").fetchone()[0] == 0


def test_naive_now_is_rejected(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        store.selfie_allowance(conn, 1, datetime(2026, 7, 20, 10, 0))


def test_unknown_trigger_source_is_rejected_and_writes_nothing(tmp_path, monkeypatch):
    from plugin import store

    conn = _connect(tmp_path, monkeypatch)

    # A typo'd source must not slip through as an uncounted selfie (silent bypass).
    with pytest.raises(ValueError):
        store.log_selfie(conn, 1, "on_request", NOW)
    assert conn.execute("SELECT COUNT(*) FROM selfie_log").fetchone()[0] == 0
