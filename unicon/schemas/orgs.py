"""What the org routes take. Forge checks the org's name; these models say
what shape the body has, and hold an org's description to the 255
characters the forge takes.
"""

from pydantic import BaseModel, Field

DESCRIPTION_MAX = 255


class CreateOrg(BaseModel):
    name: str
    description: str = Field("", max_length=DESCRIPTION_MAX)


class UpdateOrg(BaseModel):
    """The org's description, and its display name when given."""

    description: str = Field(max_length=DESCRIPTION_MAX)
    display_name: str | None = None
