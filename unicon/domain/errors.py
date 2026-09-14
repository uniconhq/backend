"""Errors the client is allowed to see. Each carries a stable `code` the frontend
switches on, so a code is renamed as rarely as a field name. `api/errors.py`
turns these into problem documents.
"""

from typing import Any


class UniconError(Exception):
    """Base class. Subclasses set `code` and `status`; `extra` becomes extra
    members of the problem document, so it must hold JSON-serialisable values
    only.
    """

    code = "internal_error"
    status = 500
    clears_session = False

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra: dict[str, Any] = extra


class NotFoundError(UniconError):
    code = "not_found"
    status = 404


class Unauthenticated(UniconError):
    """No session cookie, or one that names no row."""

    code = "unauthenticated"
    status = 401
    clears_session = True


class SessionExpired(UniconError):
    """The row is there but past its hard or idle expiry, or revoked."""

    code = "session_expired"
    status = 401
    clears_session = True


class ForgeReauthRequired(UniconError):
    """The Forgejo refresh token no longer works, so the session cannot act in
    Forgejo even though it has not expired.
    """

    code = "forge_reauth"
    status = 401
    clears_session = True


class ReauthRequired(UniconError):
    """The action needs a login from the last few minutes."""

    code = "reauth_required"
    status = 403


class OriginMismatch(UniconError):
    code = "origin_mismatch"
    status = 403


class ForgeUnavailable(UniconError):
    code = "forge_unreachable"
    status = 503


class ForgeRejectedChange(UniconError):
    """Forgejo refused the change itself rather than failing to answer. Its
    message names the reason, such as a user who still owns a repository, so it
    is passed through.
    """

    code = "forge_rejected"
    status = 409


class LastAdmin(UniconError):
    """Refused: the person is the only admin of something. `scopes` lists what."""

    code = "last_admin"
    status = 409


class ForgeMisconfigured(UniconError):
    """Forgejo refused Unicon itself rather than the person: a wrong client id or
    secret, or a redirect URI that does not match. A 502 and not a sign-out,
    since logging in again would hit the same wall.
    """

    code = "forge_misconfigured"
    status = 502


class LoginStateInvalid(UniconError):
    """The login cookie was missing, expired, or its state did not match."""

    code = "login_state_invalid"
    status = 400


class LoginDenied(UniconError):
    """The person said no on Forgejo's consent page."""

    code = "login_denied"
    status = 400
