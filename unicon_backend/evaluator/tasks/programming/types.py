"""
Unicon's type system.
List of types, along with future mapping to language-specific types should be in this file.
"""

from enum import Enum


class UniconType(str, Enum):
    Text = "text"
    Number = "number"
    Boolean = "boolean"
    Null = "null"

    # Can be considered as a string for inputs to other nodes.
    UniconFile = "UniconFile"

    # TODO: needs mapping to unicon types.
    PythonObject = "PythonObject"

    # Can be input to anything. Can accept anything.
    Unknown = "unknown"
