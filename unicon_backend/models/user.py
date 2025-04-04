from typing import TYPE_CHECKING

import sqlalchemy.orm as sa_orm
from sqlmodel import Field, Relationship

from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.models.links import GroupMember, UserRole

if TYPE_CHECKING:
    from unicon_backend.models.organisation import Organisation, OrganisationMember, Role
    from unicon_backend.models.problem import SubmissionORM, TaskAttemptORM


class UserORM(CustomSQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True)
    username: str = Field(unique=True, index=True)
    password: str

    roles: sa_orm.Mapped[list["Role"]] = Relationship(back_populates="users", link_model=UserRole)
    owned_organisations: sa_orm.Mapped[list["Organisation"]] = Relationship(back_populates="owner")
    organisations: sa_orm.Mapped[list["OrganisationMember"]] = Relationship(back_populates="user")

    submissions: sa_orm.Mapped[list["SubmissionORM"]] = Relationship(back_populates="user")

    group_members: sa_orm.Mapped[list["GroupMember"]] = Relationship(back_populates="user")
    task_attempts: sa_orm.Mapped[list["TaskAttemptORM"]] = Relationship(back_populates="user")
