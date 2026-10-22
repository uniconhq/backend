"""A run task's grading as an organiser reads it: its pipeline, the early
attempt a late one follows, and its result, version 6, each run with its
verdict and its numbers exactly as the steps wrote them.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from forge.api.gradings import GradingRecord, GradingStatus
from forge.api.types import PublicationId, TaskId
from pydantic import TypeAdapter

from unicon.schemas.gradings import Grading, RunsResult

AT = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
LOG = {"output": str(uuid.UUID(int=1)), "name": "log"}
RESULT = {
    "schema_version": 6,
    "runs": [
        {
            "id": "r3",
            "key": {"input": "tests/3.in", "answer": "tests/3.ans"},
            "verdict": "accepted",
            "passed": 1,
            "reports": {"score": 1, "time_ms": Decimal("12.5")},
            "texts": {},
            "message": {"output": str(uuid.UUID(int=2)), "name": "message"},
        },
        {
            "id": "r4",
            "key": {"input": "tests/4.in", "answer": "tests/4.ans"},
            "verdict": "wrong_answer",
            "passed": 0,
            "reports": {},
            "texts": {},
        },
    ],
    "once": {"reports": {}, "texts": {"log": LOG}},
    "staff": [{"step": "compare", "run": "r4", "staff_message": LOG}],
    "error": None,
    "run_log": None,
}

RECORD: dict[str, Any] = {
    "id": uuid.UUID(int=8),
    "task": TaskId("acme/spring/islands"),
    "workspace": "acme/spring/@u8",
    "submission_number": 1,
    "submitted_at": AT,
    "publication": PublicationId("acme/spring/islands#1"),
    "attempt": 1,
    "latest": True,
    "submitted_by": 8,
    "status": GradingStatus.DONE,
    "error": None,
    "log": False,
    "progress": None,
    "queued_at": AT,
    "dispatched_at": AT,
    "started_at": AT,
    "finished_at": AT,
    "deadline_at": AT,
}


def test_a_late_attempt_is_read_with_its_runs_and_the_early_attempt_it_follows() -> None:
    early = uuid.UUID(int=7)
    given = GradingRecord(**RECORD, result=RESULT, pipeline="late", early=early)

    read = TypeAdapter(Grading).validate_python(given, from_attributes=True)

    assert (read.pipeline, read.early) == ("late", early)
    assert isinstance(read.result, RunsResult)
    shown = read.model_dump(mode="json")["result"]
    assert [(run["id"], run["verdict"]) for run in shown["runs"]] == [
        ("r3", "accepted"),
        ("r4", "wrong_answer"),
    ]
    assert shown["runs"][0]["reports"] == {"score": "1", "time_ms": "12.5"}
    assert shown["once"]["texts"]["log"] == LOG
    assert "run_log" not in shown
