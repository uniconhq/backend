"""A machine's request reaches forge as it was sent: the target with its
path undecoded and its query, and every header by its name in lower case,
a repeated one's values joined as HTTP reads them.
"""

from fastapi import Request

from unicon.api import raw


def _request(raw_path: bytes, query: bytes, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": raw_path.decode().replace("%2F", "/"),
            "raw_path": raw_path,
            "query_string": query,
            "headers": headers,
        }
    )


def test_the_target_is_the_path_and_query_as_sent() -> None:
    request = _request(b"/api/v1/ci/config%2Fx", b"a=1&b=%20", [])

    assert raw.target(request) == "/api/v1/ci/config%2Fx?a=1&b=%20"


def test_a_target_with_no_query_has_no_question_mark() -> None:
    assert raw.target(_request(b"/api/v1/ci/config", b"", [])) == "/api/v1/ci/config"


def test_every_header_is_kept_and_a_repeated_one_joined() -> None:
    request = _request(
        b"/api/v1/ci/config",
        b"",
        [
            (b"signature-input", b'woodpecker-ci-extensions=("@request-target")'),
            (b"x-extra", b"one"),
            (b"x-extra", b"two"),
        ],
    )

    assert raw.headers(request) == {
        "signature-input": 'woodpecker-ci-extensions=("@request-target")',
        "x-extra": "one, two",
    }
