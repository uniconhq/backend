"""What the org routes take and answer with. Forge checks the org's name;
these models say what shape the body has, and hold an org's description to
the 255 characters the forge takes.
"""

from datetime import datetime
from typing import Literal

from forge.api.orgs import Record
from pydantic import BaseModel, Field

DESCRIPTION_MAX = 255


class CreateOrg(BaseModel):
    name: str
    description: str = Field("", max_length=DESCRIPTION_MAX)


class UpdateOrg(BaseModel):
    """The org's description, and its display name when given."""

    description: str = Field(max_length=DESCRIPTION_MAX)
    display_name: str | None = None


class Provisioning(BaseModel):
    """How far making something has got. `steps` are the steps of its kind
    in the order they run, and `last_step` is the last one that completed.
    A failed record names the step it stopped at in `failed_step`, which is
    none when the work failed outside any step, and says when it is tried
    again, from where it stopped, in `retry_at`; both are none unless the
    status is `failed`. `error` is the reason the last try failed, and
    `attempts` counts the tries.
    """

    kind: Literal["org", "contest", "task"]
    target: str
    status: Literal["pending", "running", "ready", "failed"]
    steps: list[str]
    last_step: str | None
    failed_step: str | None
    error: str | None
    retry_at: datetime | None
    attempts: int
    ready_at: datetime | None

    @classmethod
    def of(cls, record: Record) -> Provisioning:
        return cls(
            kind=record.kind,
            target=record.target_id,
            status=record.status,
            steps=list(record.steps),
            last_step=record.last_step,
            failed_step=record.failed_step,
            error=record.error,
            retry_at=record.retry_at,
            attempts=record.attempts,
            ready_at=record.ready_at,
        )
