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

import pytest

from plugin.image_backend import ImageBackendError
from plugin.reference_manifest import Reference, ReferenceManifestError

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


def _png_files(out):
    out = Path(out)
    return sorted(out.glob("*.png")) if out.exists() else []


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


# --- Finding 1: failures AFTER backend success must soft-fail, never raise ----


def test_save_failure_soft_fails_without_row(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("plugin.tools._save_selfie", boom)

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="cafe selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "save_failed"
    # A save failure consumes no quota (no row) and never raises to chat.
    assert _selfie_rows(db_path) == []


def test_log_failure_after_save_soft_fails_and_cleans_up(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()
    out = tmp_path / "selfies"

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("plugin.store.log_selfie", boom)

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="cafe selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=out,
    )

    assert result["ok"] is False
    assert result["reason"] == "log_failed"
    # No row written, and the orphaned image is cleaned up.
    assert _selfie_rows(db_path) == []
    assert _png_files(out) == []


# --- Finding 2: quota re-check + log are atomic (single-writer race) ----------


def test_concurrent_breach_between_check_and_log_soft_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    out = tmp_path / "selfies"

    from plugin import store

    conn = store.connect()
    try:  # 2 of the 3 request slots already used -> initial check passes
        for i in range(2):
            store.log_selfie(conn, user_id, "request", NOW - timedelta(hours=i + 1))
    finally:
        conn.close()

    class RaceBackend:
        """A concurrent call lands the 3rd row between pre-check and the log step."""

        def __init__(self):
            self.calls = []

        def generate(self, reference_image, scene_prompt):
            self.calls.append((reference_image, scene_prompt))
            other = store.connect()
            try:
                store.log_selfie(other, user_id, "request", NOW - timedelta(minutes=1))
            finally:
                other.close()
            return IMG_BYTES

    backend = RaceBackend()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="gym selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=out,
    )

    assert result["ok"] is False
    assert result["reason"] == "quota_exceeded"
    assert len(backend.calls) == 1
    # The cap is exactly 3: the two prefilled + the one the race injected. Our
    # call must NOT have added a fourth, and it cleaned up its orphaned file.
    assert len(_selfie_rows(db_path)) == 3
    assert _png_files(out) == []


# --- Finding 3: filename hardening (traversal + collision) --------------------


@pytest.mark.parametrize("bad_user", ["../etc/passwd", "1/2", "abc", None, 3.5, True, 0, -1])
def test_invalid_user_id_soft_fails_before_backend(tmp_path, monkeypatch, bad_user):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=bad_user,
        scene="cafe selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "invalid_user"
    # Rejected before any spend: no backend call, no row.
    assert backend.calls == []
    assert _selfie_rows(db_path) == []


def test_two_rapid_saves_do_not_collide(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    out = tmp_path / "selfies"

    from plugin.tools import luvia_selfie

    # Same user, source, and timestamp on both calls.
    first = luvia_selfie(
        user_id=user_id, scene="one", trigger_source="request",
        now=NOW, backend=FakeBackend(), output_dir=out,
    )
    second = luvia_selfie(
        user_id=user_id, scene="two", trigger_source="request",
        now=NOW, backend=FakeBackend(), output_dir=out,
    )

    assert first["ok"] is True and second["ok"] is True
    assert first["path"] != second["path"]
    assert len(_png_files(out)) == 2


# --- Finding 4: nonexistent user_id validated before backend spend ------------


def test_nonexistent_user_id_soft_fails_before_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    _new_user()  # user id 1 exists; 99999 does not
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=99999,
        scene="cafe selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "invalid_user"
    assert backend.calls == []
    assert _selfie_rows(db_path) == []


# --- Finding 5: reference-unavailable + invalid trigger_source ----------------


def test_reference_unavailable_soft_fails_without_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    backend = FakeBackend()

    def raise_missing(reference_role, assets_dir=None):
        raise ReferenceManifestError("manifest.json not found on the box")

    monkeypatch.setattr("plugin.tools.resolve_reference_role", raise_missing)

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="cafe selfie",
        trigger_source="request",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "reference_unavailable"
    assert backend.calls == []
    assert _selfie_rows(db_path) == []


def test_invalid_trigger_source_soft_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))
    user_id = _new_user()
    _patch_resolver(monkeypatch, _fake_reference(tmp_path))
    backend = FakeBackend()

    from plugin.tools import luvia_selfie

    result = luvia_selfie(
        user_id=user_id,
        scene="cafe selfie",
        trigger_source="banana",
        now=NOW,
        backend=backend,
        output_dir=tmp_path / "selfies",
    )

    assert result["ok"] is False
    assert result["reason"] == "invalid_trigger_source"
    assert backend.calls == []
    assert _selfie_rows(db_path) == []
