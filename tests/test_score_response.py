from pathlib import Path

import pytest
import yaml

MANIFEST = Path(__file__).parent.parent / "plugin" / "plugin.yaml"


def test_score_response_declared_in_manifest():
    manifest = yaml.safe_load(MANIFEST.read_text())
    assert "luvia_score_response" in manifest["provides_tools"]


def test_scoring_has_no_scheduling_side_effect(tmp_path, monkeypatch):
    db_path = tmp_path / "luvia.db"
    monkeypatch.setenv("LUVIA_DB", str(db_path))

    from plugin.tools import luvia_score_response

    luvia_score_response(answer="het huis", expected="het huis")

    # Pure scoring: no session, event, or learner-item state is written.
    assert not db_path.exists()


def test_normalized_exact_match_ignores_case_whitespace_punctuation():
    from plugin.tools import luvia_score_response

    result = luvia_score_response(answer="  Het Huis! ", expected="het huis")

    assert result["verdict"] == "exact"
    assert result["score"] == 1.0
    assert result["matched"] == "het huis"


def test_fuzzy_near_miss_within_threshold_accepted():
    from plugin.tools import luvia_score_response

    # One dropped letter in a long word: well inside the fuzzy threshold.
    result = luvia_score_response(answer="goedemorgn", expected="goedemorgen")

    assert result["verdict"] == "fuzzy"
    assert result["score"] >= 0.85
    assert result["matched"] == "goedemorgen"


@pytest.mark.parametrize(
    "answer, expected, verdict",
    [
        ("computer", "computer", "exact"),      # 1.00
        ("appel", "appels", "fuzzy"),           # 0.909
        ("camputer", "computer", "fuzzy"),      # 0.875, just above threshold
        ("hus", "huis", "fuzzy"),               # 0.857, just above threshold
        ("ziekle", "ziekte", "no_match"),       # 0.833, just below threshold
        ("goedemorgen", "tot ziens", "no_match"),  # 0.300, clear reject
    ],
)
def test_threshold_boundary_cases(answer, expected, verdict):
    from plugin.tools import luvia_score_response

    assert luvia_score_response(answer=answer, expected=expected)["verdict"] == verdict


def test_multiple_accepted_answers_match_any():
    from plugin.tools import luvia_score_response

    accepted = ["couch", "sofa", "settee"]

    exact = luvia_score_response(answer="Sofa", expected=accepted)
    assert exact["verdict"] == "exact"
    assert exact["matched"] == "sofa"

    fuzzy = luvia_score_response(answer="sette", expected=accepted)
    assert fuzzy["verdict"] == "fuzzy"
    assert fuzzy["matched"] == "settee"
