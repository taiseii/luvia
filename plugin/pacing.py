"""Pacing band: how many genuinely-new items the learner takes on per week.

Pure functions over review histories. The band is never stored mutable state;
it is replayed from a fixed start by folding weekly ratchets over the history,
so a cron run reconstructs the same band from SQLite alone.
"""

from __future__ import annotations

BAND_START = 50
BAND_FLOOR = 35
BAND_CEILING = 70

# The binding daily constraint: a review-load ceiling so one missed day never
# creates a guilt backlog. Excess due items spill forward instead of piling on.
REVIEW_CEILING = 100


def next_band(
    current_band: int, recall: float, completion: float, skipped_days: int
) -> int:
    """One weekly ratchet step, clamped to the band's floor and ceiling.

    Strong trailing recall and completion move the band up; weak recall or too
    many skipped days move it down. Backing off wins ties (safety first)."""
    band = current_band
    if recall < 0.70 or skipped_days >= 3:
        band -= 10 if (recall < 0.60 or skipped_days >= 5) else 5
    elif recall >= 0.85 and completion >= 0.80:
        band += 10 if recall >= 0.95 else 5
    return max(BAND_FLOOR, min(BAND_CEILING, band))


def current_band(weeks: list[dict], start: int = BAND_START) -> int:
    """Replay the band from `start` by folding one ratchet per completed week.

    Each week is {"recall", "completion", "skipped_days"} in chronological order.
    With no history the band is simply its start value."""
    band = start
    for week in weeks:
        band = next_band(
            band, week["recall"], week["completion"], week["skipped_days"]
        )
    return band


def daily_new_intake(band: int) -> int:
    """The guaranteed daily allotment of genuinely-new items from the weekly
    band, floored at 1 so review backlog can never starve intake to zero."""
    return max(1, round(band / 7))


def daily_plan(band: int, due_count: int, review_ceiling: int = REVIEW_CEILING) -> dict:
    """Shape today's touches: cap review load at the ceiling with the remainder
    spilled forward, and hand back the band's guaranteed new intake untouched by
    that backlog."""
    return {
        "due_load": min(due_count, review_ceiling),
        "overflow": max(0, due_count - review_ceiling),
        "new_intake": daily_new_intake(band),
    }
