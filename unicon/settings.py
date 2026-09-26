"""The shell's settings: the package's, plus what only the HTTP layer reads,
the session cookie's signing key and whether the cookie is marked secure.
"""

from typing import Any, Self

from forge.settings import TEST_KEY, Settings, decode_key, load, require_key
from pydantic import SecretStr, field_validator


class ShellSettings(Settings):
    session_signing_key: SecretStr
    cookie_secure: bool = False

    @field_validator("session_signing_key")
    @classmethod
    def _thirty_two_bytes(cls, value: SecretStr) -> SecretStr:
        return require_key(value)

    @property
    def session_signing_key_bytes(self) -> bytes:
        return decode_key(self.session_signing_key)

    @classmethod
    def for_tests(cls, **overrides: Any) -> Self:
        return super().for_tests(**{"session_signing_key": TEST_KEY, **overrides})


def load_shell_settings() -> ShellSettings:
    return load(ShellSettings)
