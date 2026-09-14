"""Unicon's own login sessions, and the Forgejo tokens they carry. There is no
users table: `user_id` is Forgejo's numeric id and the username is only a
cache, since Forgejo sends no event on a rename. The tokens are encrypted at
rest.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, Index
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[bytes] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str]

    forge_access_token: Mapped[bytes]
    forge_refresh_token: Mapped[bytes]
    forge_token_expires_at: Mapped[datetime]

    created_at: Mapped[datetime]

    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]

    ip: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)

    user_agent: Mapped[str | None]
    revoked_at: Mapped[datetime | None]

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )
