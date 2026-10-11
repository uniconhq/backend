"""A contestant input as its form is served: a number input's default and
bounds as the exact digits the task gives, every other default as it is.
"""

from decimal import Decimal
from typing import Any

import pytest
from forge.api.contest_home import Field, Type
from pydantic import TypeAdapter

from unicon.schemas.contest_home import InputField

DIGITS = "0.123456789012345678901234567891"


def _field(**given: Any) -> InputField:
    return InputField.model_validate(
        {
            "id": "ratio",
            "type": "number",
            "label": "ratio",
            "options": None,
            "per_test": False,
            "default": None,
            "min": None,
            "max": None,
            "max_size": 1024,
            **given,
        }
    )


@pytest.mark.parametrize("default", [Decimal("2.5"), 3])
def test_a_number_inputs_default_from_forges_own_field_is_served_as_its_digits(
    default: Decimal | int,
) -> None:
    """A route answers forge's `Field`, which FastAPI reads by its attributes."""
    given = Field(id="ratio", type=Type.NUMBER, label="ratio", default=default)

    field = TypeAdapter(InputField).validate_python(given, from_attributes=True)

    assert field.default == str(default)


def test_a_number_inputs_default_and_bounds_are_served_to_the_digit() -> None:
    field = _field(default=Decimal(DIGITS), min=Decimal("0"), max=Decimal("1.5"))

    assert field.model_dump(mode="json")["default"] == DIGITS
    assert (field.min, field.max) == ("0", "1.5")


@pytest.mark.parametrize(
    ("kind", "default"), [("text", "12"), ("boolean", True), ("enum", "python")]
)
def test_any_other_inputs_default_is_served_as_it_is(kind: str, default: object) -> None:
    assert _field(type=kind, default=default).model_dump(mode="json")["default"] == default
