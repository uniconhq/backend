"""What a contestant is answered with is what forge gives and nothing more: a
grading carries exactly the verdict its stage's `show` let through, a
submission's inputs are read leniently from its `submission.json`, and a
file's download is named after the file, quoted when its name is not plain.
"""

import uuid
from typing import Any

import pytest
from forge.api.submissions import GradingStatus, Result, Show
from forge.api.submissions import SubmittedFiles as SubmittedFilesRecord
from forge.api.types import TaskId

from unicon.api.v1.submissions import _attachment
from unicon.schemas.submissions import Result as ResultAnswer
from unicon.schemas.submissions import SubmittedFiles

GRADING = uuid.UUID("0192f4a4-7b7e-7000-8000-000000000001")


def _result(
    show: Show,
    *,
    outcome: str | None = None,
    metrics: dict[str, Any] | None = None,
    summary: str | None = None,
    tests: tuple[dict[str, Any], ...] | None = None,
    log: bool = False,
) -> Result:
    return Result(
        id=GRADING,
        stage="default",
        attempt=2,
        status=GradingStatus.DONE,
        show=show,
        outcome=outcome,
        metrics=metrics,
        summary=summary,
        tests=tests,
        log=log,
    )


@pytest.mark.parametrize(
    ("result", "shown"),
    [
        (_result(Show.HIDDEN), {}),
        (
            _result(Show.METRICS, outcome="accepted", metrics={"score": 100}),
            {"outcome": "accepted", "metrics": {"score": 100}},
        ),
        (
            _result(
                Show.FULL,
                outcome="accepted",
                metrics={"score": 100},
                summary="All passed.",
                tests=(
                    {
                        "id": "1",
                        "outcome": "accepted",
                        "time_ms": 12,
                        "memory_kb": None,
                        "metrics": {"points": 1},
                    },
                ),
                log=True,
            ),
            {
                "outcome": "accepted",
                "metrics": {"score": 100},
                "summary": "All passed.",
                "tests": [
                    {
                        "id": "1",
                        "outcome": "accepted",
                        "time_ms": 12,
                        "memory_kb": None,
                        "metrics": {"points": 1.0},
                        "message": None,
                    }
                ],
                "log": True,
            },
        ),
    ],
    ids=["hidden", "metrics", "full"],
)
def test_a_grading_carries_what_forge_let_through_and_nothing_else(
    result: Result, shown: dict[str, object]
) -> None:
    empty = {"outcome": None, "metrics": None, "summary": None, "tests": None, "log": False}

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "id": str(GRADING),
        "stage": "default",
        "attempt": 2,
        "status": "done",
        "show": result.show.value,
        **empty,
        **shown,
    }


def test_a_submissions_inputs_are_read_leniently() -> None:
    record = SubmittedFilesRecord(
        TaskId("acme/spring/sum"),
        3,
        {
            "submission": {"files": ["files/submission/main.py", 7], "language": "python"},
            "alpha": {"value": 0.5},
            "odd": ["not", "an", "object"],
            "weights": {"files": "files/weights/model.bin", "value": {"nested": True}},
        },
    )

    answer = SubmittedFiles.model_validate(record, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "number": 3,
        "inputs": {
            "submission": {
                "files": ["files/submission/main.py"],
                "language": "python",
                "value": None,
            },
            "alpha": {"files": [], "language": None, "value": 0.5},
            "odd": {"files": [], "language": None, "value": None},
            "weights": {"files": [], "language": None, "value": None},
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
    assert _attachment(path) == header
