"""A request handed to forge as it arrived, for the doors a machine calls with
no session: the forge's event push, the CI's configuration extension and a
grading run's callback. What admits such a request is a signature or a token
over its exact bytes, so the body is read raw and never parsed here, and it
is read only up to a bound, since nothing checks who sent it until it is
read. A body past the bound is `payload_too_large` before more of it is
read, whether its `Content-Length` says so or it runs past the bound with no
length or a length that is not a number.
"""

from fastapi import Request
from forge.api.errors import UniconError


class PayloadTooLarge(UniconError):
    code = "payload_too_large"


async def body(request: Request, limit: int, what: str) -> bytes:
    """The raw body, at most `limit` bytes. `what` names the body in the
    refusal, as in "An event's body".
    """
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit, what)
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise _too_large(limit, what)
    return bytes(received)


def target(request: Request) -> str:
    """The request's target as it was sent: the path undecoded and the query,
    which is what a signature over `@request-target` covers.
    """
    path: bytes = request.scope.get("raw_path") or request.scope["path"].encode()
    query: bytes = request.scope.get("query_string", b"")
    sent = path + b"?" + query if query else path
    return sent.decode("latin-1")


def headers(request: Request) -> dict[str, str]:
    """Every header by its name in lower case, a repeated one's values joined
    with a comma as HTTP reads them.
    """
    joined: dict[str, str] = {}
    for name, value in request.headers.items():
        joined[name] = f"{joined[name]}, {value}" if name in joined else value
    return joined


def _too_large(limit: int, what: str) -> PayloadTooLarge:
    return PayloadTooLarge(f"{what} is at most {limit} bytes.")
