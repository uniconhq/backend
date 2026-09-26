"""Every line the backend logs is one JSON record, secrets come out masked, and a
request produces exactly one record with nothing from the request in it.
"""

import json
import logging
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from unicon.log import MASK, JsonFormatter, get_logger
from unicon.main import create_app
from unicon.settings import Settings

FORMATTER = JsonFormatter()


def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [
        json.loads(FORMATTER.format(record))
        for record in caplog.records
        if record.getMessage() == event
    ]


def test_a_record_is_one_json_object_with_named_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    get_logger("unicon.test").info("login.refused", code="forge_unreachable", attempt=2)

    (record,) = _records(caplog, "login.refused")
    assert record["level"] == "INFO"
    assert record["logger"] == "unicon.test"
    assert record["code"] == "forge_unreachable"
    assert record["attempt"] == 2
    assert record["time"].endswith("+00:00")


def test_a_secret_logged_on_purpose_comes_out_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    get_logger("unicon.test").warning(
        "token.seen", token=SecretStr("gho_live_token"), nested={"key": SecretStr("k")}
    )

    (record,) = _records(caplog, "token.seen")
    line = json.dumps(record)
    assert "gho_live_token" not in line
    assert record["token"] == MASK
    assert record["nested"]["key"] == MASK


def test_an_exception_record_carries_the_traceback(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("unicon.test").exception("job.failed", job="nightly")

    (record,) = _records(caplog, "job.failed")
    assert record["job"] == "nightly"
    assert "ValueError: boom" in record["exception"]


async def test_a_request_produces_exactly_one_record_without_the_cookie(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    app = create_app(settings)
    transport = ASGITransport(app=app)
    cookies = {"unicon_session": "cookie-value-nobody-may-log"}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as client:
        response = await client.get("/healthz?code=login-code&state=login-state")
    assert response.status_code == 200

    (record,) = _records(caplog, "http.request")
    assert record["method"] == "GET"
    assert record["path"] == "/healthz"
    assert record["status"] == 200
    assert record["duration_ms"] >= 0
    line = json.dumps(record)
    assert "cookie-value-nobody-may-log" not in line
    assert "login-code" not in line
    assert "login-state" not in line
