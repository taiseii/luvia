"""Method profiles: named methodology bundles expressed as YAML config.

Phase 1 ships two — frequency_srs and communicative_hybrid. Each profile's
methodology lives verbatim in a YAML file under profiles/; this module owns the
stable identity (id, label, version) that becomes the method_profiles row and
loads the file text into config_yaml as-is. Nothing here parses or acts on the
config — mixing and mechanism logic stay out of the loader.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

# Identity lives here, methodology lives in the YAML file. Keeping id/label/version
# out of the YAML avoids a runtime YAML parser (pyyaml is dev-only) and a second
# source of truth for the columns; config_yaml stores the file text as-is so
# downstream consumers own the parsing.
_PROFILES = (
    {
        "id": "frequency_srs",
        "label": "Frequency SRS",
        "version": 1,
        "filename": "frequency_srs.yaml",
    },
    {
        "id": "communicative_hybrid",
        "label": "Communicative Hybrid",
        "version": 1,
        "filename": "communicative_hybrid.yaml",
    },
)


def load_method_profiles(conn: sqlite3.Connection) -> list[str]:
    """Upsert every shipped profile into method_profiles, returning the ids loaded.

    Idempotent: the upsert overwrites the same row by primary key, so a second run
    never duplicates a profile nor bumps version on its own — version only changes
    when the _PROFILES entry (and the YAML behind it) changes.
    """
    loaded = []
    with conn:
        for profile in _PROFILES:
            config_yaml = (PROFILES_DIR / profile["filename"]).read_text()
            conn.execute(
                "INSERT INTO method_profiles (id, label, version, config_yaml, active)"
                " VALUES (?, ?, ?, ?, 1)"
                " ON CONFLICT(id) DO UPDATE SET"
                " label = excluded.label, version = excluded.version,"
                " config_yaml = excluded.config_yaml, active = excluded.active",
                (profile["id"], profile["label"], profile["version"], config_yaml),
            )
            loaded.append(profile["id"])
    return loaded
