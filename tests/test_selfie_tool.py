"""luvia_selfie tool seam — happy path + graceful soft-fail.

Driven exactly like the other luvia_* tool tests (temp SQLite via LUVIA_DB,
window-driven quota like test_pacing/test_plan_today). The image backend and
reference resolution are injected/monkeypatched so nothing touches the network
and no real assets dir is read. Assertions are on externally observable
behavior only: returned payloads, selfie_log rows, quota decisions, and the
bytes handed to / saved from the backend.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plugin.image_backend import ImageBackendError
from plugin.reference_manifest import Reference

NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
REF_BYTES = b"REFERENCE-IMAGE-BYTES"
IMG_BYTES = b"GENERATED-SELFIE-BYTES"


def _new_user():
    from plugin.tools import luvia_setup

    return luvia_setup(name="Taisei", telegram_user_id="tg-1", target_lang="nl")[
        "user_id"
    ]


def _fake_reference(tmp_path, role="canonical_face"):
    ref_file = tmp_path / "portrait.jpg"
    ref_file.write_bytes(REF_BYTES)
    return Reference(
        file="portrait.jpg",
        role=role,
        framing="portrait",
        setting="studio",
        tags=(),
        description="canonical face",
        default=True,
        path=ref_file,
    )


class FakeBackend:
    """Injected ImageBackend double: records calls, returns or raises."""

    def __init__(self, image=IMG_BYTES, error=None):
        self.image = image
        self.error = error
        self.calls = []

    def generate(self, reference_image, scene_prompt):
        self.calls.append((reference_image, scene_prompt))
        if self.error is not None:
            raise self.error
        return self.image


def _patch_resolver(monkeypatch, ref):
    """Replace the real resolver so no real assets dir is read; capture the role."""
    captured = {}

    def fake_resolve(reference_role, assets_dir=None):
        captured["role"] = reference_role
        captured["assets_dir"] = assets_dir
        return ref

    monkeypatch.setattr("plugin.tools.resolve_reference_role", fake_resolve)
    return captured


def _selfie_rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT user_id, trigger_source FROM selfie_log"
        ).fetchall()
    finally:
        conn.close()


def test_happy_path_writes_row_and_returns_saved_path(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    captured = _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()
    out = tmp_path / "selfies"

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="sunny cafe selfie with a latte",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=out,
    )

    assert result["ok"] is True
    path = Path(result["path"])
    assert path.is_file()
    assert path.read_bytes() == IMG_BYTES
    # The backend edited the resolved reference bytes with the scene prompt.
    assert backend.calls == [(REF_BYTES, "sunny cafe selfie with a latte")]
    # Reference role omitted -> resolver asked for the canonical_face default.
    assert captured["role"] == "canonical_face"
    # Exactly one selfie_log row, for this source.
    assert _selfie_rows(db_path) == [(user_id, "request")]


def test_sanitizer_reject_soft_fails_without_row_or_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="she is completely naked in the shot",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "content_blocked"
    # Never spent a backend call, never logged a selfie (no quota consumed).
    assert backend.calls == []
    assert _selfie_rows(db_path) == []


def test_quota_cap_soft_fails_no_row_backend_untouched(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    from plugin import store

    conn = store.connect()
    try:
        for i in range(3):  # request cap is 3 / rolling 24h
            store.log_selfie(conn, user_id, "request", NOW - timedelta(hours=i + 1))
    finally:
        conn.close()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="cute selfie at the gym",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "quota_exceeded"
    # Quota is checked BEFORE the backend is called; no new row is written.
    assert backend.calls == []
    assert len(_selfie_rows(db_path)) == 3


def test_backend_error_soft_fails_no_row(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend(error=ImageBackendError("moderation", "BFL blocked it"))

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="flirty selfie from bed",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "backend_error"
    assert result["detail"] == "moderation"
    # The backend WAS attempted, but a failed generation consumes no quota.
    assert len(backend.calls) == 1
    assert _selfie_rows(db_path) == []


def test_proactive_window_independent_from_request(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()
    out = tmp_path / "selfies"

    from plugin import store

    conn = store.connect()
    try:  # proactive cap is 1 / rolling 72h — exhaust it
        store.log_selfie(conn, user_id, "proactive", NOW - timedelta(hours=1))
    finally:
        conn.close()

    from plugin.tools import luvia_selfie

    proactive = luvia_selfie(
        user_id=user_id,
        scene="quiet morning selfie",
        trigger_source="proactive",
        now=NOW,
        backend=backend,
        output_dir=out,
    )
    assert proactive["ok"] is False
    assert proactive["reason"] == "quota_exceeded"
    assert backend.calls == []  # capped source never reaches the backend

    # The request window is separate and still has allowance.
    request = luvia_selfie(
        user_id=user_id,
        scene="quiet morning selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=out,
    )
    assert request["ok"] is True
    assert request["trigger_source"] == "request"
    assert len(backend.calls) == 1
    # Proactive prefill + the new request row, each logged under its own source.
    assert sorted(src for _, src in _selfie_rows(db_path)) == ["proactive", "request"]


def test_result_payload_shapes(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path, role="canonical_face"))
    out = tmp_path / "selfies"

    from plugin.tools import luvia_selfie

    success = luvia_selfie(
        user_id=user_id,
        scene="golden hour selfie on the balcony",
        reference_role="canonical_face",
        trigger_source="request",
        now=NOW,
        backend=FakeBackend(),
        output_dir=out,
    )
    assert success["ok"] is True
    assert set(success) >= {"ok", "path", "trigger_source", "reference_role"}
    assert success["trigger_source"] == "request"
    assert success["reference_role"] == "canonical_face"

    soft_fail = luvia_selfie(
        user_id=user_id,
        scene="explicit nude photo",
        trigger_source="request",
        now=NOW,
        backend=FakeBackend(),
        output_dir=out,
    )
    assert soft_fail["ok"] is False
    assert set(soft_fail) >= {"ok", "reason", "trigger_source"}
    assert soft_fail["trigger_source"] == "request"
