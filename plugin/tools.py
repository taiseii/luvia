"""The luvia_* tool surface declared in plugin.yaml."""

import json
from datetime import datetime, timedelta, timezone

from plugin import pacing, scheduler, scoring, store

LANGUAGE_NAMES = {"nl": "Dutch", "en": "English"}

# Bursts of activity in the same mode are grouped into one session row until this
# much silence passes; the next touch opens a fresh burst. No user-facing ceremony.
SESSION_GAP = timedelta(minutes=30)

REVIEW_BATCH_SIZE = 20
AMBIENT_BATCH_SIZE = 5


def _resolve_session(conn, user_id, lang, mode, now):
    """Return the id of the open burst for (user, lang, mode), reusing it while
    activity stays within SESSION_GAP and opening a new session past the gap."""
    row = conn.execute(
        "SELECT id, started_at FROM sessions WHERE user_id = ? AND lang = ?"
        " AND mode = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
        (user_id, lang, mode),
    ).fetchone()
    if row:
        session_id, started_at = row
        (last_event,) = conn.execute(
            "SELECT MAX(created_at) FROM session_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        last_activity = datetime.fromisoformat(last_event or started_at)
        if now - last_activity <= SESSION_GAP:
            return session_id
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (last_activity.isoformat(), session_id),
        )
    cursor = conn.execute(
        "INSERT INTO sessions (user_id, lang, mode, method_profile_id, started_at)"
        " VALUES (?, ?, ?, 'default', ?)",
        (user_id, lang, mode, now.isoformat()),
    )
    return cursor.lastrowid


