"""What can go wrong when Unicon calls Forgejo. The distinction that matters to
callers: Forgejo did not answer, or Forgejo answered no.
"""


class ForgeError(Exception):
    """Base class. Letting one out of a service gives a 500, which is correct: it
    means nobody thought about that path.
    """


class ForgeUnreachable(ForgeError):
    """No answer: refused, timed out, or a gateway error. A 5xx counts here, since
    a broken Forgejo and an absent one are the same to a caller.
    """


class ForgeRejected(ForgeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Forgejo answered {status}: {body[:200]}")
        self.status = status
        self.body = body


class ForgeTokenExpired(ForgeError):
    """A refresh token Forgejo no longer accepts: expired, used twice, or revoked."""
