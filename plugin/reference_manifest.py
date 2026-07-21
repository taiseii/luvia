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
        raise RuntimeError(
            f"{ASSETS_ENV_VAR} is not set and no assets_dir was provided; "
            "the reference library location is unknown."
        )
    return Path(env)


def load_reference_manifest(assets_dir_path: Path | str | None = None) -> list[Reference]:
    """Parse ``manifest.json`` into Reference rows with resolved absolute paths."""
    directory = assets_dir(assets_dir_path)
    manifest_path = directory / MANIFEST_FILENAME
    rows = json.loads(manifest_path.read_text())
    return [
        Reference(
            file=row["file"],
            role=row["role"],
            framing=row["framing"],
            setting=row["setting"],
            tags=tuple(row.get("tags", [])),
            description=row["description"],
            default=bool(row["default"]),
            path=(directory / row["file"]).resolve(),
        )
        for row in rows
    ]


def resolve_reference_role(
    reference_role: str | None,
    assets_dir: Path | str | None = None,
) -> Reference:
    """Map a persona-chosen role to a concrete reference, falling back to portrait.

    A role that matches manifest rows returns the default-flagged match (or the
    first match if none is flagged). A missing, empty, or unknown role falls back
    to the canonical face portrait — the single ``default`` row.
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


def _default_portrait(manifest: list[Reference]) -> Reference:
    """The fallback reference: the single default-flagged canonical face portrait."""
    for ref in manifest:
        if ref.default:
            return ref
    raise ValueError(
        "reference manifest declares no default portrait; cannot apply fallback."
    )
