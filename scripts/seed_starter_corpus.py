#!/usr/bin/env python3
"""Prep a luvia.db for end-to-end smoke testing: load the method profiles and the
hand-enriched Dutch starter corpus. Idempotent — safe to rerun.

Targets the database at $LUVIA_DB, or ~/.hermes/luvia.db by default (the path the
tool surface uses on the Hermes box). Run:

    LUVIA_DB=/home/hermes/.hermes/luvia.db python scripts/seed_starter_corpus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plugin import store  # noqa: E402
from plugin.profiles import load_method_profiles  # noqa: E402
from plugin.seed import STARTER_CORPUS, seed_starter_corpus  # noqa: E402


def main() -> None:
    conn = store.connect()
    try:
        profiles = load_method_profiles(conn)
        inserted = seed_starter_corpus(conn)
    finally:
        conn.close()
    print(f"db:       {store.db_path()}")
    print(f"profiles: {', '.join(profiles)}")
    print(f"corpus:   {len(inserted)} inserted, {len(STARTER_CORPUS)} total")


if __name__ == "__main__":
    main()
