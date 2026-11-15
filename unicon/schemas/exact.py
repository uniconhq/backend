"""Numbers as the API serves them: exactly, as a string of plain decimal
digits, so a score, a key or a reported value reads back as the forge holds
it, which a JSON number read into a float would not. A number that is not a
decimal, a third say, is written to 30 significant digits.
"""

import math
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Any

from forge.api.leaderboards import written
from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer

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


def _decimals(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, dict):
        return {key: _decimals(each) for key, each in value.items()}
    if isinstance(value, list):
        return [_decimals(each) for each in value]
    return value


def _numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _numbers(each) for key, each in value.items()}
    if isinstance(value, list | tuple):
        return [_numbers(each) for each in value]
    return value


Values = Annotated[
    dict[str, Any],
    AfterValidator(_decimals),
    PlainSerializer(_numbers, return_type=dict[str, Any], when_used="json"),
]
"""A mapping forge reads or writes as a file, such as a request: a number
that is not whole goes in as a decimal, as forge reads a file, and out as a
JSON number, so it reads back as it was saved."""
