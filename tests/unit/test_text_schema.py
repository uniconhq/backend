"""A served answer may carry a text value, a text cell and a check that
never began.
"""

from datetime import UTC, datetime

from unicon.schemas.leaderboards import LeaderboardCell
from unicon.schemas.publications import FailedCheck, Publication
from unicon.schemas.submissions import RunValue


def test_a_text_value_a_text_cell_and_an_unchecked_check_validate() -> None:
    value = RunValue.model_validate(
        {
            "name": "first_failed",
            "number": None,
            "text": "WA",
            "waiting": False,
            "self_reported": False,
        }
    )
    cell = LeaderboardCell.model_validate(
        {
            "column": "medal",
            "number": None,
            "text": "gold",
            "hidden": False,
            "counted": None,
            "waiting": None,
        }
    )
    publication = Publication.model_validate(
        {
            "number": 1,
            "version": "1",
            "grading_changed": False,
            "changes": [],
            "at": datetime(2026, 1, 1, tzinfo=UTC),
            "meanings": [],
            "check": "unchecked",
        }
    )

    failed = FailedCheck.model_validate(
        {
            "index": 1,
            "failing": ["first_failed is none, not WA."],
            "runs": [],
            "outcomes": {},
            "values": {"first_failed": "none", "total": 40},
            "error": None,
        }
    )

    assert (value.text, cell.text, publication.check) == ("WA", "gold", "unchecked")
    assert failed.values == {"first_failed": "none", "total": "40"}
