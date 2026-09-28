"""A request produces exactly one log record, with nothing from the request
in it.
"""

import json
import logging

import pytest
from forge.testing import logged
from httpx import ASGITransport, AsyncClient

from unicon.main import create_app


async def test_a_request_produces_exactly_one_record_without_the_cookie(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    app = create_app()
    transport = ASGITransport(app=app)
    cookies = {"unicon_session": "cookie-value-nobody-may-log"}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as client:
        response = await client.get("/healthz?code=login-code&state=login-state")
    assert response.status_code == 200

    (record,) = logged(caplog, "http.request")
    assert record["method"] == "GET"
    assert record["path"] == "/healthz"
    assert record["status"] == 200
    assert record["duration_ms"] >= 0
    line = json.dumps(record)
    assert "cookie-value-nobody-may-log" not in line
    assert "login-code" not in line
    assert "login-state" not in line
