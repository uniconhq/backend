"""What a contestant is answered with is what forge gives and nothing more: a
grading carries exactly what the task's test groups let through, a group
that did not run on it marked so, its numbers and its points as exact
decimal strings, a submission's inputs are read leniently from its
`submission.json`, and a file's download is named after the file, quoted
when its name is not plain.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from forge.api.boards import Points
from forge.api.submissions import GradingStatus, GroupShown, Result, Show
from forge.api.submissions import SubmittedFiles as SubmittedFilesRecord
from forge.api.types import TaskId

from unicon.api.door import attachment
from unicon.schemas.submissions import Result as ResultAnswer
from unicon.schemas.submissions import SubmittedFiles

GRADING = uuid.UUID("0192f4a4-7b7e-7000-8000-000000000001")
REVEAL = datetime(2026, 9, 26, 15, tzinfo=UTC)


def test_a_grading_being_run_carries_its_status_alone() -> None:
    result = Result(GRADING, 2, GradingStatus.RUNNING, None, None, (), {})

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "id": str(GRADING),
        "attempt": 2,
        "status": "running",
        "stopped": None,
        "outcome": None,
        "groups": [],
        "values": {"numbers": {}, "texts": {}},
        "reason": None,
        "points": None,
        "factor": None,
    }


def test_a_grading_staff_cancelled_carries_their_sentence() -> None:
    result = Result(GRADING, 1, GradingStatus.CANCELLED, None, None, (), {}, "Not counted.")

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert (answer["status"], answer["reason"], answer["groups"]) == (
        "cancelled",
        "Not counted.",
        [],
    )


def test_a_grading_carries_each_group_as_forge_let_it_through() -> None:
    row = {
        "test": "samples/1",
        "outcome": "accepted",
        "values": {"time_ms": 12, "fraction": Decimal("0.25")},
    }
    result = Result(
        GRADING,
        1,
        GradingStatus.DONE,
        None,
        "wrong_answer",
        (
            GroupShown("samples", Show.ALWAYS, "accepted", (row,), None),
            GroupShown("small", Show.VERDICT, "wrong_answer", None, REVEAL),
            GroupShown("large", Show.AFTER_CLOSE, None, None, REVEAL),
            GroupShown("extra", Show.ALWAYS, None, (), None, ran=False),
        ),
        {"log": "", "score": Decimal("1.5")},
    )

    answer = ResultAnswer.model_validate(result, from_attributes=True)

    assert answer.model_dump(mode="json") == {
        "id": str(GRADING),
        "attempt": 1,
        "status": "done",
        "stopped": None,
        "outcome": "wrong_answer",
        "groups": [
            {
                "group": "samples",
                "show": "always",
                "outcome": "accepted",
                "tests": [
                    {
                        "test": "samples/1",
                        "outcome": "accepted",
                        "values": {"numbers": {"time_ms": "12", "fraction": "0.25"}, "texts": {}},
                        "credit": None,
                        "best": None,
                    }
                ],
                "shown_at": None,
                "ran": True,
                "points": None,
                "max": None,
            },
            {
                "group": "small",
                "show": "verdict",
                "outcome": "wrong_answer",
                "tests": None,
                "shown_at": "2026-09-26T15:00:00Z",
                "ran": True,
                "points": None,
                "max": None,
            },
            {
                "group": "large",
                "show": "after_close",
                "outcome": None,
                "tests": None,
                "shown_at": "2026-09-26T15:00:00Z",
                "ran": True,
                "points": None,
                "max": None,
            },
            {
                "group": "extra",
                "show": "always",
                "outcome": None,
                "tests": [],
                "shown_at": None,
                "ran": False,
                "points": None,
                "max": None,
            },
        ],
        "values": {"numbers": {"score": "1.5"}, "texts": {"log": ""}},
        "reason": None,
        "points": None,
        "factor": None,
    }


def test_numbers_are_served_as_exact_decimals_and_text_stays_text() -> None:
    row = {
        "test": "main/1",
        "outcome": "accepted",
        "values": {"loss": Decimal("0.1000000000000000000000000001"), "label": "12.5"},
        "credit": Fraction(1, 3),
        "best": Decimal("0.05"),
    }
    result = Result(
        GRADING,
        1,
        GradingStatus.DONE,
        None,
        "accepted",
        (
            GroupShown(
                "main",
                Show.ALWAYS,
                "accepted",
                (row,),
                None,
                points=Fraction(85, 3),
                max=Fraction(85),
            ),
            GroupShown("large", Show.AFTER_CLOSE, None, None, REVEAL, max=Fraction(15)),
        ),
        {"total": 10**20},
        points=Points(Fraction(85, 3), Fraction(15), REVEAL),
        factor=Fraction(9, 10),
    )

    served = json.loads(ResultAnswer.model_validate(result, from_attributes=True).model_dump_json())

    [main, large] = served["groups"]
    [test] = main["tests"]
    assert test["values"] == {
        "numbers": {"loss": "0.1000000000000000000000000001"},
        "texts": {"label": "12.5"},
    }
    assert (test["credit"], test["best"]) == ("0." + "3" * 30, "0.05")
    assert (main["points"], main["max"]) == ("28." + "3" * 28, "85")
    assert (large["points"], large["max"]) == (None, "15")
    assert served["values"] == {"numbers": {"total": "100000000000000000000"}, "texts": {}}
    assert served["points"] == {
        "shown": "28." + "3" * 28,
        "pending": "15",
        "pending_until": "2026-09-26T15:00:00Z",
    }
    assert served["factor"] == "0.9"


def test_a_submissions_inputs_are_read_leniently() -> None:
    record = SubmittedFilesRecord(
        TaskId("acme/spring/sum"),
        3,
        {
            "submission": {"files": ["files/submission/main.py", 7]},
            "language": {"value": "python"},
            "alpha": {"value": 0.5},
            "odd": ["not", "an", "object"],
            "weights": {"files": "files/weights/model.bin", "value": {"nested": True}},
        },
    )

    answer = SubmittedFiles.model_validate(record, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "number": 3,
        "inputs": {
            "submission": {"files": ["files/submission/main.py"], "value": None},
            "language": {"files": [], "value": "python"},
            "alpha": {"files": [], "value": 0.5},
            "odd": {"files": [], "value": None},
            "weights": {"files": [], "value": None},
        },
    }


@pytest.mark.parametrize(
    ("path", "header"),
    [
        ("files/submission/main.py", 'attachment; filename="main.py"'),
        ("files/notes/my notes.txt", "attachment; filename*=UTF-8''my%20notes.txt"),
        ('files/notes/"x";.txt', "attachment; filename*=UTF-8''%22x%22%3B.txt"),
        ("files/notes/résumé.pdf", "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf"),
    ],
    ids=["plain", "a space", "quotes", "not ascii"],
)
def test_a_download_is_named_after_the_file(path: str, header: str) -> None:
    assert attachment(path) == header
