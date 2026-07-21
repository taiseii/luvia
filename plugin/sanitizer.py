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

Design notes:
- Detection is fail-closed: when in doubt about an anatomy word that is innocent
  when clothed (breasts, chest, butt) we only reject if an exposure/removal cue
  co-occurs; unambiguous tokens (nude, naked, genitals, explicit acts) reject on
  their own.
- Inputs are de-obfuscated before matching (leetspeak folding + a separator-
  stripped pass) so "n u d e", "n4k3d", and "n.u.d.e" cannot slip past.
"""

from __future__ import annotations

import re

# Leetspeak / homoglyph folding applied before matching. Conservative on
# purpose: only substitutions that overwhelmingly appear as bypass attempts,
# never ones that would routinely corrupt innocent words.
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

# Category -> list of regex patterns. Any match anywhere in the scene rejects.
# Patterns run against the leet-folded, lower-cased text.
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
        r"\bsex\b",
        r"\bintercourse\b",
        r"\bsex\s+act\b",
        r"\bsex\s?tape\b",
        r"\bblow\s?job\b",
        r"\bhand\s?job\b",
        r"\boral\s+sex\b",
        r"\banal(\s+sex)?\b",
        r"\bmasturbat\w*",
        r"\bpenetrat\w*",
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

# Distinctive single tokens re-checked against a separator-stripped copy of the
# text, catching spaced-out bypasses like "n u d e" or "n.u.d.e". Kept to long,
# unambiguous words so collapsing separators cannot forge a hit across an
# innocent word boundary.
_COMPACT_TOKENS: dict[str, str] = {
    "naked": "nudity",
    "topless": "nudity",
    "unclothed": "nudity",
    "undressed": "nudity",
    "genital": "exposed_anatomy",
    "vagina": "exposed_anatomy",
    "penis": "exposed_anatomy",
    "nipple": "exposed_anatomy",
    "areola": "exposed_anatomy",
    "clitoris": "exposed_anatomy",
    "blowjob": "explicit_act",
    "masturbat": "explicit_act",
    "penetrat": "explicit_act",
    "orgasm": "explicit_act",
    "ejaculat": "explicit_act",
    "fellatio": "explicit_act",
    "cunnilingus": "explicit_act",
    "intercourse": "explicit_act",
}

_SEPARATORS = re.compile(r"[\W_]+")

# "nude" is a nudity signal *and* a fashion color. Match it (tolerating spaced /
# punctuated obfuscation like "n u d e" or "n.u.d.e"), then subtract the
# occurrences that are plainly the color (followed by a garment/cosmetic noun).
_NUDE = re.compile(r"\bn[\W_]*u[\W_]*d[\W_]*e\b")
_NUDE_COLOR = re.compile(
    r"\bn[\W_]*u[\W_]*d[\W_]*e[\W_]+"
    r"(heels?|pumps?|sandals?|flats?|dress(es)?|gown|top|slip|lingerie|bra|"
    r"underwear|panties|clutch|bag|lip|lips|lipstick|lipgloss|gloss|"
    r"colou?red?|colou?r|tone[d]?|shade|palette|makeup|make-up|eyeshadow|"
    r"blush|manicure|nails?|polish|beige|pink)\b"
)


def _nude_is_nudity(folded: str) -> bool:
    """True when "nude" appears as nudity rather than a fashion color."""
    return len(_NUDE.findall(folded)) > len(_NUDE_COLOR.findall(folded))


def _fold(text: str) -> str:
    """Lower-case and fold common leetspeak/homoglyph substitutions."""
    return text.lower().translate(_LEET)


def sanitize(scene) -> dict:
    """Return a content-ceiling verdict for a selfie scene prompt.

    Returns a dict with:
      - "verdict":    "pass" or "reject"
      - "matched":    list of the offending phrases found (empty on pass)
      - "categories": sorted list of violated categories (empty on pass)

    Never raises: non-string input is treated as an empty scene. The ceiling is
    fixed — this function reads no configuration and takes no tuning argument.
    """
    text = scene if isinstance(scene, str) else ""
    folded = _fold(text)
    compact = _SEPARATORS.sub("", folded)

    matched: list[str] = []
    categories: set[str] = set()

    for category, patterns in _COMPILED.items():
        for pattern in patterns:
            for hit in pattern.findall(folded):
                phrase = hit if isinstance(hit, str) else next(
                    (part for part in hit if part), ""
                )
                # findall with groups returns tuples; fall back to a search for
                # the full matched span so `matched` reports something useful.
                span = pattern.search(folded)
                matched.append(span.group(0) if span else phrase)
                categories.add(category)
                break  # one hit per pattern is enough to record the violation

    for token, category in _COMPACT_TOKENS.items():
        if token in compact and category not in categories:
            matched.append(token)
            categories.add(category)

    if _nude_is_nudity(folded):
        matched.append("nude")
        categories.add("nudity")

    if categories:
        # De-duplicate matched phrases while preserving order.
        seen: set[str] = set()
        unique = [m for m in matched if not (m in seen or seen.add(m))]
        return {
            "verdict": "reject",
            "matched": unique,
            "categories": sorted(categories),
        }

    return {"verdict": "pass", "matched": [], "categories": []}
