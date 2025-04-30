from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from unicon_backend.dependencies.auth import get_current_user
from unicon_backend.dependencies.common import get_db_session
from unicon_backend.models.organisation import Project, Role
from unicon_backend.models.user import UserORM
from unicon_backend.schemas.organisation import ProjectCreate

OWNER_ROLE = "Owner"
DEFAULT_ROLES = [OWNER_ROLE, "Helper", "Member"]

role_permissions = {}
role_permissions["member"] = [
    "view_problems_access",
    "make_submission_access",
    "view_own_submission_access",
]
role_permissions["helper"] = role_permissions["member"] + [
    "create_problems_access",
    "edit_problems_access",
    "delete_problems_access",
    "view_supervised_submission_access",
    "view_groups_access",
    "view_full_problem_details_access",
]
role_permissions["admin"] = role_permissions["helper"] + [
    "view_restricted_problems_access",
    "view_full_restricted_problem_details_access",
    "edit_restricted_problems_access",
    "delete_restricted_problems_access",
    "view_others_submission_access",
    "create_groups_access",
    "edit_groups_access",
    "delete_groups_access",
]


def get_default_project_roles(user: UserORM) -> list[Role]:
    return [
        Role(
            name="admin",
            users=[user],
            **{perm: True for perm in role_permissions["admin"]},
        ),
        *[
            Role(name=role, **{perm: True for perm in role_permissions[role]})
            for role in ["helper", "member"]
        ],
    ]


def create_project_with_defaults(
    create_data: ProjectCreate, organisation_id: int, user: UserORM
) -> Project:
    """Note: this function does not add permission tuples (e.g. permify.)
    Expected to be done outside the function (e.g. after the database commit after this function is called)."""
    new_project = Project.model_validate(
        {**create_data.model_dump(), "organisation_id": organisation_id}
    )

    # Create three default roles
    new_project.roles = get_default_project_roles(user)

    return new_project


def get_project_by_id(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
) -> Project:
    project = db_session.exec(
        select(Project)
        .join(Role)
        .where(Project.id == id)
        .options(
            selectinload(Project.roles.and_(Role.users.contains(user))).selectinload(
                Role.invitation_keys
            )
        )
    ).first()

    if project is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Project not found")

    return project
