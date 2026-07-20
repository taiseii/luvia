"""The luvia_* tool surface declared in plugin.yaml."""

import json

from plugin import store

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
