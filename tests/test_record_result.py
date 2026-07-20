import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

LEARNER_ITEM_COLUMNS = {
    "user_id",
    "item_id",
    "status",
    "due_at",
    "last_seen_at",
    "last_score",
    "success_count",
    "failure_count",
    "scheduler_state_json",
    "listening_score",
    "speaking_score",
    "reading_score",
    "writing_score",
    "notes",
}


def _seed(db_path):
    """Create a user, content item, learner item, and open session; return ids."""
    from plugin.tools import luvia_setup

    user = luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")
    user_id = user["user_id"]
    conn = sqlite3.connect(db_path)
    item_id = conn.execute(
        "INSERT INTO content_items (lang, item_type, surface)"
        " VALUES ('nl', 'lemma', 'het huis')"
    ).lastrowid
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id) VALUES (?, ?)",
        (user_id, item_id),
    )
    session_id = conn.execute(
        "INSERT INTO sessions (user_id, lang, mode, method_profile_id, started_at)"
        " VALUES (?, 'nl', 'review', 'default', ?)",
        (user_id, "2026-07-20T10:00:00+00:00"),
    ).lastrowid
    conn.commit()
    conn.close()
    return user_id, item_id, session_id


def test_record_result_logs_event_and_reschedules(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="good",
        mechanism="flashcard",
        now=now,
    )

    conn = sqlite3.connect(db_path)
    (grade,) = conn.execute(
        "SELECT grade FROM session_events WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert grade == "good"

    due_at, state_json = conn.execute(
        "SELECT due_at, scheduler_state_json FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    assert due_at > now.isoformat()
    assert state_json is not None


def test_sm2_params_live_only_in_scheduler_state_json(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="good",
        mechanism="flashcard",
        now=now,
    )

    conn = sqlite3.connect(db_path)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(learner_items)")
    }
    assert columns == LEARNER_ITEM_COLUMNS

    (state_json,) = conn.execute(
        "SELECT scheduler_state_json FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    state = json.loads(state_json)
    assert set(state) == {"repetitions", "ef", "interval_days"}


def test_tool_stores_alternate_scheduler_state_verbatim(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin import scheduler
    from plugin.tools import luvia_record_result

    opaque_state = {"fsrs_stability": 12.5, "fsrs_difficulty": 0.3, "note": "opaque"}

    class FakeScheduler:
        def schedule(self, state, grade, now):
            return opaque_state, datetime(2026, 8, 1, tzinfo=timezone.utc)

    scheduler.register("fake", FakeScheduler())

    luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="good",
        mechanism="flashcard",
        scheduler_name="fake",
        now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )

    conn = sqlite3.connect(db_path)
    state_json, due_at = conn.execute(
        "SELECT scheduler_state_json, due_at FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    assert json.loads(state_json) == opaque_state
    assert due_at == "2026-08-01T00:00:00+00:00"


def test_scheduler_failure_leaves_neither_event_nor_reschedule(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin import scheduler
    from plugin.tools import luvia_record_result

    class BoomScheduler:
        def schedule(self, state, grade, now):
            raise RuntimeError("scheduler exploded")

    scheduler.register("boom", BoomScheduler())

    with pytest.raises(RuntimeError):
        luvia_record_result(
            user_id=user_id,
            item_id=item_id,
            session_id=session_id,
            grade="good",
            mechanism="flashcard",
            scheduler_name="boom",
            now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
        )

    conn = sqlite3.connect(db_path)
    assert conn.execute(
        "SELECT COUNT(*) FROM session_events WHERE session_id = ?", (session_id,)
    ).fetchone()[0] == 0
    due_at, state_json, success_count = conn.execute(
        "SELECT due_at, scheduler_state_json, success_count FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    assert due_at is None
    assert state_json is None
    assert success_count == 0


def test_session_event_stores_all_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="easy",
        mechanism="flashcard",
        latency_ms=1500,
        comprehension_break=True,
        now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )

    conn = sqlite3.connect(db_path)
    grade, latency_ms, comprehension_break, created_at = conn.execute(
        "SELECT grade, latency_ms, comprehension_break, created_at"
        " FROM session_events WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    assert grade == "easy"
    assert latency_ms == 1500
    assert comprehension_break == 1
    assert created_at is not None


def test_ambient_comprehension_break_is_queryable(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    luvia_record_result(
        user_id=user_id,
        item_id=None,
        session_id=session_id,
        grade=None,
        mechanism="ambient",
        comprehension_break=True,
        learner_response="ik snap het niet",
        now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT mechanism, learner_response FROM session_events"
        " WHERE session_id = ? AND comprehension_break = 1",
        (session_id,),
    ).fetchall()
    assert rows == [("ambient", "ik snap het niet")]


def test_already_knew_on_first_encounter_fast_tracks(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    result = luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="already_knew",
        mechanism="flashcard",
        now=now,
    )

    # ~30-day sweep, counted as a success rather than a lapse.
    assert result["due_at"] == (now + timedelta(days=30)).isoformat()
    assert result["status"] == "review"

    conn = sqlite3.connect(db_path)
    (grade,) = conn.execute(
        "SELECT grade FROM session_events WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert grade == "already_knew"

    status, success_count, failure_count = conn.execute(
        "SELECT status, success_count, failure_count FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    assert status == "review"
    assert success_count == 1
    assert failure_count == 0


def test_already_knew_rejected_on_later_encounter(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, item_id, session_id = _seed(db_path)

    from plugin.tools import luvia_record_result

    luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        session_id=session_id,
        grade="good",
        mechanism="flashcard",
        now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="first encounter"):
        luvia_record_result(
            user_id=user_id,
            item_id=item_id,
            session_id=session_id,
            grade="already_knew",
            mechanism="flashcard",
            now=datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc),
        )

    # Rejection is atomic: only the first (good) event survives.
    conn = sqlite3.connect(db_path)
    grades = conn.execute(
        "SELECT grade FROM session_events WHERE session_id = ?", (session_id,)
    ).fetchall()
    assert grades == [("good",)]


def test_swept_items_distinguishable_from_new_intake(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id, swept_item, session_id = _seed(db_path)

    # A second item the learner genuinely learns through the graduation ladder.
    conn = sqlite3.connect(db_path)
    new_item = conn.execute(
        "INSERT INTO content_items (lang, item_type, surface)"
        " VALUES ('nl', 'lemma', 'de kat')"
    ).lastrowid
    conn.execute(
        "INSERT INTO learner_items (user_id, item_id) VALUES (?, ?)",
        (user_id, new_item),
    )
    conn.commit()
    conn.close()

    from plugin.tools import luvia_record_result

    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    luvia_record_result(
        user_id=user_id, item_id=swept_item, session_id=session_id,
        grade="already_knew", mechanism="flashcard", now=now,
    )
    luvia_record_result(
        user_id=user_id, item_id=new_item, session_id=session_id,
        grade="good", mechanism="flashcard", now=now,
    )

    # Pacing-band accounting (issue 0006) excludes items whose intake was a sweep.
    conn = sqlite3.connect(db_path)
    swept = conn.execute(
        "SELECT DISTINCT item_id FROM session_events WHERE grade = 'already_knew'"
    ).fetchall()
    assert swept == [(swept_item,)]


def test_grading_untracked_item_creates_scheduled_learner_item(tmp_path, monkeypatch):
    """First grading of a freshly-picked new item must enter it into the schedule.

    Regression: record_result was UPDATE-only, so grading an item with no
    learner_items row silently dropped the schedule and the item never came due."""
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))

    from plugin import store
    from plugin.tools import luvia_record_result, luvia_setup

    user_id = luvia_setup(name="T", telegram_user_id="tg-untracked", target_lang="nl")[
        "user_id"
    ]
    conn = store.connect()
    item_id = conn.execute(
        "INSERT INTO content_items (lang, item_type, surface)"
        " VALUES ('nl', 'lemma', 'de fiets')",
        (),
    ).lastrowid
    conn.commit()
    # No learner_items row exists for this item yet.
    assert conn.execute("SELECT COUNT(*) FROM learner_items").fetchone()[0] == 0
    conn.close()

    result = luvia_record_result(
        user_id=user_id,
        item_id=item_id,
        grade="good",
        mechanism="ambient_recall",
        lang="nl",
        mode="ambient",
    )

    conn = store.connect()
    row = conn.execute(
        "SELECT status, due_at, success_count FROM learner_items"
        " WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchone()
    conn.close()
    assert row is not None, "grading an untracked item must persist a learner_items row"
    status, due_at, success_count = row
    assert status == "review"
    assert due_at == result["due_at"]
    assert success_count == 1
