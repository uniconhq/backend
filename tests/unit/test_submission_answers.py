"""What a contestant is answered with is what forge gives and nothing more: a
grading carries its runs as forge shows them and when it reveals, its
numbers as exact decimal strings and its text as text, a submission's inputs
are read leniently from its `submission.json`, and a file's download is
named after the file, quoted when its name is not plain.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from forge.api.submissions import GradingStatus, Result, SubmissionState, ValueShown
from forge.api.submissions import SubmittedFiles as SubmittedFilesRecord
from forge.api.types import TaskId

from unicon.api.door import attachment
from unicon.schemas.submissions import OrganisedResult, SubmittedFiles
from unicon.schemas.submissions import Result as ResultAnswer

GRADING = uuid.UUID("0192f4a4-7b7e-7000-8000-000000000001")
REVEAL = datetime(2026, 9, 26, 15, tzinfo=UTC)


def test_a_grading_being_run_carries_its_status_alone() -> None:
    result = Result(GRADING, 2, SubmissionState.GRADING)

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "id": str(GRADING),
        "attempt": 2,
        "status": "grading",
        "reason": None,
        "limit": None,
        "runs": [],
        "reveal_at": None,
        "run_values": [],
        "once": {"reports": {}, "texts": {}},
        "compiled": None,
    }


def test_a_grading_staff_cancelled_carries_their_sentence() -> None:
    result = Result(GRADING, 1, SubmissionState.CANCELLED, "Not counted.")

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert (answer["status"], answer["reason"], answer["runs"]) == (
        "cancelled",
        "Not counted.",
        [],
    )


def test_a_grading_carries_each_run_with_exact_numbers_its_texts_and_reveal() -> None:
    run = {
        "group": "sample_tests",
        "place": 1,
        "tuples": [
            {"title": "Small grid", "key": {"input": "samples/1.in"}},
            {"title": None, "key": {"seed": 2}},
        ],
        "verdict": "accepted",
        "passed": 1,
        "reports": [
            {"title": "Run time", "unit": "ms", "number": 12},
            {"title": "Memory used", "unit": "KB", "number": Decimal("2048")},
        ],
        # An entrant is sent where a text is, never the output holding it.
        "texts": {"log": {}},
        "message": {},
    }
    result = Result(GRADING, 1, SubmissionState.GRADED, runs=(run,), reveal_at=REVEAL)

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer["reveal_at"] == "2026-09-26T15:00:00Z"
    assert answer["runs"] == [
        {
            "group": "sample_tests",
            "place": 1,
            "id": None,
            "dropped": False,
            "tuples": [
                {"title": "Small grid", "key": {"input": "samples/1.in"}},
                {"title": None, "key": {"seed": 2}},
            ],
            "verdict": "accepted",
            "passed": 1,
            "reports": [
                {"title": "Run time", "unit": "ms", "number": "12"},
                {"title": "Memory used", "unit": "KB", "number": "2048"},
            ],
            "texts": {"log": {"output": None, "name": None}},
            "label": None,
            "message": {"output": None, "name": None},
        }
    ]


def test_a_gradings_values_once_and_compiled_are_served_exactly() -> None:
    log = {"output": "0192f4a4-7b7e-7000-8000-000000000002", "name": "log"}
    run = {
        "group": "all",
        "place": 1,
        "id": "3",
        "tuples": [{"title": "Big grid", "key": {}}],
        "verdict": "accepted",
        "passed": 1,
        "reports": [],
        "label": log,
    }
    result = Result(
        GRADING,
        1,
        GradingStatus.DONE,
        runs=(run, {**run, "place": 2, "id": "9", "dropped": True}),
        run_values=(
            ValueShown("score", Fraction(1, 3), False, True, "now", ("3",), ("tests",), ()),
            ValueShown("late", None, True, False),
            ValueShown("first_failed", None, False, False, "now", (), (), (), "WA"),
        ),
        once={"reports": {"setup_ms": 40}, "texts": {"log": log}},
        compiled=1,
        facts={"seconds_late": Fraction(1800), "compiled": Fraction(1)},
    )

    answer = OrganisedResult.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer["run_values"] == [
        {
            "name": "score",
            "number": "0." + "3" * 30,
            "text": None,
            "waiting": False,
            "self_reported": True,
            "show": "now",
            "runs": ["3"],
            "values": ["tests"],
            "facts": [],
        },
        {
            "name": "late",
            "number": None,
            "text": None,
            "waiting": True,
            "self_reported": False,
            "show": None,
            "runs": None,
            "values": None,
            "facts": None,
        },
        {
            "name": "first_failed",
            "number": None,
            "text": "WA",
            "waiting": False,
            "self_reported": False,
            "show": "now",
            "runs": [],
            "values": [],
            "facts": [],
        },
    ]
    assert answer["runs"][0]["label"] == log
    assert answer["runs"][0]["tuples"] == [{"title": "Big grid", "key": {}}]
    assert [each["dropped"] for each in answer["runs"]] == [False, True]
    assert answer["once"] == {"reports": {"setup_ms": "40"}, "texts": {"log": log}}
    assert (answer["compiled"], answer["facts"]) == (1, {"seconds_late": "1800", "compiled": "1"})


def test_numbers_are_served_as_exact_decimals_and_text_stays_text() -> None:
    run = {
        "group": "all",
        "place": 1,
        "tuples": [{"title": None, "key": {}}],
        "verdict": "accepted",
        "passed": 1,
        "reports": [
            {"title": "loss", "number": Decimal("0.1000000000000000000000000001")},
            {"title": "total", "number": 10**20},
        ],
    }
    result = Result(
        GRADING,
        1,
        SubmissionState.GRADED,
        runs=(run,),
        run_values=(ValueShown("label", None, False, False, text="12.5"),),
    )

    served = json.loads(ResultAnswer.model_validate(result, from_attributes=True).model_dump_json())

    assert served["runs"][0]["reports"] == [
        {"title": "loss", "unit": None, "number": "0.1000000000000000000000000001"},
        {"title": "total", "unit": None, "number": "100000000000000000000"},
    ]
    [label] = served["run_values"]
    assert (label["number"], label["text"]) == (None, "12.5")


def test_a_submissions_inputs_are_read_leniently() -> None:
    record = SubmittedFilesRecord(
        TaskId("acme/spring/sum"),
        3,
        {
            "code": {"files": ["files/code/main.py", 7]},
            "language": {"value": "python"},
            "alpha": {"value": 0.5},
            "ratio": {"value": Decimal("0.123456789012345678901234567891")},
            "odd": ["not", "an", "object"],
            "weights": {"files": "files/weights/model.bin", "value": {"nested": True}},
            "route": {"parts": {"1": {"files": ["files/route/1/a.txt", 3]}, "3": {"value": 7}}},
            "tour": {"parts": {"1": "not an object", "2": {"value": True}}},
            "broken": {"parts": ["files/broken/1/a.txt"]},
        },
    )

    answer = SubmittedFiles.model_validate(record, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "number": 3,
        "inputs": {
            "code": {"files": ["files/code/main.py"], "value": None, "parts": None},
            "language": {"files": [], "value": "python", "parts": None},
            "alpha": {"files": [], "value": "0.5", "parts": None},
            "ratio": {"files": [], "value": "0.123456789012345678901234567891", "parts": None},
            "odd": {"files": [], "value": None, "parts": None},
            "weights": {"files": [], "value": None, "parts": None},
            "route": {
                "files": [],
                "value": None,
                "parts": {
                    "1": {"files": ["files/route/1/a.txt"], "value": None},
                    "3": {"files": [], "value": "7"},
                },
            },
            "tour": {"files": [], "value": None, "parts": {"2": {"files": [], "value": True}}},
            "broken": {"files": [], "value": None, "parts": None},
        },
    }


@pytest.mark.parametrize(
    ("path", "header"),
    [
        ("files/code/main.py", 'attachment; filename="main.py"'),
        ("files/notes/my notes.txt", "attachment; filename*=UTF-8''my%20notes.txt"),
        ('files/notes/"x";.txt', "attachment; filename*=UTF-8''%22x%22%3B.txt"),
        ("files/notes/résumé.pdf", "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf"),
    ],
    ids=["plain", "a space", "quotes", "not ascii"],
)
def test_a_download_is_named_after_the_file(path: str, header: str) -> None:
    assert attachment(path) == header
