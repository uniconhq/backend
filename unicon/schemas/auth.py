"""What the login endpoints answer with, where they answer at all: the others are
redirects and a 204.
"""

from pydantic import BaseModel


class RegisterUrl(BaseModel):
    url: str | None
