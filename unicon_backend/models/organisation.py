import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
import sqlalchemy.orm as sa_orm
from sqlmodel import Field, Relationship

from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.models.links import GroupMember, UserRole

if TYPE_CHECKING:
    from unicon_backend.models.problem import ProblemORM
    from unicon_backend.models.user import UserORM


class OrganisationBase(CustomSQLModel):
    name: str
    description: str


class Organisation(OrganisationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int | None = Field(foreign_key="user.id", nullable=False)

    projects: sa_orm.Mapped[list["Project"]] = Relationship(
        back_populates="organisation", cascade_delete=True
    )
    owner: sa_orm.Mapped["UserORM"] = Relationship(back_populates="owned_organisations")
    members: sa_orm.Mapped[list["OrganisationMember"]] = Relationship(
        back_populates="organisation", cascade_delete=True
    )
    invitation_keys: sa_orm.Mapped[list["OrganisationInvitationKey"]] = Relationship(
        back_populates="organisation", cascade_delete=True
    )

    excluded_fields_on_copy: ClassVar[list[str]] = ["members", "invitation_keys"]


class OrganisationRole(StrEnum):
    ADMIN = "admin"
    OBSERVER = "observer"


class OrganisationInvitationKey(CustomSQLModel, table=True):
    __tablename__ = "organisation_invitation_key"

    id: int | None = Field(default=None, primary_key=True)
    organisation_id: int | None = Field(foreign_key="organisation.id", nullable=False)
    role: OrganisationRole = Field(sa_column=sa.Column(pg.ENUM(OrganisationRole), nullable=False))

    key: uuid.UUID = Field(default_factory=uuid.uuid4, unique=True)
    organisation: sa_orm.Mapped[Organisation] = Relationship(back_populates="invitation_keys")


class OrganisationMember(CustomSQLModel, table=True):
    __tablename__ = "organisation_member"

    id: int = Field(primary_key=True)

    user_id: int = Field(foreign_key="user.id")
    organisation_id: int = Field(foreign_key="organisation.id")
    role: OrganisationRole = Field(sa_column=sa.Column(sa.Enum(OrganisationRole), nullable=False))

    organisation: sa_orm.Mapped[Organisation] = Relationship(back_populates="members")
    user: sa_orm.Mapped["UserORM"] = Relationship(back_populates="organisations")


class ProjectBase(CustomSQLModel):
    name: str


class Project(ProjectBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    organisation_id: int | None = Field(foreign_key="organisation.id", nullable=False)

    organisation: sa_orm.Mapped[Organisation] = Relationship(back_populates="projects")
    roles: sa_orm.Mapped[list["Role"]] = Relationship(back_populates="project", cascade_delete=True)
    problems: sa_orm.Mapped[list["ProblemORM"]] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"order_by": "ProblemORM.id.desc()"},
        cascade_delete=True,
    )
    groups: sa_orm.Mapped[list["Group"]] = Relationship(
        back_populates="project", cascade_delete=True
    )

    excluded_fields_on_copy: ClassVar[list[str]] = ["organisation", "roles", "groups"]


class Group(CustomSQLModel, table=True):
    """This is closer to tutorial groups and not intended to be used for submitting problems."""

    __tablename__ = "group"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(foreign_key="project.id")

    name: str

    members: sa_orm.Mapped[list["GroupMember"]] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={
            "order_by": "GroupMember.is_supervisor.desc()",
            # This line is used to fix an error with updating group members.
            # https://github.com/marshmallow-code/marshmallow-sqlalchemy/issues/250
            "cascade": "all, delete-orphan",
        },
    )

    project: sa_orm.Mapped[Project] = Relationship(back_populates="groups")


class RoleBase(CustomSQLModel):
    name: str


class Role(RoleBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")

    # Assignable permissions

    # Normal problem permissions
    view_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    view_full_problem_details_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    create_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    edit_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    delete_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )

    # Restricted problem permissions
    view_restricted_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    view_full_restricted_problem_details_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    edit_restricted_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    delete_restricted_problems_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )

    # Submission permissions
    make_submission_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    view_own_submission_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    view_supervised_submission_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    view_others_submission_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )

    # Group permissions
    view_groups_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    create_groups_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    edit_groups_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )
    delete_groups_access: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
    )

    project: sa_orm.Mapped[Project] = Relationship(back_populates="roles")
    invitation_keys: sa_orm.Mapped[list["InvitationKey"]] = Relationship(
        back_populates="role", cascade_delete=True
    )

    users: sa_orm.Mapped[list["UserORM"]] = Relationship(
        back_populates="roles", link_model=UserRole
    )


class InvitationKeyBase(CustomSQLModel):
    key: uuid.UUID = Field(default_factory=uuid.uuid4, unique=True)
    enabled: bool = Field(default=True)


class InvitationKey(InvitationKeyBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="role.id")

    role: sa_orm.Mapped[Role] = Relationship(back_populates="invitation_keys")
