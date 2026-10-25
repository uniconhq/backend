"""What the hold routes answer with."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HoldRequest(BaseModel):
    """Ending the contest's hold early. Without `confirm` nothing changes,
    and the answer is `confirmation_required` with the words to show."""

    confirm: bool = False


class HoldState(BaseModel):
    """Where the contest's hold stands: its `from` and `until`, a time or
    `staff`, both null with no hold; whether it holds now; and, once staff
    ended it early, who, by user id and username, null when the forge gives
    none, and when."""

    from_: datetime | None = Field(serialization_alias="from")
    until: datetime | Literal["staff"] | None
    holding: bool
    ended_by: int | None
    ended_by_name: str | None
    ended_at: datetime | None
