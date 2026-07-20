from datetime import datetime, timedelta, timezone

import pytest

from plugin.scheduler import Grade, SM2Scheduler

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "grades, expected_intervals",
    [
        ([Grade.good, Grade.good, Grade.good], [1.0, 6.0, 15.0]),
        ([Grade.easy, Grade.easy, Grade.easy], [1.0, 6.0, 16.8]),
        ([Grade.again], [1.0]),
        ([Grade.good, Grade.good, Grade.again, Grade.good], [1.0, 6.0, 1.0, 1.0]),
    ],
)
def test_sm2_interval_progression(grades, expected_intervals):
    sched = SM2Scheduler()
    state: dict = {}
    intervals = []
    for grade in grades:
        state, due = sched.schedule(state, grade, NOW)
        intervals.append(state["interval_days"])
        assert due == NOW + timedelta(days=state["interval_days"])
    assert intervals == pytest.approx(expected_intervals)
