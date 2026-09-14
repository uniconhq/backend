"""Primary keys are UUID v7, and they sort in the order they were made."""

import uuid

from unicon.domain.identifiers import new_id


def test_ids_are_uuid_version_7() -> None:
    generated = new_id()

    assert isinstance(generated, uuid.UUID)
    assert generated.version == 7


def test_ids_from_one_process_increase() -> None:
    ids = [str(new_id()) for _ in range(10_000)]

    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
