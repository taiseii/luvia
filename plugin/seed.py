"""A tiny hand-enriched Dutch starter corpus for end-to-end smoke testing.

This is NOT the seed pipeline (PRD 0001) — it exists so a freshly provisioned
luvia.db has a handful of fully-enriched content items to review, weave into
ambient practice, and score against, before the real ~3,000-lemma pipeline
lands. Loading is idempotent: items are matched by (lang, surface), so a rerun
never duplicates a card nor disturbs learning state.
"""

from __future__ import annotations

import sqlite3

# Everyday informal Dutch: nouns carry their de/het article in `surface`, verbs
# are infinitives, phrases are single items. frequency_rank orders the picker.
STARTER_CORPUS = (
    {"surface": "zijn", "type": "lemma", "base": "zijn", "pos": "verb", "meaning": "to be", "translation": "to be", "register": "neutral", "example": "Ik ben moe.", "rank": 1},
    {"surface": "hebben", "type": "lemma", "base": "hebben", "pos": "verb", "meaning": "to have", "translation": "to have", "register": "neutral", "example": "Heb je even tijd?", "rank": 2},
    {"surface": "gaan", "type": "lemma", "base": "gaan", "pos": "verb", "meaning": "to go", "translation": "to go", "register": "neutral", "example": "Ik ga nu weg.", "rank": 3},
    {"surface": "de man", "type": "lemma", "base": "man", "pos": "noun", "meaning": "adult male", "translation": "man", "register": "neutral", "example": "Die man daar ken ik.", "rank": 5},
    {"surface": "de vrouw", "type": "lemma", "base": "vrouw", "pos": "noun", "meaning": "adult female", "translation": "woman", "register": "neutral", "example": "Die vrouw werkt hier.", "rank": 6},
    {"surface": "het huis", "type": "lemma", "base": "huis", "pos": "noun", "meaning": "dwelling", "translation": "house", "register": "neutral", "example": "We gaan naar huis.", "rank": 8},
    {"surface": "goed", "type": "lemma", "base": "goed", "pos": "adj", "meaning": "good, well", "translation": "good", "register": "neutral", "example": "Alles goed?", "rank": 12},
    {"surface": "zitten", "type": "lemma", "base": "zitten", "pos": "verb", "meaning": "to sit", "translation": "to sit", "register": "neutral", "example": "Kom je naast me zitten?", "rank": 20},
    {"surface": "dankjewel", "type": "phrase", "base": "dankjewel", "pos": "interj", "meaning": "thanks", "translation": "thank you", "register": "informal", "example": "Dankjewel voor je hulp!", "rank": 30},
    {"surface": "leuk", "type": "lemma", "base": "leuk", "pos": "adj", "meaning": "nice, fun", "translation": "nice", "register": "informal", "example": "Wat een leuk idee!", "rank": 40},
    {"surface": "lekker", "type": "lemma", "base": "lekker", "pos": "adj", "meaning": "tasty, pleasant", "translation": "tasty", "register": "informal", "example": "Dit eten is echt lekker.", "rank": 45},
    {"surface": "de hond", "type": "lemma", "base": "hond", "pos": "noun", "meaning": "dog", "translation": "dog", "register": "neutral", "example": "De hond blaft.", "rank": 60},
    {"surface": "de kat", "type": "lemma", "base": "kat", "pos": "noun", "meaning": "cat", "translation": "cat", "register": "neutral", "example": "De kat slaapt.", "rank": 65},
    {"surface": "tot straks", "type": "phrase", "base": "tot straks", "pos": "interj", "meaning": "see you soon", "translation": "see you later", "register": "informal", "example": "Ik ga nu, tot straks!", "rank": 80},
)

LANG = "nl"


def seed_starter_corpus(conn: sqlite3.Connection) -> list[str]:
    """Insert any missing starter items into content_items, returning the surfaces
    actually inserted. Matched by (lang, surface) so reruns are no-ops."""
    inserted = []
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO languages (code, name) VALUES ('nl', 'Dutch')"
        )
        for item in STARTER_CORPUS:
            cursor = conn.execute(
                "INSERT INTO content_items"
                " (lang, item_type, surface, base_form, pos, meaning, translation,"
                " register, example, frequency_rank, source)"
                " SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'starter_corpus'"
                " WHERE NOT EXISTS ("
                " SELECT 1 FROM content_items WHERE lang = ? AND surface = ?)",
                (
                    LANG, item["type"], item["surface"], item["base"], item["pos"],
                    item["meaning"], item["translation"], item["register"],
                    item["example"], item["rank"], LANG, item["surface"],
                ),
            )
            if cursor.rowcount:
                inserted.append(item["surface"])
    return inserted