def luvia_pick_items(
    user_id: int,
    mode: str,
    lang: str,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Return a mode-aware batch for the carrier persona, attached to the current
    burst: due-review items for review mode, a small due+new micro-batch for
    ambient mode."""
    now = now or datetime.now(timezone.utc)
    conn = store.connect()
    try:
        with conn:
            session_id = _resolve_session(conn, user_id, lang, mode, now)
            cap = batch_size or (
                AMBIENT_BATCH_SIZE if mode == "ambient" else REVIEW_BATCH_SIZE
            )
            due = conn.execute(
                "SELECT li.item_id, ci.surface FROM learner_items li"
                " JOIN content_items ci ON ci.id = li.item_id"
                " WHERE li.user_id = ? AND li.due_at IS NOT NULL AND li.due_at <= ?"
                " ORDER BY li.due_at LIMIT ?",
                (user_id, now.isoformat(), cap),
            ).fetchall()
            items = [
                {"item_id": r[0], "surface": r[1], "source": "due"} for r in due
            ]

            if mode == "ambient":
                # New intake is governed by the pacing band's daily allotment,
                # capped by the space left in the micro-batch.
                band = pacing.current_band(_weekly_history(conn, user_id, now))
                new_cap = min(
                    pacing.daily_new_intake(band), AMBIENT_BATCH_SIZE - len(items)
                )
                new = conn.execute(
                    "SELECT id, surface FROM content_items WHERE lang = ?"
                    " AND id NOT IN (SELECT item_id FROM learner_items WHERE user_id = ?)"
                    " ORDER BY frequency_rank IS NULL, frequency_rank, id LIMIT ?",
                    (lang, user_id, new_cap),
                ).fetchall()
                items += [
                    {"item_id": r[0], "surface": r[1], "source": "new"} for r in new
                ]
        return {"session_id": session_id, "mode": mode, "items": items}
    finally:
        conn.close()


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


# A week with no genuine (non-sweep) reviews carries no recall signal, so it
# holds the band rather than dragging it down.
NEUTRAL_RECALL = 0.75


def _weekly_history(conn, user_id: int, now: datetime) -> list[dict]:
    """Reconstruct completed-week pacing stats from session events alone.

    Fast-tracked sweeps (grade 'already_knew') are excluded from recall so they
    never consume the band; the in-progress week is skipped until it closes."""
    rows = conn.execute(
        "SELECT se.created_at, se.grade FROM session_events se"
        " JOIN sessions s ON s.id = se.session_id WHERE s.user_id = ?",
        (user_id,),
    ).fetchall()

    weeks: dict[int, dict] = {}
    for created_at, grade in rows:
        week_index = (now - datetime.fromisoformat(created_at)).days // 7
        if week_index <= 0:
            continue  # current, still-open week does not ratchet yet
        week = weeks.setdefault(
            week_index, {"dates": set(), "correct": 0, "reviews": 0}
        )
        week["dates"].add(datetime.fromisoformat(created_at).date())
        if grade in ("again", "good", "easy"):
            week["reviews"] += 1
            if grade in ("good", "easy"):
                week["correct"] += 1

    history = []
    for week_index in sorted(weeks, reverse=True):  # oldest week first
        week = weeks[week_index]
        active_days = len(week["dates"])
        recall = (
            week["correct"] / week["reviews"] if week["reviews"] else NEUTRAL_RECALL
        )
        history.append(
            {
                "recall": recall,
                "completion": active_days / 7,
                "skipped_days": 7 - active_days,
            }
        )
    return history


def luvia_plan_today(user_id: int, lang: str, now: datetime | None = None) -> dict:
    """The carrier persona's daily plan, from SQLite state alone (cron-safe).

    Returns the pacing band, the capped due load with any overflow spilled
    forward, the guaranteed new intake, and a suggested mode balance."""
    now = now or datetime.now(timezone.utc)
    conn = store.connect()
    try:
        (due_count,) = conn.execute(
            "SELECT COUNT(*) FROM learner_items li"
            " JOIN content_items ci ON ci.id = li.item_id"
            " WHERE li.user_id = ? AND ci.lang = ?"
            " AND li.due_at IS NOT NULL AND li.due_at <= ?",
            (user_id, lang, now.isoformat()),
        ).fetchone()
        band = pacing.current_band(_weekly_history(conn, user_id, now))
    finally:
        conn.close()

    plan = pacing.daily_plan(band, due_count)
    plan["band"] = band
    plan["mode_balance"] = {
        "review": plan["due_load"],
        "ambient": plan["new_intake"],
    }
    return plan


def luvia_stats(user_id: int, lang: str, now: datetime | None = None) -> dict:
    """A read-only "is this working" snapshot from SQLite state alone (cron-safe,
    no chat context): recall rate, sweep progress, pacing-band position, and due
    counts.

    Recall reuses the same grade classification the pacing band folds over —
    'already_knew' sweeps are excluded so they never inflate the figure — but
    aggregates it across the whole trailing history rather than folding per week."""
    now = now or datetime.now(timezone.utc)
    conn = store.connect()
    try:
        reviews, correct = conn.execute(
            "SELECT"
            " SUM(CASE WHEN se.grade IN ('again', 'good', 'easy') THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN se.grade IN ('good', 'easy') THEN 1 ELSE 0 END)"
            " FROM session_events se JOIN sessions s ON s.id = se.session_id"
            " WHERE s.user_id = ? AND s.lang = ?",
            (user_id, lang),
        ).fetchone()
        reviews, correct = reviews or 0, correct or 0

        # Swept: distinct items the first-encounter fast-track has cleared.
        # Remaining: corpus the sweep has not yet reached (still unencountered).
        (swept,) = conn.execute(
            "SELECT COUNT(DISTINCT se.item_id) FROM session_events se"
            " JOIN sessions s ON s.id = se.session_id"
            " WHERE s.user_id = ? AND s.lang = ? AND se.grade = 'already_knew'",
            (user_id, lang),
        ).fetchone()
        (remaining,) = conn.execute(
            "SELECT COUNT(*) FROM content_items ci WHERE ci.lang = ?"
            " AND ci.id NOT IN (SELECT item_id FROM learner_items WHERE user_id = ?)",
            (lang, user_id),
        ).fetchone()

        (due_now,) = conn.execute(
            "SELECT COUNT(*) FROM learner_items li"
            " JOIN content_items ci ON ci.id = li.item_id"
            " WHERE li.user_id = ? AND ci.lang = ?"
            " AND li.due_at IS NOT NULL AND li.due_at <= ?",
            (user_id, lang, now.isoformat()),
        ).fetchone()
        (tracked,) = conn.execute(
            "SELECT COUNT(*) FROM learner_items li"
            " JOIN content_items ci ON ci.id = li.item_id"
            " WHERE li.user_id = ? AND ci.lang = ?",
            (user_id, lang),
        ).fetchone()

        band = pacing.current_band(_weekly_history(conn, user_id, now))
    finally:
        conn.close()

    return {
        "recall": {
            "rate": correct / reviews if reviews else None,
            "reviews": reviews,
            "correct": correct,
        },
        "sweep": {"swept": swept, "remaining": remaining},
        "band": {
            "position": band,
            "daily_new_intake": pacing.daily_new_intake(band),
        },
        "due": {"due_now": due_now, "tracked": tracked},
    }


def luvia_score_response(answer: str, expected: str | list[str]) -> dict:
    """Deterministically score a typed answer against the accepted answer(s).

    Pure scoring, no scheduling side effects: the carrier persona applies LLM
    judgment to ambiguous answers based on the verdict this returns."""
    return scoring.score(answer, expected)


_SUCCESS_GRADES = {"good", "easy", "already_knew"}


def luvia_record_result(
    user_id: int,
    item_id: int,
    grade: str | None,
    mechanism: str,
    session_id: int | None = None,
    lang: str | None = None,
    mode: str | None = None,
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
    is ever persisted without its scheduling effect. Pass an explicit session_id
    to append to a known burst, or lang+mode to attach to the current one."""
    now = now or datetime.now(timezone.utc)
    grade_value = scheduler.Grade(grade) if grade is not None else None
    engine = scheduler.get(scheduler_name)

    conn = store.connect()
    try:
        with conn:
            if session_id is None:
                if lang is None or mode is None:
                    raise ValueError(
                        "luvia_record_result needs either session_id or lang+mode"
                    )
                session_id = _resolve_session(conn, user_id, lang, mode, now)
            (next_index,) = conn.execute(
                "SELECT COALESCE(MAX(event_index) + 1, 0) FROM session_events"
                " WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            conn.execute(
                "INSERT INTO session_events (session_id, event_index, mechanism,"
                " item_id, prompt, learner_response, grade, score, feedback,"
                " latency_ms, comprehension_break, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    now.isoformat(),
                ),
            )

            # Ungraded events (e.g. ambient comprehension-break signals) are
            # logged without touching the learner item's schedule.
            if grade_value is None:
                return {"session_id": session_id, "due_at": None, "status": None}

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
            result = {
                "session_id": session_id,
                "due_at": due.isoformat(),
                "status": status,
            }
    finally:
        conn.close()

    return result
