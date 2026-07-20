import pytest


def test_strong_recall_and_completion_ratchets_up_five():
    from plugin.pacing import next_band

    # recall in [0.85, 0.95): step up by 5.
    assert next_band(50, recall=0.90, completion=0.90, skipped_days=0) == 55


def test_excellent_recall_ratchets_up_ten():
    from plugin.pacing import next_band

    assert next_band(50, recall=0.97, completion=0.90, skipped_days=0) == 60


@pytest.mark.parametrize(
    "recall, completion, skipped_days, expected",
    [
        (0.65, 0.90, 0, 45),   # recall <0.70: down 5
        (0.90, 0.90, 3, 45),   # 3+ skipped days: down 5 even with strong recall
        (0.55, 0.90, 0, 40),   # recall <0.60: down 10
        (0.90, 0.90, 5, 40),   # 5+ skipped days: down 10
        (0.80, 0.90, 0, 50),   # between 0.70 and 0.85: hold
    ],
)
def test_ratchet_down_and_hold(recall, completion, skipped_days, expected):
    from plugin.pacing import next_band

    assert next_band(50, recall, completion, skipped_days) == expected


@pytest.mark.parametrize(
    "current, recall, completion, skipped_days, expected",
    [
        (70, 0.97, 0.90, 0, 70),   # ceiling binds: no rise above 70
        (68, 0.90, 0.90, 0, 70),   # +5 would overshoot, clamped to 70
        (35, 0.55, 0.90, 0, 35),   # floor binds: no drop below 35
        (38, 0.65, 0.90, 0, 35),   # -5 would undershoot, clamped to 35
    ],
)
def test_band_stays_within_floor_and_ceiling(
    current, recall, completion, skipped_days, expected
):
    from plugin.pacing import next_band

    assert next_band(current, recall, completion, skipped_days) == expected


def test_daily_plan_caps_reviews_and_spills_overflow():
    from plugin.pacing import daily_plan

    plan = daily_plan(band=50, due_count=130)

    assert plan["due_load"] == 100          # review-load ceiling binds
    assert plan["overflow"] == 30           # spills forward, not lost
    assert plan["new_intake"] == 7          # round(50 / 7), unaffected by backlog


def test_daily_plan_new_intake_never_starved_to_zero():
    from plugin.pacing import daily_plan

    # Even with a crushing review backlog, new intake stays positive.
    plan = daily_plan(band=35, due_count=500)

    assert plan["due_load"] == 100
    assert plan["new_intake"] >= 1


def test_current_band_replays_weekly_ratchets_from_start():
    from plugin.pacing import current_band

    # No history yet: the band sits at its start value.
    assert current_band([]) == 50

    # Two strong weeks (+5, +5) then a weak one (-5): 50 -> 55 -> 60 -> 55.
    weeks = [
        {"recall": 0.90, "completion": 0.90, "skipped_days": 0},
        {"recall": 0.90, "completion": 0.90, "skipped_days": 0},
        {"recall": 0.65, "completion": 0.90, "skipped_days": 0},
    ]
    assert current_band(weeks) == 55
