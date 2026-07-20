"""Swappable spaced-repetition scheduler.

The scheduler is reached only through the `schedule(state, grade, now)`
interface and its state is an opaque JSON-serializable dict stored in
`learner_items.scheduler_state_json`. Nothing about a given algorithm's
parameters leaks into the schema, so SM-2 can later be swapped for FSRS with a
migration and no data loss.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum


class Grade(str, Enum):
    again = "again"
    good = "good"
    easy = "easy"
    already_knew = "already_knew"


_REGISTRY: dict[str, object] = {}


def register(name: str, scheduler: object) -> None:
    _REGISTRY[name] = scheduler


def get(name: str) -> object:
    return _REGISTRY[name]


class SM2Scheduler:
    """SM-2 variant mapping the three review grades onto the classic algorithm.

    State: {"repetitions": int, "ef": float, "interval_days": float}.
    """

    MIN_EF = 1.3
    QUALITY = {Grade.again: 2, Grade.good: 4, Grade.easy: 5}

    def schedule(
        self, state: dict, grade: Grade, now: datetime
    ) -> tuple[dict, datetime]:
        if grade == Grade.already_knew:
            raise ValueError(
                "grade 'already_knew' is not supported until issue 0003"
            )

        repetitions = state.get("repetitions", 0)
        ef = state.get("ef", 2.5)
        interval = state.get("interval_days", 0.0)

        quality = self.QUALITY[grade]
        ef = max(self.MIN_EF, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

        if grade == Grade.again:
            repetitions = 0
            interval = 1.0
        else:
            if repetitions == 0:
                interval = 1.0
            elif repetitions == 1:
                interval = 6.0
            else:
                interval = round(interval * ef, 4)
            repetitions += 1

        new_state = {"repetitions": repetitions, "ef": ef, "interval_days": interval}
        due = now + timedelta(days=interval)
        return new_state, due


register("sm2", SM2Scheduler())
