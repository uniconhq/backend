"""The address a request came from, as far as anyone can tell. It arrives in a
proxy header nothing has validated and is only ever displayed, so junk becomes
nothing rather than failing a login.
"""

from ipaddress import IPv4Address, IPv6Address, ip_address


def client_address(value: str | None) -> IPv4Address | IPv6Address | None:
    if not value:
        return None
    try:
        return ip_address(value.strip())
    except ValueError:
        return None
