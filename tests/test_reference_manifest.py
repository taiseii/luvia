"""Tests for the reference-manifest resolver (issue 0014).

This is the *reference* manifest (Sophia's curated reference-image library),
deliberately named apart from the plugin content manifest exercised in
test_manifest.py. Every test builds its own temp assets dir + manifest.json
fixture; nothing here touches the real (gitignored) assets/sophie/ contents or
the network.
"""

import json

import pytest

from plugin import reference_manifest
from plugin.reference_manifest import ReferenceManifestError


# A 5-row fixture that mirrors the on-box library shape: one canonical-face
# portrait (the default / fallback) plus four poses.
FIXTURE_ROWS = [
    {
        "file": "canonical_portrait.png",
        "role": "canonical_face",
        "framing": "portrait",
        "setting": "studio",
        "tags": ["neutral", "headshot"],
        "description": "Canonical face portrait — the default reference.",
        "default": True,
    },
    {
        "file": "pose_cafe_half.png",
        "role": "pose",
        "framing": "half",
        "setting": "cafe",
        "tags": ["seated", "smiling"],
        "description": "Half-body at a cafe table.",
        "default": False,
    },
    {
        "file": "pose_street_full.png",
        "role": "pose",
        "framing": "full",
        "setting": "street",
        "tags": ["walking"],
        "description": "Full-body walking down a street.",
        "default": False,
    },
    {
        "file": "pose_park_half.png",
        "role": "pose",
        "framing": "half",
        "setting": "park",
        "tags": ["outdoor"],
        "description": "Half-body in a park.",
        "default": False,
    },
    {
        "file": "pose_home_full.png",
        "role": "pose",
        "framing": "full",
        "setting": "home",
        "tags": ["cozy"],
        "description": "Full-body at home.",
        "default": False,
    },
]


