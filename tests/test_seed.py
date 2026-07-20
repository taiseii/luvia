from plugin import store
from plugin.seed import STARTER_CORPUS, seed_starter_corpus


def test_seed_loads_enriched_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()

    inserted = seed_starter_corpus(conn)

    assert len(inserted) == len(STARTER_CORPUS)
    rows = conn.execute(
        "SELECT surface, translation, register, example FROM content_items"
        " WHERE lang = 'nl'"
    ).fetchall()
    assert len(rows) == len(STARTER_CORPUS)
    # Every item is fully enriched — no hollow rows that would make e2e meaningless.
    for surface, translation, register, example in rows:
        assert surface and translation and register and example


def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    conn = store.connect()

    seed_starter_corpus(conn)
    second = seed_starter_corpus(conn)

    assert second == []  # nothing re-inserted on a rerun
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM content_items WHERE lang = 'nl'"
    ).fetchone()
    assert count == len(STARTER_CORPUS)
