"""Where a login may land: a path on this site, or the front page."""

import pytest

from unicon.domain.next_path import MAX_LENGTH, safe_next

ACCEPTED = ["/", "/contests/4", "/tasks/1?tab=files", "/a/b/c"]

REFUSED = [
    None,
    "",
    "/" + "a" * MAX_LENGTH,
    "//evil.test/steal",
    "/\\evil.test",
    "https://evil.test",
    "evil.test",
    "javascript:alert(1)",
    "/ok\nSet-Cookie: x=1",
]


@pytest.mark.parametrize("path", ACCEPTED)
def test_a_path_on_this_site_is_kept(path: str) -> None:
    assert safe_next(path) == path


@pytest.mark.parametrize("candidate", REFUSED)
def test_anything_that_could_leave_the_site_lands_on_the_front_page(
    candidate: str | None,
) -> None:
    assert safe_next(candidate) == "/"