def _write_assets(tmp_path, rows=FIXTURE_ROWS):
    """Materialise a temp assets dir: manifest.json + the image files beside it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text(json.dumps(rows))
    for row in rows:
        (tmp_path / row["file"]).write_bytes(b"fake-image-bytes")
    return tmp_path


def test_reads_env_assets_dir_and_parses_schema(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    rows = reference_manifest.load_reference_manifest()

    assert len(rows) == 5
    first = rows[0]
    # Every field of the per-image schema survives parsing.
    assert first.file == "canonical_portrait.png"
    assert first.role == "canonical_face"
    assert first.framing == "portrait"
    assert first.setting == "studio"
    assert list(first.tags) == ["neutral", "headshot"]
    assert first.description
    assert first.default is True
    # Resolved absolute path points at the colocated file on disk.
    assert first.path.is_absolute()
    assert first.path == tmp_path / "canonical_portrait.png"
    assert first.path.exists()


def test_resolves_valid_role_to_its_file(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    ref = reference_manifest.resolve_reference_role("pose")

    assert ref.role == "pose"
    assert ref.path == tmp_path / ref.file
    assert ref.path.exists()


def test_missing_role_falls_back_to_default_portrait(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    ref = reference_manifest.resolve_reference_role(None)

    assert ref.role == "canonical_face"
    assert ref.framing == "portrait"
    assert ref.default is True
    assert ref.file == "canonical_portrait.png"


def test_unknown_role_falls_back_to_default_portrait(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    ref = reference_manifest.resolve_reference_role("does_not_exist")

    assert ref.role == "canonical_face"
    assert ref.default is True


def test_empty_role_falls_back_to_default_portrait(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    ref = reference_manifest.resolve_reference_role("")

    assert ref.role == "canonical_face"
    assert ref.default is True


def test_explicit_assets_dir_overrides_env(tmp_path, monkeypatch):
    # Env points nowhere; explicit arg wins, proving the resolver is a pure
    # function of its inputs rather than of ambient state.
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path / "nonexistent"))
    assets = _write_assets(tmp_path / "real")

    ref = reference_manifest.resolve_reference_role(None, assets_dir=assets)

    assert ref.default is True
    assert ref.path == assets / "canonical_portrait.png"


def test_resolution_is_read_only_no_auto_growth(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    before_manifest = (tmp_path / "manifest.json").read_text()
    before_files = sorted(p.name for p in tmp_path.iterdir())

    reference_manifest.resolve_reference_role("pose")
    reference_manifest.resolve_reference_role(None)
    reference_manifest.load_reference_manifest()

    # Manifest is never written back and no new files appear: fixed library.
    assert (tmp_path / "manifest.json").read_text() == before_manifest
    assert sorted(p.name for p in tmp_path.iterdir()) == before_files


def test_missing_assets_dir_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("LUVIA_SOPHIA_ASSETS", raising=False)

    with pytest.raises(ReferenceManifestError):
        reference_manifest.load_reference_manifest()


def test_manifest_without_default_portrait_raises_on_fallback(tmp_path, monkeypatch):
    # A library with no default entry can't satisfy the portrait fallback; that
    # is a manifest-authoring error and should surface loudly, not silently.
    rows = [dict(r, default=False) for r in FIXTURE_ROWS]
    _write_assets(tmp_path, rows)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    with pytest.raises(ReferenceManifestError):
        reference_manifest.resolve_reference_role(None)


def test_traversal_file_escaping_assets_dir_is_rejected(tmp_path, monkeypatch):
    # A tampered manifest must not read files outside the library via ../.
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    assets = tmp_path / "assets"
    rows = [dict(FIXTURE_ROWS[0], file="../secret.txt")]
    _write_assets(assets, rows)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(assets))

    with pytest.raises(ReferenceManifestError):
        reference_manifest.load_reference_manifest()


def test_absolute_file_path_is_rejected(tmp_path, monkeypatch):
    # Write the manifest directly; an absolute `file` must be rejected without
    # the loader ever touching the target path.
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = [dict(FIXTURE_ROWS[0], file="/etc/passwd")]
    (tmp_path / "manifest.json").write_text(json.dumps(rows))
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    with pytest.raises(ReferenceManifestError):
        reference_manifest.load_reference_manifest()


def test_symlink_escaping_assets_dir_is_rejected(tmp_path, monkeypatch):
    # A symlink inside the assets dir pointing out must not smuggle a read past
    # the containment check — resolution follows the link, then we reject it.
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside-bytes")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "escape.png").symlink_to(outside)
    (assets / "manifest.json").write_text(
        json.dumps([dict(FIXTURE_ROWS[0], file="escape.png")])
    )
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(assets))

    with pytest.raises(ReferenceManifestError):
        reference_manifest.load_reference_manifest()


def test_missing_image_file_is_caught_at_load(tmp_path, monkeypatch):
    # File named in the manifest but never placed on disk: fail at load with a
    # message naming the bad file, not later in the backend.
    rows = [r.copy() for r in FIXTURE_ROWS]
    _write_assets(tmp_path, rows)
    (tmp_path / "pose_cafe_half.png").unlink()  # remove one referenced image
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    with pytest.raises(ReferenceManifestError) as excinfo:
        reference_manifest.load_reference_manifest()
    assert "pose_cafe_half.png" in str(excinfo.value)


def test_default_flag_on_pose_does_not_hijack_portrait_fallback(tmp_path, monkeypatch):
    # A pose flagged default must not become the missing/unknown-role fallback;
    # the fallback is the canonical-face portrait specifically.
    rows = [
        dict(FIXTURE_ROWS[0], default=True),   # canonical_face portrait, default
        dict(FIXTURE_ROWS[1], default=True),   # a pose ALSO flagged default
        FIXTURE_ROWS[2],
        FIXTURE_ROWS[3],
        FIXTURE_ROWS[4],
    ]
    _write_assets(tmp_path, rows)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    ref = reference_manifest.resolve_reference_role(None)

    assert ref.role == "canonical_face"
    assert ref.file == "canonical_portrait.png"


def test_malformed_json_raises_manifest_error(tmp_path, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text("{not valid json,,,")
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    with pytest.raises(ReferenceManifestError):
        reference_manifest.load_reference_manifest()


def test_missing_required_field_raises_manifest_error(tmp_path, monkeypatch):
    bad = FIXTURE_ROWS[0].copy()
    del bad["role"]
    _write_assets(tmp_path, [bad])
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    with pytest.raises(ReferenceManifestError) as excinfo:
        reference_manifest.load_reference_manifest()
    assert "role" in str(excinfo.value)


# --- identity anchors: fixed face set sent alongside every generation ------


def test_identity_anchors_return_the_canonical_face(tmp_path, monkeypatch):
    _write_assets(tmp_path)
    monkeypatch.setenv("LUVIA_SOPHIA_ASSETS", str(tmp_path))

    anchors = reference_manifest.identity_anchor_references()

    roles = [ref.role for ref in anchors]
    assert roles == ["canonical_face"]
    assert anchors[0].path == tmp_path / "canonical_portrait.png"
