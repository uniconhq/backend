"""What the two probes answer with."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]


class NotReady(BaseModel):
    """Deliberately not a problem document: an orchestrator reads this and wants
    the reason in a fixed place.
    """

    status: Literal["not_ready"]
    postgres: str
