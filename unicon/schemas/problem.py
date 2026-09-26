"""The body of every error response: an RFC 9457 problem document. `code` is what
clients switch on and is stable; `title` and `detail` are for people and may be
reworded.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

PROBLEM_CONTENT_TYPE = "application/problem+json"


class Problem(BaseModel):
    """Extra members are allowed: `sole_admin` carries `scopes`, for instance."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str

    @classmethod
    def of(cls, *, code: str, status: int, title: str, detail: str, **extra: Any) -> Problem:
        return cls(code=code, status=status, title=title, detail=detail, **extra)
