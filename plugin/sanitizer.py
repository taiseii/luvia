"""Hard no-nudity content ceiling for selfie scene prompts (PRD 0003).

A pure function: scene text in, verdict out. It runs *before* any image backend
is called and is the first of two enforcement layers (the second being the BFL
`safety_tolerance` at call time, which lands with the backend in 0015).

The ceiling is a hard rule baked into code. Suggestive-but-clothed scenes
(lingerie/underwear, bedroom, flirty framing) pass through unchanged; full
nudity, exposed genitals/breasts, and explicit acts are rejected. There is no
parameter, environment variable, or persona hook that can raise it — the only
input is the scene text.

The reject verdict is a plain data payload (verdict + matched phrases +
categories) so the calling tool can turn it into a soft, in-character
deflection. This module never raises to the chat.

Design — fail-closed throughout:
- Malformed input (anything that is not a `str`, or that cannot be normalized)
  is REJECTED, never passed. A filter that fails open is worse than useless.
- Matching runs over an aggressively normalized copy of the text:
    * Unicode NFKC (folds fullwidth `ｎｕｄｅ` and mathematical `𝚗𝚞𝚍𝚎` to ASCII),
    * format / zero-width / combining chars stripped (`s‍ex`, `nu͏de`),
    * casefold, then Greek/Cyrillic homoglyph folding (`nυde`, `nаked`),
    * leetspeak folding (`n4k3d`, `t0pless`, `$ex`).
- A word-boundary-safe "letter-run collapse" additionally neutralizes spaced-out
  bypasses (`s e x`, `p u s s y`, `n.u.d.e`) across the *whole* banned surface,
  without merging across ordinary words (so "open is the question" stays clean).
- Ambiguous anatomy that is innocent when clothed (breasts, chest, butt) rejects
  only when an exposure/removal cue co-occurs; unambiguous tokens reject alone.
"""

from __future__ import annotations

import re
import unicodedata

# --- Normalization tables ----------------------------------------------------

# Leetspeak / symbol substitutions applied before matching. Conservative on
# purpose: only substitutions that overwhelmingly appear as bypass attempts.
_LEET = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)

# Greek / Cyrillic look-alikes folded to the Latin letter they impersonate.
# NFKC does NOT touch these (they are distinct scripts), so a scene of English
# text seeded with a single confusable would otherwise slip past. Scenes are
# English, so folding these is safe.
_HOMOGLYPHS = {
    # Cyrillic
    "а": "a", "в": "b", "с": "c", "ԁ": "d", "е": "e", "г": "r", "н": "n",
    "і": "i", "ј": "j", "к": "k", "л": "l", "м": "m", "о": "o", "р": "p",
    "ѕ": "s", "т": "t", "у": "y", "х": "x", "һ": "h",
    # Greek
    "α": "a", "β": "b", "γ": "y", "ε": "e", "ζ": "z", "η": "n", "ι": "i",
    "κ": "k", "μ": "u", "ν": "v", "ο": "o", "π": "n", "ρ": "p", "σ": "s",
    "ς": "s", "τ": "t", "υ": "u", "φ": "o", "χ": "x", "ω": "w", "ϲ": "c",
}
_HOMOGLYPH = str.maketrans(_HOMOGLYPHS)


