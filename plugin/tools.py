"""The luvia_* tool surface declared in plugin.yaml."""

import json
from datetime import datetime, timezone

from plugin import scheduler, store

LANGUAGE_NAMES = {"nl": "Dutch", "en": "English"}


def luvia_setup(
    name: str,
    telegram_user_id: str,
    target_lang: str = "nl",
    timezone: str = "Europe/Amsterdam",
    reference_lang: str = "en",
    interests: list[str] | None = None,
    contexts: list[str] | None = None,
    level: str | None = None,
) -> dict:
    """Create the learner and capture onboarding context (interests, contexts,
    level prior) for content tagging and phrase seeding."""
    conn = store.connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO languages (code, name) VALUES (?, ?)",
            (target_lang, LANGUAGE_NAMES.get(target_lang, target_lang)),
        )
        metadata = {
            "interests": interests or [],
            "contexts": contexts or [],
            "levels": {target_lang: level} if level else {},
        }
        existing = conn.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        if existing:
            user_id, created = existing[0], False
            conn.execute(
                "UPDATE users SET name = ?, timezone = ?, reference_lang = ?,"
                " metadata_json = ? WHERE id = ?",
                (name, timezone, reference_lang, json.dumps(metadata), user_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO users (name, telegram_user_id, timezone, reference_lang,"
                " metadata_json) VALUES (?, ?, ?, ?, ?)",
                (name, telegram_user_id, timezone, reference_lang, json.dumps(metadata)),
            )
            user_id, created = cursor.lastrowid, True
        conn.commit()
        return {"user_id": user_id, "created": created, "target_lang": target_lang}
    finally:
        conn.close()


_SUCCESS_GRADES = {"good", "easy", "already_knew"}


def luvia_record_result(
    user_id: int,
    item_id: int,
    session_id: int,
    grade: str | None,
    mechanism: str,
    latency_ms: int | None = None,
    comprehension_break: bool = False,
    prompt: str | None = None,
    learner_response: str | None = None,
    score: float | None = None,
    feedback: str | None = None,
    scheduler_name: str = "sm2",
    now: datetime | None = None,
) -> dict:
    """Log a session event and reschedule the learner item in one transaction.

    The event is written first, then the scheduler runs and the learner item is
    updated; the whole block commits or rolls back together, so no review event
    is ever persisted without its scheduling effect."""
    now = now or datetime.now(timezone.utc)
    grade_value = scheduler.Grade(grade) if grade is not None else None
    engine = scheduler.get(scheduler_name)

    conn = store.connect()
    try:
        with conn:
            (next_index,) = conn.execute(
                "SELECT COALESCE(MAX(event_index) + 1, 0) FROM session_events"
                " WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            conn.execute(
                "INSERT INTO session_events (session_id, event_index, mechanism,"
                " item_id, prompt, learner_response, grade, score, feedback,"
                " latency_ms, comprehension_break) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    next_index,
                    mechanism,
                    item_id,
                    prompt,
                    learner_response,
                    grade,
                    score,
                    feedback,
                    latency_ms,
                    1 if comprehension_break else 0,
                ),
            )

            # Ungraded events (e.g. ambient comprehension-break signals) are
            # logged without touching the learner item's schedule.
            if grade_value is None:
                return {"due_at": None, "status": None}

            row = conn.execute(
                "SELECT scheduler_state_json, success_count, failure_count"
                " FROM learner_items WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            ).fetchone()
            state = json.loads(row[0]) if row and row[0] else {}
            success_count, failure_count = (row[1], row[2]) if row else (0, 0)

            new_state, due = engine.schedule(state, grade_value, now)

            if grade in _SUCCESS_GRADES:
                success_count += 1
                status = "review"
            else:
                failure_count += 1
                status = "learning"

            conn.execute(
                "UPDATE learner_items SET status = ?, due_at = ?, last_seen_at = ?,"
                " last_score = ?, success_count = ?, failure_count = ?,"
                " scheduler_state_json = ? WHERE user_id = ? AND item_id = ?",
                (
                    status,
                    due.isoformat(),
                    now.isoformat(),
                    score,
                    success_count,
                    failure_count,
                    json.dumps(new_state),
                    user_id,
                    item_id,
                ),
            )
            result = {"due_at": due.isoformat(), "status": status}
    finally:
        conn.close()

    return result
