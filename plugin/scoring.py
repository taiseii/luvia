"""Deterministic scoring of typed answers, before any LLM judgment.

Pure functions: normalize the learner's answer and the accepted answer(s), try
an exact match, then fall back to a fuzzy ratio. Semantic judgment of ambiguous
answers stays in the carrier persona; this module only reports the deterministic
verdict so the persona knows when to escalate.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.85

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    text = _PUNCT.sub("", text)
    return _WS.sub(" ", text).strip()


def score(answer: str, expected: str | list[str]) -> dict:
    """Return {"verdict", "score", "matched"} for the best accepted answer.

    verdict is "exact" on a normalized exact match, "fuzzy" within the threshold,
    else "no_match". matched is the accepted answer that scored best.
    """
    candidates = [expected] if isinstance(expected, str) else list(expected)
    normalized_answer = normalize(answer)

    best_candidate, best_ratio = candidates[0], 0.0
    for candidate in candidates:
        normalized_candidate = normalize(candidate)
        if normalized_candidate == normalized_answer:
            return {"verdict": "exact", "score": 1.0, "matched": candidate}
        # Stdlib-only LCS-based similarity (2·M/T), equivalent to the indel ratio
        # this used to get from rapidfuzz — keeps the plugin dependency-free so it
        # loads on any host Python without a pip step.
        ratio = SequenceMatcher(None, normalized_answer, normalized_candidate).ratio()
        if ratio > best_ratio:
            best_candidate, best_ratio = candidate, ratio

    verdict = "fuzzy" if best_ratio >= FUZZY_THRESHOLD else "no_match"
    return {"verdict": verdict, "score": best_ratio, "matched": best_candidate}
