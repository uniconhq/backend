"""What the two probes answer with."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]


class NotReady(BaseModel):
    """Deliberately not a problem document: an orchestrator reads the status in
    a fixed place. What failed underneath is in the log and not here.
    """

    status: Literal["not_ready"]
