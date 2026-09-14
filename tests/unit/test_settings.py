"""Configuration is checked at startup, and a mistake names the variable."""

from datetime import timedelta

import pytest

from unicon.settings import Settings, load_settings

COMPLETE_ENVIRONMENT = {
    "UNICON_PUBLIC_URL": "http://localhost:8080",
    "UNICON_DATABASE_URL": "postgresql+psycopg://unicon:pw@postgres:5432/unicon",
    "UNICON_FORGE_PUBLIC_URL": "http://localhost:3300",
    "UNICON_FORGE_ADMIN_TOKEN": "admin-token",
    "UNICON_FORGE_OAUTH_CLIENT_ID": "client-id",
    "UNICON_FORGE_OAUTH_CLIENT_SECRET": "client-secret",
    "UNICON_WOODPECKER_URL": "http://woodpecker-server:8000",
    "UNICON_WOODPECKER_TOKEN": "woodpecker-token",
    "UNICON_S3_ENDPOINT": "http://garage:3900",
    "UNICON_S3_REGION": "garage",
    "UNICON_S3_ACCESS_KEY": "access",
    "UNICON_S3_SECRET_KEY": "secret",
    "UNICON_SESSION_SIGNING_KEY": "dW5pY29uIHRlc3Qgc2Vzc2lvbiBzaWduaW5nIGtleS4",
    "UNICON_TOKEN_ENCRYPTION_KEY": "dW5pY29uIHRlc3QgdG9rZW4gZW5jcnlwdGlvbiBrZXk",
}


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    strays = [
        "UNICON_FORGE_INTERNAL_URL",
        "UNICON_FORGE_REGISTRATION_OPEN",
        "UNICON_LOG_LEVEL",
        "UNICON_SESSION_HARD_TTL",
        "UNICON_SESSION_IDLE_TTL",
    ]
    for name in [*COMPLETE_ENVIRONMENT, *strays]:
        monkeypatch.delenv(name, raising=False)
    for name, value in COMPLETE_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    return dict(COMPLETE_ENVIRONMENT)


def test_a_complete_environment_loads(environment: dict[str, str]) -> None:
    settings = load_settings()

    assert str(settings.public_url) == "http://localhost:8080/"
    assert settings.forge_admin_token.get_secret_value() == "admin-token"


def test_a_missing_variable_stops_the_process_and_names_it(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("UNICON_FORGE_ADMIN_TOKEN")

    with pytest.raises(SystemExit) as exit_info:
        load_settings()

    assert exit_info.value.code == 2
    message = capsys.readouterr().err
    assert "UNICON_FORGE_ADMIN_TOKEN" in message
    assert "Traceback" not in message


def test_an_empty_variable_is_refused(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("UNICON_FORGE_ADMIN_TOKEN", "")

    with pytest.raises(SystemExit):
        load_settings()

    assert "UNICON_FORGE_ADMIN_TOKEN" in capsys.readouterr().err


def test_a_key_of_the_wrong_length_is_refused(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("UNICON_TOKEN_ENCRYPTION_KEY", "dG9vLXNob3J0")

    with pytest.raises(SystemExit):
        load_settings()

    assert "UNICON_TOKEN_ENCRYPTION_KEY" in capsys.readouterr().err


def test_a_key_that_is_not_base64url_is_refused(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("UNICON_SESSION_SIGNING_KEY", "not base64 at all !!")

    with pytest.raises(SystemExit):
        load_settings()

    assert "UNICON_SESSION_SIGNING_KEY" in capsys.readouterr().err


def test_the_internal_forge_url_falls_back_to_the_public_one(
    environment: dict[str, str],
) -> None:
    settings = load_settings()

    assert str(settings.forge_internal_url) == "http://localhost:3300/"


def test_the_internal_forge_url_is_used_when_given(
    environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNICON_FORGE_INTERNAL_URL", "http://forgejo:3000")

    settings = load_settings()

    assert str(settings.forge_internal_url) == "http://forgejo:3000/"
    assert str(settings.forge_public_url) == "http://localhost:3300/"


def test_lifetimes_are_read_as_seconds(
    environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNICON_SESSION_HARD_TTL", "604800")
    monkeypatch.setenv("UNICON_SESSION_IDLE_TTL", "86400")

    settings = load_settings()

    assert settings.session_hard_ttl == timedelta(days=7)
    assert settings.session_idle_ttl == timedelta(days=1)
    assert settings.reauth_window == timedelta(minutes=5)


def test_an_idle_window_longer_than_the_session_is_refused(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("UNICON_SESSION_HARD_TTL", "3600")
    monkeypatch.setenv("UNICON_SESSION_IDLE_TTL", "7200")

    with pytest.raises(SystemExit):
        load_settings()

    message = capsys.readouterr().err
    assert "UNICON_SESSION_IDLE_TTL" in message
    assert "UNICON_SESSION_HARD_TTL" in message


def test_sign_ups_are_closed_unless_the_instance_says_otherwise(
    environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert load_settings().forge_registration_open is False

    monkeypatch.setenv("UNICON_FORGE_REGISTRATION_OPEN", "true")

    assert load_settings().forge_registration_open is True


def test_the_log_level_has_to_be_one(
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert load_settings().log_level == "INFO"

    monkeypatch.setenv("UNICON_LOG_LEVEL", "chatty")

    with pytest.raises(SystemExit):
        load_settings()

    assert "UNICON_LOG_LEVEL" in capsys.readouterr().err


def test_the_session_lifetime_does_not_outlive_the_default_forge_refresh_token() -> None:
    assert Settings.for_tests().session_hard_ttl == timedelta(days=30)
