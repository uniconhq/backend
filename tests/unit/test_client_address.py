"""What a proxy header turns into."""

from ipaddress import ip_address

import pytest

from unicon.domain.client_address import client_address

NOTHING = [None, "", "   ", "junk", "unknown", "1.2.3.4, 5.6.7.8", "999.1.1.1", "<script>"]


@pytest.mark.parametrize("value", ["10.0.0.4", "2001:db8::1", " 10.0.0.4 "])
def test_an_address_is_kept(value: str) -> None:
    assert client_address(value) == ip_address(value.strip())


@pytest.mark.parametrize("value", NOTHING)
def test_anything_else_is_nothing(value: str | None) -> None:
    assert client_address(value) is None
