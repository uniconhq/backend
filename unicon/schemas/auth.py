"""What the sign-in routes answer with, where they answer with a body."""

from pydantic import BaseModel


class RegisterUrl(BaseModel):
    url: str | None
