"""Every `UNICON_*` setting, read once at start-up. A bad value stops the process
with the variable named, rather than failing later on a request.
"""

import base64
import binascii
import logging
import sys
from datetime import timedelta
from typing import Any, Self

from pydantic import HttpUrl, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KEY_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNICON_", extra="ignore")

    public_url: HttpUrl

    database_url: PostgresDsn

    forge_public_url: HttpUrl

    forge_internal_url: HttpUrl

    forge_admin_token: SecretStr

    forge_oauth_client_id: str
    forge_oauth_client_secret: SecretStr

    forge_registration_open: bool = False

    woodpecker_url: HttpUrl
    woodpecker_token: SecretStr

    s3_endpoint: HttpUrl
    s3_region: str
    s3_access_key: SecretStr
    s3_secret_key: SecretStr

    session_signing_key: SecretStr

    token_encryption_key: SecretStr

    cookie_secure: bool = False

    log_level: str = "INFO"

    session_hard_ttl: timedelta = timedelta(days=30)

    session_idle_ttl: timedelta = timedelta(days=14)
    login_state_ttl: timedelta = timedelta(minutes=10)
    reauth_window: timedelta = timedelta(minutes=5)

    @field_validator("log_level")
    @classmethod
    def _a_real_level(cls, value: str) -> str:
        name = value.strip().upper()
        if name not in logging.getLevelNamesMapping():
            raise ValueError(f"is not a logging level: {value}")
        return name

    @model_validator(mode="after")
    def _idle_within_hard(self) -> Self:
        """An idle window longer than the hard lifetime is one that never closes."""
        if self.session_idle_ttl > self.session_hard_ttl:
            raise ValueError("UNICON_SESSION_IDLE_TTL is longer than UNICON_SESSION_HARD_TTL")
        return self

    @model_validator(mode="before")
    @classmethod
    def _default_internal_url_to_public(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("forge_internal_url"):
            data["forge_internal_url"] = data.get("forge_public_url")
        return data

    @field_validator("*")
    @classmethod
    def _no_blank_values(cls, value: Any) -> Any:
        """An empty variable is one somebody meant to fill in."""
        secret = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(secret, str) and not secret.strip():
            raise ValueError("is empty")
        return value

    @field_validator(
        "session_hard_ttl",
        "session_idle_ttl",
        "login_state_ttl",
        "reauth_window",
        mode="before",
    )
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        """Lifetimes are given in seconds. Pydantic would otherwise read a bare
        string as an ISO 8601 duration.
        """
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return value

    @field_validator("session_signing_key", "token_encryption_key")
    @classmethod
    def _must_be_32_bytes_base64url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        try:
            decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("not base64url") from exc
        if len(decoded) != KEY_BYTES:
            raise ValueError(f"decodes to {len(decoded)} bytes, expected {KEY_BYTES}")
        return value

    @property
    def session_signing_key_bytes(self) -> bytes:
        return _decode_key(self.session_signing_key)

    @property
    def token_encryption_key_bytes(self) -> bytes:
        return _decode_key(self.token_encryption_key)

    @classmethod
    def for_tests(cls, **overrides: Any) -> Self:
        """A complete settings object, so a test never sees the developer's own
        environment.
        """
        key = base64.urlsafe_b64encode(b"\x00" * KEY_BYTES).decode().rstrip("=")
        values: dict[str, Any] = {
            "public_url": "http://localhost:8080",
            "database_url": "postgresql+psycopg://unicon:unicon@localhost:5432/unicon",
            "forge_public_url": "http://localhost:3300",
            "forge_internal_url": "http://forgejo:3000",
            "forge_admin_token": "test-admin-token",
            "forge_oauth_client_id": "test-client-id",
            "forge_oauth_client_secret": "test-client-secret",
            "woodpecker_url": "http://woodpecker-server:8000",
            "woodpecker_token": "test-woodpecker-token",
            "s3_endpoint": "http://garage:3900",
            "s3_region": "garage",
            "s3_access_key": "test-access-key",
            "s3_secret_key": "test-secret-key",
            "session_signing_key": key,
            "token_encryption_key": key,
            "cookie_secure": False,
            "forge_registration_open": True,
            "log_level": "INFO",
            "session_hard_ttl": timedelta(days=30),
            "session_idle_ttl": timedelta(days=14),
            "login_state_ttl": timedelta(minutes=10),
            "reauth_window": timedelta(minutes=5),
        }
        values.update(overrides)
        return cls(**values)


class DatabaseSettings(BaseSettings):
    """What `unicon migrate` needs, which is the database URL and nothing else.
    Demanding the OAuth secrets to create a table would be noise.
    """

    model_config = SettingsConfigDict(env_prefix="UNICON_", extra="ignore")

    database_url: PostgresDsn


def _decode_key(secret: SecretStr) -> bytes:
    """`Settings` has already validated that this decodes to 32 bytes."""
    raw = secret.get_secret_value()
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def load_settings() -> Settings:
    """Read the environment, or exit with the offending variables listed and no
    traceback.
    """
    return _loaded(Settings)


def load_database_settings() -> DatabaseSettings:
    """The same treatment for the one variable `unicon migrate` reads."""
    return _loaded(DatabaseSettings)


def _loaded[T: BaseSettings](settings_class: type[T]) -> T:
    try:
        return settings_class()
    except ValueError as exc:
        for line in _configuration_problems(exc):
            print(line, file=sys.stderr)
        raise SystemExit(2) from None


def _configuration_problems(exc: ValueError) -> list[str]:
    errors = getattr(exc, "errors", None)
    if errors is None:
        return [f"configuration error: {exc}"]
    lines = ["configuration error:"]
    for error in errors():
        if not error["loc"]:
            lines.append(f"  {error['msg']}")
            continue
        location = str(error["loc"][0])
        name = location if location.startswith("UNICON_") else f"UNICON_{location.upper()}"
        lines.append(f"  {name}: {error['msg']}")
    return lines