def _normalize(text: str) -> str:
    """Fold a scene to a canonical ASCII-ish form before matching.

    NFKC -> strip format/zero-width/combining marks -> casefold -> homoglyph
    fold -> leetspeak fold. Raises only if `text` is not a string, which the
    caller treats as malformed (reject).
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        ch for ch in text if unicodedata.category(ch) not in ("Cf", "Mn", "Me")
    )
    text = text.casefold()
    text = text.translate(_HOMOGLYPH)
    text = text.translate(_LEET)
    return text


# A "letter run" is 3+ single alphanumerics each separated by non-alphanumerics
# ("s e x", "n.u.d.e", "h a n d j o b"). Collapsing only these neutralizes
# spaced-out bypasses without ever merging two ordinary multi-letter words — so
# "open is the question" is left intact and cannot forge "penis".
_LETTER_RUN = re.compile(r"(?<![0-9a-z])([0-9a-z](?:[^0-9a-z]+[0-9a-z]){2,})(?![0-9a-z])")
_RUN_SEPARATORS = re.compile(r"[^0-9a-z]+")


def _collapse(text: str, keep_word_gaps: bool) -> str:
    """Collapse spaced-out single-letter runs; leave ordinary words untouched.

    Two strategies, both confined to detected runs so ordinary words are never
    merged:
      - keep_word_gaps=False: drop every separator ("t a k e s" -> "takes"),
        which recovers a single letter-spaced word.
      - keep_word_gaps=True:  drop single separators but turn a run of 2+
        separators into one space ("t a k e s   o f f" -> "takes off"), which
        recovers a letter-spaced multi-word phrase.
    """

    def collapse_run(match: re.Match) -> str:
        def sub_sep(sep: re.Match) -> str:
            return " " if keep_word_gaps and len(sep.group(0)) >= 2 else ""

        return _RUN_SEPARATORS.sub(sub_sep, match.group(1))

    return _LETTER_RUN.sub(collapse_run, text)


# --- Banned surface ----------------------------------------------------------

# Category -> list of regex patterns. Any match anywhere rejects. Patterns are
# run against each normalized text variant (folded, and letter-run-collapsed).
_PATTERNS: dict[str, list[str]] = {
    "nudity": [
        r"\bnudes\b",
        r"\bnudity\b",
        r"\bnudist\b",
        r"\bnaked(ness)?\b",
        r"\btopless\b",
        r"\bshirtless\b",
        r"\bbottomless\b",
        r"\bunclothed\b",
        r"\bundressed\b",
        r"\bundressing\b",
        r"\bdisrobed?\b",
        r"\bdisrobing\b",
        r"\bstark\s+naked\b",
        r"\bbuck\s+naked\b",
        r"\bbutt\s+naked\b",
        r"\b(fully|completely|totally|entirely)\s+nude\b",
        # Bare "nude" is handled separately (see _NUDE_* below) because it is
        # also a common fashion color ("nude heels", "nude lipstick").
        r"\bin\s+the\s+nude\b",
        r"\bin\s+the\s+buff\b",
        r"\bin\s+the\s+raw\b",
        r"\bbirthday\s+suit\b",
        r"\bau\s+naturel\b",
        r"\bnothing\s+on\b",
        r"\bwith\s+nothing\s+on\b",
        r"\bwear(s|ing)?\s+nothing\b",
        r"\bwear(s|ing)?\s+nothing\s+but\b",
        r"\bwear(s|ing)?\s+only\s+a\s+smile\b",
        r"\bnot\s+wearing\s+anything\b",
        r"\bnothing\s+but\s+(her\s+)?(bare\s+)?skin\b",
        r"\bno\s+clothes\b",
        r"\bwithout\s+(any\s+)?(clothes|clothing)\b",
    ],
    "exposed_anatomy": [
        # Unambiguous private anatomy — reject on sight.
        r"\bgenital(s|ia)?\b",
        r"\bvagina[l]?\b",
        r"\bvulva\b",
        r"\bpussy\b",
        r"\bclit(oris)?\b",
        r"\bpenis\b",
        r"\bpenile\b",
        r"\bcock\b",
        r"\bdicks?\b",
        r"\btesticles?\b",
        r"\bscrotum\b",
        r"\bnipples?\b",
        r"\bareola[e]?\b",
        r"\btits\b",
        r"\bpubic\b",
        r"\bcrotch\b",
        # Ambiguous anatomy (innocent when clothed) + an exposure cue nearby.
        r"\bbare\s+(breasts?|boobs?|chest|butt|ass|buttocks?|bottom|behind)\b",
        r"\b(breasts?|boobs?|butt|ass|buttocks?|chest|behind|bottom)\b"
        r"(?:\W+\w+){0,3}?\W+"
        r"(exposed|out|bared|uncovered|showing|visible|spilling\s+out)\b",
        r"\b(exposed|exposing|uncovered|bared|revealing|flash(es|ing)?)\b"
        r"(?:\W+\w+){0,3}?\W+"
        r"(breasts?|boobs?|butt|ass|buttocks?|chest|behind|bottom|genital)",
    ],
    "explicit_act": [
        # "same-sex" / "opposite-sex" describe orientation, not an act.
        r"(?<!same.)(?<!opposite.)\bsex\b",
        r"\bintercourse\b",
        r"\bsex\s+act\b",
        r"\bsex\s?tape\b",
        r"\bblow\s?job\b",
        r"\bhand\s?job\b",
        r"\boral\s+sex\b",
        r"\banal(\s+sex)?\b",
        r"\bmasturbat\w*",
        # "penetrating gaze/stare/look" is not sexual — exclude those.
        r"\bpenetrat\w*\b(?!\s+(?:gaze|gazes|stare|stares|staring|look|looks|"
        r"looking|eyes|glance|glances|insight|insights?|questions?))",
        r"\borgasm\w*",
        r"\bejaculat\w*",
        r"\bcum(shot|ming|s)?\b",
        r"\bfellatio\b",
        r"\bcunnilingus\b",
        r"\bcoitus\b",
        r"\bfinger(ing|s)?\s+(herself|her\s+\w+)\b",
        r"\btouch(ing|es)?\s+herself\b",
        r"\bspread(ing)?\s+(her\s+)?legs\b",
        r"\blegs\s+spread\b",
        r"\bspread\s+eagle\b",
        r"\bdoggy\s?style\b",
        r"\bmaking\s+love\b",
        r"\bgives?\s+head\b",
        r"\bgiving\s+head\b",
        r"\bgo(es|ing)?\s+down\s+on\s+(her|him)\b",
        r"\bporn\w*\b",
        r"\bnsfw\b",
        r"\bxxx\b",
        r"\bhardcore\b",
        r"\bx[-\s]?rated\b",
        r"\bexplicit\b",
    ],
    "undressing": [
        r"\b(takes?|took|taking)\s+off\s+(all\s+)?(her\s+|the\s+)?"
        r"(top|bra|shirt|clothes|clothing|underwear|panties|dress|everything|it\s+all)\b",
        r"\b(takes?|took|taking)\s+(everything|it\s+all|her\s+(top|bra|shirt|clothes|"
        r"clothing|underwear|panties|dress))\s+off\b",
        r"\b(removes?|removing)\s+(her\s+|the\s+)?"
        r"(top|bra|shirt|clothes|clothing|underwear|panties|dress)\b",
        r"\bslip(s|ping)?\s+out\s+of\s+(her\s+)?"
        r"(dress|clothes|top|bra|underwear|panties)\b",
        r"\bpull(s|ing)?\s+(down|off)\s+(her\s+)?"
        r"(top|bra|panties|underwear|dress|shirt)\b",
        r"\b(top|bra|clothes|dress|panties)\s+off\b",
        # "strip" must carry an undress cue — a "strip of light" is innocent.
        r"\bstrips?\s+(down|off|naked|nude)\b",
        r"\bstrips?\s+(out\s+of|to\s+(her|nothing))\b",
        r"\bstripping\s+(down|off|naked|nude)\b",
        r"\bstriptease\b",
    ],
}

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    category: [re.compile(p) for p in patterns]
    for category, patterns in _PATTERNS.items()
}

# "nude" is a nudity signal *and* a fashion color. It rejects unless every
# occurrence is plainly the color (followed by a garment/cosmetic noun).
# Obfuscated spellings ("n u d e", "n.u.d.e") are already collapsed to "nude"
# before this runs, so a plain word match suffices.
_NUDE = re.compile(r"\bnude\b")
_NUDE_COLOR = re.compile(
    r"\bnude[\s-]+"
    r"(heels?|pumps?|sandals?|flats?|dress(es)?|gown|top|slip|lingerie|bra|"
    r"underwear|panties|clutch|bag|lip|lips|lipstick|lipgloss|gloss|"
    r"colou?red?|colou?r|tone[d]?|shade|palette|makeup|make-up|eyeshadow|"
    r"blush|manicure|nails?|polish|beige|pink)\b"
)


def _nude_is_nudity(variant: str) -> bool:
    """True when "nude" appears as nudity rather than a fashion color."""
    return len(_NUDE.findall(variant)) > len(_NUDE_COLOR.findall(variant))


# --- Public API --------------------------------------------------------------

_PASS = {"verdict": "pass", "matched": [], "categories": []}


def _reject(matched: list[str], categories: list[str]) -> dict:
    return {
        "verdict": "reject",
        "matched": matched,
        "categories": sorted(set(categories)),
    }


def _scan(variant: str, matched: list[str], categories: set[str]) -> None:
    for category, patterns in _COMPILED.items():
        for pattern in patterns:
            m = pattern.search(variant)  # early-exit search, not findall
            if m:
                matched.append(m.group(0))
                categories.add(category)
    if _nude_is_nudity(variant):
        matched.append("nude")
        categories.add("nudity")


def sanitize(scene) -> dict:
    """Return a content-ceiling verdict for a selfie scene prompt.

    Returns a dict with:
      - "verdict":    "pass" or "reject"
      - "matched":    list of the offending phrases found (empty on pass)
      - "categories": sorted list of violated categories (empty on pass)

    Fail-closed: anything that is not a `str`, or that cannot be normalized, is
    REJECTED as malformed rather than waved through. Never raises. The ceiling is
    fixed — this function reads no configuration and takes no tuning argument.
    """
    if not isinstance(scene, str):
        return _reject(["<non-text scene rejected>"], ["malformed"])

    try:
        folded = _normalize(scene)
        variants = (
            folded,
            _collapse(folded, keep_word_gaps=False),
            _collapse(folded, keep_word_gaps=True),
        )
    except Exception:
        return _reject(["<unprocessable scene rejected>"], ["malformed"])

    matched: list[str] = []
    categories: set[str] = set()
    # dict.fromkeys de-duplicates while preserving order (folded first).
    for variant in dict.fromkeys(variants):
        _scan(variant, matched, categories)

    if not categories:
        return dict(_PASS)

    seen: set[str] = set()
    unique = [m for m in matched if not (m in seen or seen.add(m))]
    return _reject(unique, sorted(categories))
