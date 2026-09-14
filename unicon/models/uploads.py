"""Files a browser uploaded to Garage that are not yet part of anything. Between
the presigned PUT and the commit that makes it a submission an upload has no
owner; the expiry lets a sweeper delete what was never used.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from unicon.db.base import Base
from unicon.domain.identifiers import new_id
from unicon.models.timestamps import TimestampsMixin


class Upload(Base, TimestampsMixin):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str]
    contest_repo_id: Mapped[int | None] = mapped_column(BigInteger)
    task_repo_id: Mapped[int | None] = mapped_column(BigInteger)
    input_id: Mapped[str | None]

    object_key: Mapped[str] = mapped_column(unique=True)
    filename: Mapped[str]
    content_type: Mapped[str | None]
    declared_size: Mapped[int] = mapped_column(BigInteger)
    actual_size: Mapped[int | None] = mapped_column(BigInteger)

    sha256: Mapped[bytes | None]
    status: Mapped[str]
    multipart_upload_id: Mapped[str | None]
    consumed_by: Mapped[str | None]

    expires_at: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("purpose in ('submission', 'asset')", name="purpose"),
        CheckConstraint(
            "status in ('presigned', 'uploaded', 'verified', 'consumed', 'rejected', 'expired')",
            name="status",
        ),
        Index("ix_uploads_user_id_status", "user_id", "status"),
        Index("ix_uploads_expires_at", "expires_at"),
    )
