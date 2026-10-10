"""Numbers as the API serves them: exactly, as a string of plain decimal
digits, so a score, a key or a reported value reads back as the forge holds
it, which a JSON number read into a float would not. A number that is not a
decimal, a third say, is written to 30 significant digits. A run's values
come back split into its numbers and its texts, so text that looks like a
number stays text.
"""

import math
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Any

from forge.api.boards import written
from pydantic import BaseModel, BeforeValidator, Field, model_validator

EXACT_PATTERN = r"^-?[0-9]+(\.[0-9]+)?$"


def _rational(value: Any) -> Fraction | None:
    match value:
        case bool():
            return None
        case int() | Fraction():
            return Fraction(value)
        case Decimal():
            return Fraction(value) if value.is_finite() else None
        case float():
            return Fraction(repr(value)) if math.isfinite(value) else None
    return None


def exactly(value: Any) -> Any:
    """A number as its plain decimal digits; anything else as it is."""
    number = _rational(value)
    return value if number is None else written(number)


Exact = Annotated[
    str,
    BeforeValidator(exactly),
    Field(pattern=EXACT_PATTERN, examples=["82.5"]),
]
"""An exact number, as its plain decimal digits."""


class Reported(BaseModel):
    """The values a run reported, by name: its numbers, exactly, and its
    texts, each of at most 10,000 characters.
    """

    numbers: dict[str, Exact]
    texts: dict[str, str]

    @model_validator(mode="before")
    @classmethod
    def _split(cls, given: Any) -> Any:
        if not isinstance(given, dict):
            return given
        if given and all(isinstance(part, dict) for part in given.values()):
            return given
        return {
            "numbers": {
                name: value for name, value in given.items() if _rational(value) is not None
            },
            "texts": {name: value for name, value in given.items() if isinstance(value, str)},
        }
