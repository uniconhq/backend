"""Primary keys for Unicon-owned rows. A UUID v7 begins with a millisecond
timestamp, so keys sort by creation time and insert at the right-hand edge of a
btree instead of scattering.
"""

import uuid


def new_id() -> uuid.UUID:
    """A fresh UUID v7. Ids from one process sort in the order they were made."""
    return uuid.uuid7()
