"""What a contestant is answered with is what forge gives and nothing more: a
grading carries exactly what the task's test groups let through, a group
that did not run on it marked so, a run task's runs as forge shows them
and when it reveals, its numbers as exact decimal strings,
a submission's inputs are read leniently from its `submission.json`, and a
file's download is named after the file, quoted when its name is not
plain.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from forge.api.blocks import Better
from forge.api.submissions import (
    Fold,
    GradingStatus,
    GroupShown,
    Result,
    Show,
    SubmissionState,
    ValueMeaning,
    ValueShown,
)
from forge.api.submissions import SubmittedFiles as SubmittedFilesRecord
from forge.api.types import TaskId

from unicon.api.door import attachment
from unicon.schemas.submissions import OrganisedResult, SubmittedFiles
from unicon.schemas.submissions import Result as ResultAnswer

GRADING = uuid.UUID("0192f4a4-7b7e-7000-8000-000000000001")
REVEAL = datetime(2026, 9, 26, 15, tzinfo=UTC)


def test_a_grading_being_run_carries_its_status_alone() -> None:
    result = Result(GRADING, 2, SubmissionState.GRADING, None, None, (), {})

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer == {
        "id": str(GRADING),
        "attempt": 2,
        "status": "grading",
        "stopped": None,
        "outcome": None,
        "groups": [],
        "values": {"numbers": {}, "texts": {}},
        "reason": None,
        "limit": None,
        "meanings": [],
        "runs": [],
        "reveal_at": None,
        "run_values": [],
        "once": {"reports": {}, "texts": {}},
        "compiled": None,
    }


def test_a_grading_staff_cancelled_carries_their_sentence() -> None:
    result = Result(GRADING, 1, SubmissionState.CANCELLED, None, None, (), {}, "Not counted.")

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
        SubmissionState.GRADED,
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
        "status": "graded",
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
        "values": {"numbers": {"score": "1.5"}, "texts": {"log": ""}},
        "reason": None,
        "limit": None,
        "meanings": [],
        "runs": [],
        "reveal_at": None,
        "run_values": [],
        "once": {"reports": {}, "texts": {}},
        "compiled": None,
    }


def test_a_run_tasks_grading_carries_each_run_with_exact_numbers_its_texts_and_reveal() -> None:
    run = {
        "group": "sample_tests",
        "place": 1,
        "key": {"input": "samples/1.in"},
        "verdict": "accepted",
        "passed": 1,
        "reports": {"time_ms": 12, "memory_kb": Decimal("2048")},
        # An entrant is sent where a text is, never the output holding it.
        "texts": {"log": {}},
        "message": {},
    }
    result = Result(
        GRADING, 1, SubmissionState.GRADED, None, None, (), {}, runs=(run,), reveal_at=REVEAL
    )

    answer = ResultAnswer.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer["reveal_at"] == "2026-09-26T15:00:00Z"
    assert answer["runs"] == [
        {
            "group": "sample_tests",
            "place": 1,
            "id": None,
            "dropped": False,
            "key": {"input": "samples/1.in"},
            "verdict": "accepted",
            "passed": 1,
            "reports": {"time_ms": "12", "memory_kb": "2048"},
            "texts": {"log": {"output": None, "name": None}},
            "label": None,
            "message": {"output": None, "name": None},
        }
    ]


def test_a_run_tasks_values_once_and_compiled_are_served_exactly() -> None:
    log = {"output": "0192f4a4-7b7e-7000-8000-000000000002", "name": "log"}
    run = {
        "group": "all",
        "place": 1,
        "id": "3",
        "key": {},
        "verdict": "accepted",
        "passed": 1,
        "reports": {},
        "label": log,
    }
    result = Result(
        GRADING,
        1,
        GradingStatus.DONE,
        None,
        None,
        (),
        {},
        runs=(run, {**run, "place": 2, "id": "9", "dropped": True}),
        run_values=(
            ValueShown("score", Fraction(1, 3), False, True, "now", ("3",), ("tests",), ()),
            ValueShown("late", None, True, False),
        ),
        once={"reports": {"compile_ms": 40}, "texts": {"compile_log": log}},
        compiled=1,
        facts={"seconds_late": Fraction(1800), "compiled": Fraction(1)},
    )

    answer = OrganisedResult.model_validate(result, from_attributes=True).model_dump(mode="json")

    assert answer["run_values"] == [
        {
            "name": "score",
            "number": "0." + "3" * 30,
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
            "waiting": True,
            "self_reported": False,
            "show": None,
            "runs": None,
            "values": None,
            "facts": None,
        },
    ]
    assert answer["runs"][0]["label"] == log
    assert [each["dropped"] for each in answer["runs"]] == [False, True]
    assert answer["once"] == {"reports": {"compile_ms": "40"}, "texts": {"compile_log": log}}
    assert (answer["compiled"], answer["facts"]) == (1, {"seconds_late": "1800", "compiled": "1"})


def test_numbers_are_served_as_exact_decimals_and_text_stays_text() -> None:
    row = {
        "test": "main/1",
        "outcome": "accepted",
        "values": {"loss": Decimal("0.1000000000000000000000000001"), "label": "12.5"},
    }
    result = Result(
        GRADING,
        1,
        SubmissionState.GRADED,
        None,
        "accepted",
        (
            GroupShown("main", Show.ALWAYS, "accepted", (row,), None),
            GroupShown("large", Show.AFTER_CLOSE, None, None, REVEAL),
        ),
        {"total": 10**20},
        meanings=(
            ValueMeaning("time_ms", "Run time", "ms", Fold.MAX, Better.LOWER),
            ValueMeaning("log", "Compile log"),
        ),
    )

    served = json.loads(ResultAnswer.model_validate(result, from_attributes=True).model_dump_json())

    [main, large] = served["groups"]
    [test] = main["tests"]
    assert test == {
        "test": "main/1",
        "outcome": "accepted",
        "values": {
            "numbers": {"loss": "0.1000000000000000000000000001"},
            "texts": {"label": "12.5"},
        },
    }
    assert (large["outcome"], large["tests"], large["shown_at"]) == (
        None,
        None,
        "2026-09-26T15:00:00Z",
    )
    assert served["values"] == {"numbers": {"total": "100000000000000000000"}, "texts": {}}
    # Each value with the words a page names it by, in the report's order.
    assert served["meanings"] == [
        {"name": "time_ms", "title": "Run time", "unit": "ms", "fold": "max", "better": "lower"},
        {"name": "log", "title": "Compile log", "unit": None, "fold": None, "better": None},
    ]


def test_a_submissions_inputs_are_read_leniently() -> None:
    record = SubmittedFilesRecord(
        TaskId("acme/spring/sum"),
        3,
        {
            "submission": {"files": ["files/submission/main.py", 7]},
            "language": {"value": "python"},
            "alpha": {"value": 0.5},
            "ratio": {"value": Decimal("0.123456789012345678901234567891")},
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
            "alpha": {"files": [], "value": "0.5"},
            "ratio": {"files": [], "value": "0.123456789012345678901234567891"},
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
