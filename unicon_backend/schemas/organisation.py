import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.models.organisation import (
    InvitationKeyBase,
    OrganisationBase,
    OrganisationRole,
    ProjectBase,
    RoleBase,
)

if TYPE_CHECKING:
    from unicon_backend.schemas.auth import UserPublic


class ProblemBase(CustomSQLModel):
    id: int
    name: str
    description: str
    project_id: int
    restricted: bool
    published: bool
    started_at: datetime
    ended_at: datetime | None
    closed_at: datetime | None


class ProblemBaseWithPermissions(ProblemBase):
    view: bool
    edit: bool


class MiniOrganisationPublic(CustomSQLModel):
    id: int
    name: str


class OrganisationCreate(OrganisationBase):
    pass


class OrganisationUpdate(OrganisationBase):
    pass


class OrganisationPublic(OrganisationBase):
    id: int


class OrganisationPublicWithAllPermissions(OrganisationPublic):
    edit: bool
    edit_roles: bool
    delete: bool


class OrganisationPublicWithProjects(OrganisationPublicWithAllPermissions):
    projects: list["ProjectPublic"]


class OrganisationMemberPublic(CustomSQLModel):
    user: "UserPublic"
    role: OrganisationRole


class OrganisationInvitationKeyPublic(CustomSQLModel):
    id: int
    role: OrganisationRole
    key: uuid.UUID


class OrganisationPublicWithMembers(OrganisationPublic):
    owner: "UserPublic"
    members: list[OrganisationMemberPublic]
    """does not include owner - get this from the owner attribute"""
    invitation_keys: list[OrganisationInvitationKeyPublic] | None
    """it is null if user has no permission to edit_roles"""

    edit_roles: bool


class OrganisationInvitationKeyCreate(CustomSQLModel):
    role: OrganisationRole


class OrganisationJoinRequest(CustomSQLModel):
    key: str


class UpdatableRole(StrEnum):
    """this is OrganisationRole + owner"""

    ADMIN = "admin"
    OBSERVER = "observer"
    OWNER = "owner"


class OrganisationMemberUpdate(CustomSQLModel):
    role: UpdatableRole


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    pass


class ProjectPublic(ProjectBase):
    id: int
    roles: list["RolePublic"]

    # permissions
    view_own_submission: bool
    view_supervised_submission: bool
    view_others_submission: bool
    view_roles: bool
    add_roles: bool
    edit_roles: bool

    create_problems: bool

    view_groups: bool
    create_groups: bool
    edit_groups: bool
    delete_groups: bool

    organisation: MiniOrganisationPublic


class ProjectPublicWithProblems(ProjectPublic):
    problems: list[ProblemBaseWithPermissions]


class RolePublic(RoleBase):
    id: int
    project_id: int

    view_problems_access: bool
    view_full_problem_details_access: bool
    create_problems_access: bool
    edit_problems_access: bool
    delete_problems_access: bool

    view_restricted_problems_access: bool
    view_full_restricted_problem_details_access: bool
    edit_restricted_problems_access: bool
    delete_restricted_problems_access: bool

    make_submission_access: bool
    view_own_submission_access: bool
    view_supervised_submission_access: bool
    view_others_submission_access: bool

    view_groups_access: bool
    create_groups_access: bool
    edit_groups_access: bool
    delete_groups_access: bool


class RoleCreate(RoleBase):
    name: str


class RoleUpdate(RoleBase):
    name: str

    view_problems_access: bool
    view_full_problem_details_access: bool
    create_problems_access: bool
    edit_problems_access: bool
    delete_problems_access: bool

    view_restricted_problems_access: bool
    view_full_restricted_problem_details_access: bool
    edit_restricted_problems_access: bool
    delete_restricted_problems_access: bool

    make_submission_access: bool
    view_own_submission_access: bool
    view_supervised_submission_access: bool
    view_others_submission_access: bool

    view_groups_access: bool
    create_groups_access: bool
    edit_groups_access: bool
    delete_groups_access: bool


class RolePublicWithInvitationKeys(RolePublic):
    invitation_keys: list["InvitationKeyPublic"]


class InvitationKeyPublic(InvitationKeyBase):
    pass


class UserRoleUpdate(CustomSQLModel):
    user_id: int
    role_id: int
