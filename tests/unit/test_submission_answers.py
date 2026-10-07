"""What a contestant is answered with is what forge gives and nothing more: a
grading carries exactly what the task's test groups let through, a group
that did not run on it marked so, its numbers as JSON numbers, a
submission's inputs are read leniently from its `submission.json`, and a
file's download is named after the file, quoted when its name is not plain.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
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
        "values": {},
    }


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
                        "values": {"time_ms": 12, "fraction": 0.25},
                    }
                ],
                "shown_at": None,
                "ran": True,
            },
            {
                "group": "small",
                "show": "verdict",
                "outcome": "wrong_answer",
                "tests": None,
                "shown_at": "2026-09-26T15:00:00Z",
                "ran": True,
            },
            {
                "group": "large",
                "show": "after_close",
                "outcome": None,
                "tests": None,
                "shown_at": "2026-09-26T15:00:00Z",
                "ran": True,
            },
            {
                "group": "extra",
                "show": "always",
                "outcome": None,
                "tests": [],
                "shown_at": None,
                "ran": False,
            },
        ],
        "values": {"log": "", "score": 1.5},
    }
    served = json.loads(answer.model_dump_json())
    assert served["values"]["score"] == 1.5
    assert served["groups"][0]["tests"][0]["values"]["fraction"] == 0.25


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
