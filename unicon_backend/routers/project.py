from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import DataError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, and_, col, select

from unicon_backend.dependencies.auth import get_current_user
from unicon_backend.dependencies.common import get_db_session
from unicon_backend.dependencies.project import get_project_by_id
from unicon_backend.evaluator.problem import Problem
from unicon_backend.lib.permissions import (
    permission_check,
    permission_create,
    permission_delete,
    permission_list_for_subject,
    permission_lookup,
    permission_update,
)
from unicon_backend.models.links import GroupMember, UserRole
from unicon_backend.models.organisation import Group, InvitationKey, Project, Role
from unicon_backend.models.problem import (
    ProblemORM,
    SubmissionORM,
    SubmissionPublic,
    TaskAttemptORM,
)
from unicon_backend.models.user import UserORM
from unicon_backend.schemas.group import GroupCreate, GroupPublic, UserPublicWithRolesAndGroups
from unicon_backend.schemas.organisation import (
    ProblemBaseWithPermissions,
    ProjectPublic,
    ProjectPublicWithProblems,
    ProjectUpdate,
    RoleCreate,
    RolePublic,
    RolePublicWithInvitationKeys,
    UserRoleUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(get_current_user)])


@router.get("/", summary="Get all projects user is part of", response_model=list[ProjectPublic])
def get_all_projects(
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
):
    project_ids = permission_lookup(Project, "view", user)
    projects = db_session.exec(
        select(Project)
        .where(col(Project.id).in_(project_ids))
        .options(selectinload(Project.roles.and_(Role.users.any(col(UserORM.id) == user.id))))
    ).all()

    result = []
    for project in projects:
        permissions = permission_list_for_subject(project, user)
        result.append(ProjectPublic.model_validate(project, update=permissions))
    return result


