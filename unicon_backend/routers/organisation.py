from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import DataError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from unicon_backend.dependencies.auth import get_current_user
from unicon_backend.dependencies.common import get_db_session
from unicon_backend.dependencies.organisation import get_organisation_by_id
from unicon_backend.dependencies.project import create_project_with_defaults
from unicon_backend.lib.permissions import (
    permission_check,
    permission_create,
    permission_delete,
    permission_list_for_subject,
    permission_lookup,
    permission_update,
)
from unicon_backend.models import Organisation, UserORM
from unicon_backend.models.organisation import (
    OrganisationInvitationKey,
    OrganisationMember,
    OrganisationRole,
)
from unicon_backend.schemas import OrganisationPublicWithMembers
from unicon_backend.schemas.organisation import (
    OrganisationCreate,
    OrganisationInvitationKeyCreate,
    OrganisationJoinRequest,
    OrganisationMemberUpdate,
    OrganisationPublic,
    OrganisationPublicWithProjects,
    OrganisationUpdate,
    ProjectCreate,
    ProjectPublic,
    UpdatableRole,
)

router = APIRouter(
    prefix="/organisations", tags=["organisation"], dependencies=[Depends(get_current_user)]
)


@router.get("/", summary="Get all organisations that user owns", response_model=list[Organisation])
def get_all_organisations(
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    accessible_organisation_ids = permission_lookup(Organisation, "view_basic", user)
    organisations = db_session.exec(
        select(Organisation).where(col(Organisation.id).in_(accessible_organisation_ids))
    ).all()
    return organisations


@router.post("/", summary="Create a new organisation", response_model=OrganisationPublic)
def create_organisation(
    create_data: OrganisationCreate,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    organisation = Organisation.model_validate({**create_data.model_dump(), "owner_id": user.id})
    db_session.add(organisation)
    db_session.commit()
    db_session.refresh(organisation)

    permission_create(organisation)

    return organisation


@router.put("/{id}", summary="Update an organisation", response_model=OrganisationPublic)
def update_organisation(
    update_data: OrganisationUpdate,
    db_session: Annotated[Session, Depends(get_db_session)],
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(organisation, "edit", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    organisation.sqlmodel_update(update_data)
    db_session.commit()
    db_session.refresh(organisation)
    return organisation


@router.delete("/{id}", summary="Delete an organisation")
def delete_organisation(
    db_session: Annotated[Session, Depends(get_db_session)],
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(organisation, "delete", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    db_session.delete(organisation)
    db_session.commit()

    permission_delete(organisation)
    return


@router.get(
    "/{id}", summary="Get an organisation by ID", response_model=OrganisationPublicWithProjects
)
def get_organisation(
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(organisation, "view_basic", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    projects = []
    for project in organisation.projects:
        permissions = permission_list_for_subject(project, user)
        if permissions["view"]:
            projects.append(ProjectPublic.model_validate(project, update=permissions))

    permissions = permission_list_for_subject(organisation, user)
    return OrganisationPublicWithProjects.model_validate(
        organisation, update={**permissions, "projects": projects}
    )


@router.post("/{id}/projects", summary="Create a new project", response_model=ProjectPublic)
def create_project(
    user: Annotated[UserORM, Depends(get_current_user)],
    create_data: ProjectCreate,
    db_session: Annotated[Session, Depends(get_db_session)],
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
):
    if not permission_check(organisation, "edit", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    assert organisation.id is not None
    project = create_project_with_defaults(create_data, organisation.id, user)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    # Update permission records
    permission_create(project)
    for role in project.roles:
        permission_create(role)

    # Return permission in project
    permissions = permission_list_for_subject(project, user)
    result = ProjectPublic.model_validate(project, update=permissions)

    return result


@router.get(
    "/{id}/members",
    summary="Get all users in an organisation",
    response_model=OrganisationPublicWithMembers,
)
def get_organisation_members(
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(organisation, "view", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    can_edit_roles = permission_check(organisation, "edit_roles", user)
    assert isinstance(can_edit_roles, bool)
    if not can_edit_roles:
        return OrganisationPublicWithMembers.model_validate(
            organisation, update={"invitation_keys": None, "edit_roles": can_edit_roles}
        )

    return OrganisationPublicWithMembers.model_validate(
        organisation, update={"edit_roles": can_edit_roles}
    )


@router.post("/{id}/invitation_key", summary="Create invitation key")
def create_organisation_invitation_key(
    id: int,
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    data: OrganisationInvitationKeyCreate,
):
    if not permission_check(organisation, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    existing_key = db_session.scalar(
        select(OrganisationInvitationKey)
        .where(OrganisationInvitationKey.role == data.role)
        .where(OrganisationInvitationKey.organisation_id == id)
    )
    if existing_key:
        raise HTTPException(HTTPStatus.CONFLICT, "Invitation key for this role already exists")

    key = OrganisationInvitationKey(
        role=data.role,
        organisation_id=id,
    )
    db_session.add(key)
    db_session.commit()
    return


@router.delete("/{id}/invitation_key/{key_id}", summary="Delete invitation key")
def delete_organisation_invitation_key(
    id: int,
    key_id: int,
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
):
    if not permission_check(organisation, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    key = db_session.scalar(
        select(OrganisationInvitationKey)
        .where(OrganisationInvitationKey.id == key_id)
        .where(OrganisationInvitationKey.organisation_id == id)
    )

    if key is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Invitation key not found")

    db_session.delete(key)
    db_session.commit()
    return


@router.post("/join", summary="Join an organisation", response_model=OrganisationPublic)
def join_organisation(
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    data: OrganisationJoinRequest,
):
    try:
        invitation_key = db_session.scalar(
            select(OrganisationInvitationKey)
            .where(OrganisationInvitationKey.key == data.key)
            .options(
                selectinload(OrganisationInvitationKey.organisation).selectinload(
                    Organisation.members
                )
            )
        )
    except DataError:
        invitation_key = None

    if invitation_key is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Invitation key not found")

    organisation = invitation_key.organisation
    if user.id == organisation.owner_id:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Owner cannot join their own organisation")

    if user.id in [member.user_id for member in organisation.members]:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "User already in organisation")

    new_member = OrganisationMember(user_id=user.id, role=invitation_key.role)
    organisation.members.append(new_member)
    db_session.commit()

    permission_create(new_member)
    db_session.refresh(organisation)

    return organisation


@router.put("/{id}/members/{user_id}", summary="Update member role")
def update_member(
    id: int,
    user_id: int,
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
    data: OrganisationMemberUpdate,
):
    if not permission_check(organisation, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    is_owner_change = data.role == "owner"

    member = db_session.scalar(
        select(OrganisationMember)
        .where(OrganisationMember.organisation_id == id)
        .where(OrganisationMember.user_id == user_id)
    )
    if not member:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Member not found")

    if not is_owner_change:
        old_member = member.model_copy()
        match data.role:
            case UpdatableRole.ADMIN:
                member.role = OrganisationRole.ADMIN
            case UpdatableRole.OBSERVER:
                member.role = OrganisationRole.OBSERVER
            case _:
                raise ValueError("Should not happen.")
        db_session.add(member)
        db_session.commit()
        permission_update(old_member, member)
        return

    old_organisation = organisation.model_copy()
    organisation.owner_id = user_id
    new_member = OrganisationMember(user_id=user.id, organisation_id=organisation.id, role="admin")
    db_session.add(new_member)
    db_session.add(organisation)
    db_session.delete(member)
    db_session.commit()

    permission_update(old_organisation, organisation)
    permission_create(new_member)
    permission_delete(member)


@router.delete("/{id}/members/{user_id}", summary="Delete member")
def delete_member(
    id: int,
    user_id: int,
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
    organisation: Annotated[Organisation, Depends(get_organisation_by_id)],
):
    if not permission_check(organisation, "edit_roles", user):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Permission denied")

    member = db_session.scalar(
        select(OrganisationMember)
        .where(OrganisationMember.organisation_id == id)
        .where(OrganisationMember.user_id == user_id)
    )
    if not member:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Member not found")

    db_session.delete(member)
    db_session.commit()
    permission_delete(member)
    return
