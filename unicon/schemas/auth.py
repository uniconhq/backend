"""What the sign-in routes answer with, where they answer with a body."""

from pydantic import BaseModel


class RegisterUrl(BaseModel):
    url: str | None


class ForgeUrl(BaseModel):
    """Where a browser reaches the forge's own pages: sign-in and the account
    settings. No trailing slash.
    """

    url: str