@router.get("/{id}", summary="Get a project", response_model=ProjectPublicWithProblems)
def get_project(
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(project, "view", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    accessible_problem_ids = permission_lookup(ProblemORM, "view_index", user)

    # whether user can access individual problem page (e.g. problem is not open = user may not be able to)
    viewable_problem_ids = set(permission_lookup(ProblemORM, "view", user))
    editable_problem_ids = set(permission_lookup(ProblemORM, "edit", user))

    permissions = permission_list_for_subject(project, user)
    result = ProjectPublicWithProblems.model_validate(
        project,
        update={
            **permissions,
            "problems": [
                ProblemBaseWithPermissions.model_validate(
                    problem,
                    update={
                        "view": problem.id in viewable_problem_ids,
                        "edit": problem.id in editable_problem_ids,
                    },
                )
                for problem in project.problems
                if problem.id in accessible_problem_ids
            ],
        },
    )

    return result


@router.put("/{id}", summary="Update a project")
def update_project(
    db_session: Annotated[Session, Depends(get_db_session)],
    update_data: ProjectUpdate,
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(project, "edit", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    project.sqlmodel_update(update_data)
    db_session.commit()
    db_session.refresh(project)

    return


@router.delete("/{id}", summary="Delete a project")
def delete_project(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    project = db_session.get(Project, id)
    if not project:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Project not found")
    if not permission_check(project, "delete", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    db_session.delete(project)
    db_session.commit()
    return


@router.get(
    "/{id}/roles",
    summary="Get all roles in a project",
    response_model=list[RolePublicWithInvitationKeys],
)
def get_project_roles(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(project, "view_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    return db_session.exec(
        select(Role)
        .join(Project)
        .where(Project.id == id)
        .options(selectinload(Role.invitation_keys))
        .order_by(col(Role.id))
    ).all()


@router.get(
    "/{id}/users",
    summary="Get all users in a project",
    response_model=list[UserPublicWithRolesAndGroups],
)
def get_project_users(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(project, "view", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    return db_session.exec(
        select(UserORM)
        .join(UserRole)
        .join(Role)
        .join(Project)
        .where(Project.id == id)
        .options(
            selectinload(UserORM.roles.and_(col(Role.project_id) == id)),
            selectinload(
                UserORM.group_members.and_(GroupMember.group.has(col(Group.project_id) == id))
            ).selectinload(GroupMember.group),
        )
    ).all()


@router.delete("/{id}/users/{user_id}", summary="Remove user from project")
def remove_user_from_project(
    id: int,
    user_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if user_id != user.id and not permission_check(project, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    user_role = db_session.scalar(
        select(UserRole)
        .where(col(UserRole.user_id) == user_id)
        .where(col(UserRole.role_id).in_(select(Role.id).where(Role.project_id == id)))
    )

    if not user_role:
        raise HTTPException(HTTPStatus.NOT_FOUND, "User not found in project")

    db_session.delete(user_role)
    db_session.commit()
    permission_delete(user_role)
    return


@router.patch("/{id}/users", summary="Update users' roles in project")
def update_users_in_project(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    data: list[UserRoleUpdate],
):
    if not permission_check(project, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    proj_role_ids = set(db_session.scalars(select(Role.id).where(Role.project_id == id)))
    user_roles = list(
        db_session.scalars(select(UserRole).where(col(UserRole.role_id).in_(proj_role_ids)))
    )
    user_ids_in_proj = set(user_role.user_id for user_role in user_roles)

    if any(
        update.user_id not in user_ids_in_proj or update.role_id not in proj_role_ids
        for update in data
    ):
        raise HTTPException(
            HTTPStatus.BAD_REQUEST,
            "User or role not found in project",
        )

    user_id_to_user_role = {user_role.user_id: user_role for user_role in user_roles}
    for update in data:
        user_role = user_id_to_user_role[update.user_id]
        if user_role.role_id != update.role_id:
            old_user_role = user_role.model_copy()
            user_role.role_id = update.role_id
            db_session.add(user_role)
            db_session.commit()
            db_session.refresh(user_role)
            permission_update(old_user_role, user_role)

    return


@router.get("/{id}/groups", summary="Get all groups in a project", response_model=list[GroupPublic])
def get_project_groups(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    # TODO: implement group permissions
    if not permission_check(project, "view_groups", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    return db_session.exec(
        select(Group)
        .where(Group.project_id == id)
        # .where(col(Group.id).in_(accessible_group_ids))]
        .order_by(col(Group.name))
        .options(selectinload(Group.members).selectinload(GroupMember.user))
    ).all()


@router.post("/{id}/groups", summary="Create a new group", response_model=GroupPublic)
def create_group(
    group: GroupCreate,
    project: Annotated[Project, Depends(get_project_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(project, "create_groups", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    new_group = Group(name=group.name)
    project.groups.append(new_group)

    db_session.add(new_group)
    db_session.commit()
    db_session.refresh(new_group)

    permission_create(new_group)
    return new_group


@router.get(
    "/{id}/submissions",
    summary="Get all submissions in a project",
    response_model=list[SubmissionPublic],
)
def get_project_submissions(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    all_users: bool = False,
):
    accessible_submission_ids = permission_lookup(SubmissionORM, "view", user)

    query = (
        select(SubmissionORM)
        .where(SubmissionORM.problem.has(col(ProblemORM.project_id) == id))
        .where(col(SubmissionORM.id).in_(accessible_submission_ids))
        .options(
            selectinload(SubmissionORM.task_attempts).selectinload(TaskAttemptORM.task_results),
            selectinload(SubmissionORM.task_attempts).selectinload(TaskAttemptORM.task),
            selectinload(SubmissionORM.user)
            .selectinload(
                UserORM.group_members.and_(GroupMember.group.has(col(Group.project_id) == id))
            )
            .selectinload(GroupMember.group),
            selectinload(SubmissionORM.problem),
        )
    )

    # TODO: this will be useful for admin view, but we need to add access control
    if not all_users:
        pass

    return db_session.exec(query).all()


@router.post("/{id}/roles", summary="Create a new role", response_model=RolePublic)
def create_role(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    role_data: RoleCreate,
):
    if not permission_check(project, "add_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    role = Role(**role_data.model_dump())
    role.project_id = id
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)

    permission_create(role)

    return role


@router.post("/{key}/join", summary="Join project by invitation key", response_model=ProjectPublic)
def join_project(
    key: str,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    try:
        role = db_session.exec(
            select(Role)
            .join(Role.invitation_keys)
            .where(
                Role.invitation_keys.any(
                    and_(
                        InvitationKey.key == key,
                        InvitationKey.enabled == True,
                    )
                )
            )
        ).first()
    except DataError:
        # invitation key is an invalid uuid
        role = None

    if role is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Invitation key not found")

    project_role_ids = [role.id for role in role.project.roles]
    user_role = db_session.exec(
        select(UserRole).where(
            and_(UserRole.user_id == user.id, col(UserRole.role_id).in_(project_role_ids))
        )
    ).first()

    if user_role:
        permission_delete(user_role)
        db_session.delete(user_role)

    new_user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(new_user_role)
    db_session.commit()

    permission_create(new_user_role)

    permissions = permission_list_for_subject(role.project, user)
    return ProjectPublic.model_validate(role.project, update=permissions)


@router.post("/{id}/problems", description="Create a new problem")
def create_problem(
    problem: Problem,
    db_session: Annotated[Session, Depends(get_db_session)],
    project: Annotated[Project, Depends(get_project_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
) -> ProblemORM:
    if not permission_check(project, "create_problems", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    new_problem = ProblemORM.from_problem(problem)
    project.problems.append(new_problem)

    db_session.add(project)
    db_session.commit()
    db_session.refresh(new_problem)

    permission_create(new_problem)

    return new_problem
