"""Reference-manifest resolver: persona-chosen role -> concrete reference image.

Sophia's selfies are each a single edit-hop off one of a fixed, hand-curated
set of reference images (ADR 0002). Those images plus a colocated
``manifest.json`` live only on the box under ``LUVIA_SOPHIA_ASSETS`` — never in
the repo, since her likeness must not land on public GitHub (``assets/sophie/``
is gitignored). This module reads that manifest and maps a role chosen upstream
by the persona to a concrete file on disk.

It is deliberately named the *reference* manifest to keep it distinct from the
plugin's content/tool manifest (``plugin.yaml``). Resolution is read-only: the
library is fixed and never auto-grows — generated selfies are never fed back in,
because identity consistency is the whole point (ADR 0002). There is no
code-side fuzzy scene matching here; the persona picks the role, this slice only
resolves the role to its file and applies the portrait fallback.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MANIFEST_FILENAME = "manifest.json"
ASSETS_ENV_VAR = "LUVIA_SOPHIA_ASSETS"

# The canonical face portrait is the fallback whenever a role is missing,
# unspecified, or not present in the manifest.
CANONICAL_FACE_ROLE = "canonical_face"

_REQUIRED_FIELDS = ("file", "role", "framing", "setting", "description", "default")


class ReferenceManifestError(Exception):
    """Raised when the reference manifest is missing, malformed, or unsafe.

    Carries enough context (the manifest path and the offending row/field) to
    make on-box authoring mistakes debuggable instead of surfacing later as an
    opaque backend failure.
    """


@dataclass(frozen=True)
class Reference:
    """One resolved manifest row, with its image path made absolute on the box.

    Mirrors the per-image manifest schema plus a resolved ``path``. Nothing here
    reads the image bytes — that is the image backend's job downstream.
    """

    file: str
    role: str
    framing: str
    setting: str
    tags: tuple[str, ...]
    description: str
    default: bool
    path: Path


def assets_dir(assets_dir: Path | str | None = None) -> Path:
    """Resolve the assets directory, preferring an explicit arg over the env var.

    Keeping the env read behind an optional argument lets callers (and tests)
    treat resolution as a pure function of an explicit directory while the box
    still gets its location from ``LUVIA_SOPHIA_ASSETS`` by default.
    """
    if assets_dir is not None:
        return Path(assets_dir)
    env = os.environ.get(ASSETS_ENV_VAR)
    if not env:
        raise ReferenceManifestError(
            f"{ASSETS_ENV_VAR} is not set and no assets_dir was provided; "
            "the reference library location is unknown."
        )
    return Path(env)


def load_reference_manifest(assets_dir_path: Path | str | None = None) -> list[Reference]:
    """Parse ``manifest.json`` into Reference rows with resolved absolute paths.

    Every row is validated at load: required fields present, the ``file`` path
    contained within the assets dir (no ``../`` escape, no absolute path, no
    symlink out), and the target image actually present on disk. A resolver that
    hands back a Reference is thus one the backend can trust.
    """
    directory = assets_dir(assets_dir_path)
    base = directory.resolve()
    manifest_path = directory / MANIFEST_FILENAME

    try:
        raw = manifest_path.read_text()
    except OSError as exc:
        raise ReferenceManifestError(
            f"cannot read reference manifest at {manifest_path}: {exc}"
        ) from exc

    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReferenceManifestError(
            f"{manifest_path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(rows, list):
        raise ReferenceManifestError(
            f"{manifest_path} must contain a JSON array of image rows."
        )

    return [
        _build_reference(row, index, base, manifest_path)
        for index, row in enumerate(rows)
    ]


def _build_reference(row: object, index: int, base: Path, manifest_path: Path) -> Reference:
    if not isinstance(row, dict):
        raise ReferenceManifestError(
            f"{manifest_path} row {index} is not a JSON object."
        )
    for field in _REQUIRED_FIELDS:
        if field not in row:
            raise ReferenceManifestError(
                f"{manifest_path} row {index} is missing required field '{field}'."
            )

    file = row["file"]
    path = _resolve_contained_path(file, index, base, manifest_path)

    return Reference(
        file=file,
        role=row["role"],
        framing=row["framing"],
        setting=row["setting"],
        tags=tuple(row.get("tags", [])),
        description=row["description"],
        default=bool(row["default"]),
        path=path,
    )


def _resolve_contained_path(file: str, index: int, base: Path, manifest_path: Path) -> Path:
    """Resolve ``file`` under ``base``, rejecting escapes and missing images.

    The ``file`` value is manifest-controlled and must never be trusted to stay
    inside the library: an absolute path, a ``../`` climb, or a symlink pointing
    out would let a tampered manifest read arbitrary files. So we reject absolute
    paths outright and require the *resolved* path to remain within the assets
    dir, then confirm the image actually exists.
    """
    candidate = Path(file)
    if candidate.is_absolute():
        raise ReferenceManifestError(
            f"{manifest_path} row {index} file '{file}' must be relative to the "
            "assets dir, not an absolute path."
        )

    resolved = (base / candidate).resolve()
    if not resolved.is_relative_to(base):
        raise ReferenceManifestError(
            f"{manifest_path} row {index} file '{file}' resolves outside the "
            f"assets dir ({base}); path traversal is not allowed."
        )
    if not resolved.is_file():
        raise ReferenceManifestError(
            f"{manifest_path} row {index} references missing image file '{file}' "
            f"(expected at {resolved})."
        )
    return resolved


def resolve_reference_role(
    reference_role: str | None,
    assets_dir: Path | str | None = None,
) -> Reference:
    """Map a persona-chosen role to a concrete reference, falling back to portrait.

    A role that matches manifest rows returns the default-flagged match (or the
    first match if none is flagged). A missing, empty, or unknown role falls back
    to the canonical face portrait — the default-flagged canonical-face row.
    """
    manifest = load_reference_manifest(assets_dir)

    if reference_role:
        matches = [ref for ref in manifest if ref.role == reference_role]
        if matches:
            for ref in matches:
                if ref.default:
                    return ref
            return matches[0]

    return _default_portrait(manifest)


def identity_anchor_references(
    assets_dir: Path | str | None = None,
) -> list[Reference]:
    """The fixed identity-anchor set sent alongside every generated selfie.

    These travel as the backend's ``extra_references`` (``input_image_2..N``) so
    the model triangulates the face rather than extrapolating from one frame. The
    set is fixed here, never persona-chosen — same capability/persona split as the
    pinned POV and safety tolerance. Today it is the canonical-face portrait; when
    more curated face angles land (0018), add their rows here and every selfie
    gains fidelity with no caller change.
    """
    manifest = load_reference_manifest(assets_dir)
    return [_default_portrait(manifest)]


def _default_portrait(manifest: list[Reference]) -> Reference:
    """The fallback reference: the default-flagged canonical-face portrait.

    The fallback must be the portrait specifically — a ``default`` flag on a pose
    row must not hijack missing/unknown-role resolution into returning a pose, or
    the portrait-fallback invariant breaks. We require exactly one default
    canonical-face row.
    """
    portraits = [
        ref for ref in manifest if ref.default and ref.role == CANONICAL_FACE_ROLE
    ]
    if not portraits:
        raise ReferenceManifestError(
            "reference manifest declares no default "
            f"'{CANONICAL_FACE_ROLE}' portrait; cannot apply fallback."
        )
    if len(portraits) > 1:
        raise ReferenceManifestError(
            "reference manifest declares multiple default "
            f"'{CANONICAL_FACE_ROLE}' portraits; the fallback is ambiguous."
        )
    return portraits[0]
