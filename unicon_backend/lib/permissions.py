from datetime import datetime
from typing import Any, Final

import permify as p

from unicon_backend.constants import PERMIFY_HOST, PERMIFY_SCHEMA_VERSION, PERMIFY_TENANT_ID
from unicon_backend.models.file import FileORM
from unicon_backend.models.links import GroupMember, UserRole
from unicon_backend.models.organisation import (
    Group,
    Organisation,
    OrganisationMember,
    OrganisationRole,
    Project,
    Role,
)
from unicon_backend.models.problem import ProblemORM, SubmissionORM
from unicon_backend.models.user import UserORM

CONFIGURATION = p.Configuration(host=PERMIFY_HOST)

_api_client = p.ApiClient(p.Configuration(host=PERMIFY_HOST))
_data_api = p.DataApi(_api_client)
_schema_api = p.SchemaApi(_api_client)
_perms_api = p.PermissionApi(_api_client)


def _get_latest_schema_version() -> str | None:
    """Get the latest schema version from Permify."""
    return _schema_api.schemas_list(PERMIFY_TENANT_ID, p.SchemaListBody()).head


SCHEMA_VERSION: str | None = PERMIFY_SCHEMA_VERSION or _get_latest_schema_version()

if SCHEMA_VERSION is None:
    raise RuntimeError("Failed to get Permify schema version!")


DEFAULT_METADATA: Final = {"schema_version": SCHEMA_VERSION}


def _get_all_tuples_and_attributes() -> tuple[list[p.Tuple], list[p.Attribute]]:
    tuples: list[p.Tuple] = []
    attributes: list[p.Attribute] = []

    with p.ApiClient(CONFIGURATION) as api_client:
        data_api = p.DataApi(api_client)

        tokens = set()
        while True:
            attributes_response = data_api.data_attributes_read(
                PERMIFY_TENANT_ID,
                p.ReadAttributesBody(
                    metadata=p.AttributeReadRequestMetadata.model_validate(
                        {"schema_version": SCHEMA_VERSION}
                    ),
                    filter=p.AttributeFilter(),
                ),
            )
            if attributes_response.attributes:
                attributes += attributes_response.attributes
            if (
                not attributes_response.continuous_token
                or attributes_response.continuous_token in tokens
            ):
                break

            tokens.add(attributes_response.continuous_token)

        tokens = set()
        while True:
            tuples_response = data_api.data_relationships_read(
                PERMIFY_TENANT_ID,
                p.ReadRelationshipsBody(
                    metadata=p.RelationshipReadRequestMetadata.model_validate(
                        {"schema_version": SCHEMA_VERSION}
                    ),
                    filter=p.TupleFilter(),
                ),
            )
            if tuples_response.tuples:
                tuples += tuples_response.tuples
            if not tuples_response.continuous_token or tuples_response.continuous_token in tokens:
                break
            tokens.add(tuples_response.continuous_token)
        return tuples, attributes


def delete_all_permission_records():
    tuples, attributes = _get_all_tuples_and_attributes()
    _delete_tuples_and_attributes(tuples, attributes)


##########################################
#    List of tuples to make consistent   #
##########################################
# project_tuples [PROJECT, role, USER]
# role_tuples [PROJECT, what_permission_access, ROLE]
# role_assign_tuples [ROLE, assignee, USER]
# problem_tuples [PROBLEM, project, PROJECT]
# submission_tuples [SUBMISSION, "problem", PROBLEM] [SUBMISSION, "owner", USER] [SUBMISSION, "group_owner", GROUP]
# group_tuples [GROUP, member, SUBMISSION]
# group_member_tuples [GROUP, member, USER]
# group_supervisor_tuples [GROUP, supervisor, USER]
# organisation_tuples [ORGANISATION, owner|admin|observer, USER]

# NOT YET IMPLEMENTED
# problem_group_tuples [TO DENOTE]

PERMISSIONS = [
    "view_problems_access",
    "create_problems_access",
    "edit_problems_access",
    "delete_problems_access",
    "view_restricted_problems_access",
    "view_full_restricted_problem_details_access",
    "edit_restricted_problems_access",
    "delete_restricted_problems_access",
    "make_submission_access",
    "view_own_submission_access",
    "view_full_problem_details_access",
    "view_supervised_submission_access",
    "view_others_submission_access",
    "view_groups_access",
    "create_groups_access",
    "edit_groups_access",
    "delete_groups_access",
]

DEPTH: Final[int] = 200


def permission_lookup(model_class: Any, permission: str, user: UserORM) -> list[int]:
    """Given a model class, return all ids that the user can do PERMISSION on.

    This function uses the Lookup Entity route (https://docs.permify.co/api-reference/permission/lookup-entity)"""
    metadata = p.PermissionLookupEntityRequestMetadata.from_dict(
        {**DEFAULT_METADATA, "depth": DEPTH}
    )

    def fetch_entity_ids(cont_token: str | None = None) -> tuple[list[int], str | None]:
        resp = _perms_api.permissions_lookup_entity(
            PERMIFY_TENANT_ID,
            p.LookupEntityBody(
                metadata=metadata,
                entity_type=_model_to_type(model_class),
                permission=permission,
                subject=p.Subject(type="user", id=str(user.id)),
                continuous_token=cont_token,
                context=p.Context(data={"current_date": datetime.now().isoformat()}),
            ),
        )
        ids = [int(entity_id) for entity_id in resp.entity_ids or []]
        return ids, resp.continuous_token

    cont_tokens: set[str] = set()
    entity_ids, cont_token = fetch_entity_ids()

    while cont_token and cont_token not in cont_tokens:
        cont_tokens.add(cont_token)
        more_entity_ids, cont_token = fetch_entity_ids(cont_token)
        entity_ids.extend(more_entity_ids)

    return entity_ids


def permission_list_for_subject(model: Any, user: UserORM) -> dict[str, bool]:
    """Which permissions user:x can perform on entity:y?

    This function users the Subject Permission List route (https://docs.permify.co/api-reference/permission/subject-permission)
    """
    metadata = p.PermissionSubjectPermissionRequestMetadata.from_dict(
        {**DEFAULT_METADATA, "depth": DEPTH}
    )

    result = _perms_api.permissions_subject_permission(
        PERMIFY_TENANT_ID,
        p.SubjectPermissionBody(
            metadata=metadata,
            entity=_make_entity(_model_to_type(model), str(model.id)),
            subject=_make_entity("user", str(user.id)),
            context=p.Context(data={"current_date": datetime.now().isoformat()}),
        ),
    )

    if not result.results:
        # This should not happen.
        raise ValueError("No results found")

    return {
        permission: allowed == p.CheckResult.CHECK_RESULT_ALLOWED
        for permission, allowed in result.results.items()
    }


def _get_tuples_and_attributes(model: Any) -> tuple[list[p.Tuple], list[p.Attribute]]:
    model_type = type(model)

    if model_type is Project:
        tuples, attributes = _create_project(model)
    elif model_type is Role:
        tuples, attributes = _create_role(model)
    elif model_type is ProblemORM:
        tuples, attributes = _create_problem(model)
    elif model_type is SubmissionORM:
        tuples, attributes = _create_submission(model)
    elif model_type is UserRole:
        tuples, attributes = _create_user_role(model)
    elif model_type is Organisation:
        tuples, attributes = _create_organisation(model)
    elif model_type is Group:
        tuples, attributes = _create_group(model)
    elif model_type is GroupMember:
        tuples, attributes = _create_group_member(model)
    elif model_type is OrganisationMember:
        tuples, attributes = _create_organisation_member(model)
    elif model_type is FileORM:
        tuples, attributes = _create_file(model)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")

    return tuples, attributes


def permission_create(model: Any):
    """given a model, create permission records for it"""
    tuples, attributes = _get_tuples_and_attributes(model)

    metadata = p.DataWriteRequestMetadata.from_dict({"schema_version": SCHEMA_VERSION})
    if not metadata:
        # This should not happen.
        raise ValueError("Failed to create metadata")

    _data_api.data_write(
        PERMIFY_TENANT_ID,
        p.DataWriteBody(metadata=metadata, tuples=tuples, attributes=attributes),
    )


def permission_delete(model: Any):
    """given a model, delete permission records for it"""
    tuples, attributes = _get_tuples_and_attributes(model)

    if p.DataWriteRequestMetadata.from_dict(DEFAULT_METADATA) is None:
        # This should not happen.
        raise ValueError("Failed to create metadata")

    _delete_tuples_and_attributes(tuples, attributes)


def _delete_tuples_and_attributes(
    delete_tuples: list[p.Tuple], delete_attributes: list[p.Attribute]
):
    # delete old tuples
    for old_tuple in delete_tuples:
        entity = old_tuple.entity
        relation = old_tuple.relation
        subject = old_tuple.subject
        if (
            entity is None
            or relation is None
            or subject is None
            or entity.id is None
            or subject.id is None
        ):
            # This should never happen.
            raise ValueError("Failed to extract entity, relation, or subject")
        _data_api.data_delete(
            PERMIFY_TENANT_ID,
            p.DataDeleteBody(
                tuple_filter=p.TupleFilter(
                    entity=p.EntityFilter(type=entity.type, ids=[entity.id]),
                    relation=relation,
                    subject=p.SubjectFilter(type=subject.type, ids=[subject.id]),
                ),
                attribute_filter=p.AttributeFilter(),
            ),
        )

    for old_attribute in delete_attributes:
        entity = old_attribute.entity
        attribute = old_attribute.attribute
        if entity is None or attribute is None or entity.id is None:
            # This should never happen.
            raise ValueError("Failed to extract entity or attribute")
        _data_api.data_delete(
            PERMIFY_TENANT_ID,
            p.DataDeleteBody(
                tuple_filter=p.TupleFilter(),
                attribute_filter=p.AttributeFilter(
                    entity=p.EntityFilter(type=entity.type, ids=[entity.id]),
                    attributes=[attribute],
                ),
            ),
        )


def permission_update(old: Any, new: Any):
    """given a model, update permission records for it"""
    if type(old) != type(new):
        raise ValueError("Old and new models must be of the same type")

    delete_tuples, delete_attributes = _get_tuples_and_attributes(old)
    create_tuples, create_attributes = _get_tuples_and_attributes(new)

    metadata = p.DataWriteRequestMetadata.from_dict({"schema_version": SCHEMA_VERSION})
    if not metadata:
        # This should not happen.
        raise ValueError("Failed to create metadata")

    # Optimisation: Remove the intersecton of tuples/attributes being deleted/created
    tuples_intersection = [t for t in delete_tuples if t in create_tuples and t in delete_tuples]
    attributes_intersection = [
        a for a in delete_attributes if a in create_attributes and a in delete_attributes
    ]
    delete_tuples = [t for t in delete_tuples if t not in tuples_intersection]
    delete_attributes = [a for a in delete_attributes if a not in attributes_intersection]
    create_tuples = [t for t in create_tuples if t not in tuples_intersection]
    create_attributes = [a for a in create_attributes if a not in attributes_intersection]

    _delete_tuples_and_attributes(delete_tuples, delete_attributes)

    # recreate new tuples
    with p.ApiClient(CONFIGURATION) as api_client:
        data_api = p.DataApi(api_client)
        data_api.data_write(
            PERMIFY_TENANT_ID,
            p.DataWriteBody(metadata=metadata, tuples=create_tuples, attributes=create_attributes),
        )

    for old_attribute in delete_attributes:
        entity = old_attribute.entity
        attribute = old_attribute.attribute
        if entity is None or attribute is None or entity.id is None:
            # This should never happen.
            raise ValueError("Failed to extract entity or attribute")

        _data_api.data_delete(
            PERMIFY_TENANT_ID,
            p.DataDeleteBody(
                tuple_filter=p.TupleFilter(),
                attribute_filter=p.AttributeFilter(
                    entity=p.EntityFilter(type=entity.type, ids=[entity.id]),
                    attributes=[attribute],
                ),
            ),
        )

    # recreate new tuples
    _data_api.data_write(
        PERMIFY_TENANT_ID,
        p.DataWriteBody(metadata=metadata, tuples=create_tuples, attributes=create_attributes),
    )


def _model_to_type(model: Any) -> str:
    model_type = model if isinstance(model, type) else type(model)

    if model_type is Organisation:
        return "organisation"
    if model_type is Project:
        return "project"
    if model_type is Role:
        return "role"
    if model_type is ProblemORM:
        return "problem"
    if model_type is SubmissionORM:
        return "submission"
    if model_type is UserORM:
        return "user"
    if model_type is Group:
        return "group"
    if model_type is FileORM:
        return "file"
    raise ValueError(f"Unsupported model type: {type(model)}")


def permission_check(entity, permission, subject) -> bool:
    """can SUBJECT (probably the user) do PERMISSION on ENTITY?"""
    if (
        metadata := p.PermissionCheckRequestMetadata.from_dict({**DEFAULT_METADATA, "depth": DEPTH})
    ) is None:
        # This should not happen.
        raise ValueError("Failed to create metadata")

    result = _perms_api.permissions_check(
        PERMIFY_TENANT_ID,
        p.CheckBody(
            metadata=metadata,
            entity=_make_entity(_model_to_type(entity), str(entity.id)),
            permission=permission,
            subject=_make_entity(_model_to_type(subject), str(subject.id)),
            context=p.Context(data={"current_date": datetime.now().isoformat()}),
        ),
    )
    return result.can == p.CheckResult.CHECK_RESULT_ALLOWED


def _make_tuple(entity, relation, subject) -> p.Tuple:
    if (
        result := p.Tuple.from_dict({"entity": entity, "relation": relation, "subject": subject})
    ) is None:
        # This should never happen.
        raise ValueError("Failed to create tuple")

    return result


def _get_permify_bool(bool: bool) -> p.Any:
    # I think the type error here is from a weird bug in p.Any where it collides with typing.Any (and should be fine)
    return p.Any.from_dict({"@type": "type.googleapis.com/base.v1.BooleanValue", "data": bool})  # type:ignore


def _get_permify_str(str: str) -> p.Any:
    return p.Any.from_dict({"@type": "type.googleapis.com/base.v1.StringValue", "data": str})  # type:ignore


def _make_attribute(entity, attribute, value) -> p.Attribute:
    attribute = p.Attribute.from_dict({"entity": entity, "attribute": attribute, "value": value})
    if not attribute:
        raise ValueError("Failed to create attribute")
    return attribute


def _make_entity(type: str, id: str):
    return {"type": type, "id": id}


def _create_organisation(organisation: Organisation) -> tuple[list[p.Tuple], list[p.Attribute]]:
    owner_link = _make_tuple(
        _make_entity("organisation", str(organisation.id)),
        "owner",
        _make_entity("user", str(organisation.owner_id)),
    )
    return [owner_link], []


def _create_organisation_member(
    organisationMember: OrganisationMember,
) -> tuple[list[p.Tuple], list[p.Attribute]]:
    relation = "admin" if organisationMember.role == OrganisationRole.ADMIN else "observer"
    member_link = _make_tuple(
        _make_entity("organisation", str(organisationMember.organisation_id)),
        relation,
        _make_entity("user", str(organisationMember.user_id)),
    )
    return [member_link], []


def _create_project(project: Project) -> tuple[list[p.Tuple], list[p.Attribute]]:
    project_to_organisation_link = _make_tuple(
        _make_entity("project", str(project.id)),
        "org",
        _make_entity("organisation", str(project.organisation_id)),
    )
    organisation_to_project_link = _make_tuple(
        _make_entity("organisation", str(project.organisation_id)),
        "project",
        _make_entity("project", str(project.id)),
    )
    return [project_to_organisation_link, organisation_to_project_link], []


def _create_role(role: Role) -> tuple[list[p.Tuple], list[p.Attribute]]:
    role_access_links = [
        _make_tuple(
            _make_entity("project", str(role.project_id)),
            permission,
            {**_make_entity("role", str(role.id)), "relation": "assignee"},
        )
        for permission in PERMISSIONS
        if getattr(role, permission)
    ]
    return role_access_links, []


def _create_problem(problem: ProblemORM) -> tuple[list[p.Tuple], list[p.Attribute]]:
    problem_project_link = _make_tuple(
        _make_entity("problem", str(problem.id)),
        "project",
        _make_entity("project", str(problem.project_id)),
    )
    attributes = [
        _make_attribute(
            _make_entity("problem", str(problem.id)),
            "restricted",
            _get_permify_bool(problem.restricted),
        ),
        _make_attribute(
            _make_entity("problem", str(problem.id)),
            "published",
            _get_permify_bool(problem.published),
        ),
        _make_attribute(
            _make_entity("problem", str(problem.id)),
            "started_at",
            _get_permify_str(problem.started_at.isoformat()),
        ),
        _make_attribute(
            _make_entity("problem", str(problem.id)),
            "closed_at",
            # If there is no lock date (`closed_at`), use the due date (`ended_at`)
            # If there is no due date, use the maximum date possible
            _get_permify_str((problem.closed_at or problem.ended_at or datetime.max).isoformat()),
        ),
    ]
    return [problem_project_link], attributes


def _create_submission(submission: SubmissionORM) -> tuple[list[p.Tuple], list[p.Attribute]]:
    submission_problem_link = _make_tuple(
        _make_entity("submission", str(submission.id)),
        "problem",
        _make_entity("problem", str(submission.problem_id)),
    )

    # TODO: account for group submissions
    submission_owner_link = _make_tuple(
        _make_entity("submission", str(submission.id)),
        "owner",
        _make_entity("user", str(submission.user_id)),
    )

    group_links = [
        _make_tuple(
            _make_entity("submission", str(submission.id)),
            "group",
            _make_entity("group", str(group_member.group.id)),
        )
        for group_member in submission.user.group_members
    ]

    return [submission_problem_link, submission_owner_link] + group_links, []


def _create_group_member(groupMember: GroupMember) -> tuple[list[p.Tuple], list[p.Attribute]]:
    if groupMember.is_supervisor:
        return _create_group_supervisor(groupMember)

    group = groupMember.group
    user = groupMember.user
    submissions = [
        submission
        for submission in user.submissions
        if submission.problem.project_id == group.project_id
    ]
    group_member_relation_tuple = _make_tuple(
        _make_entity("group", str(groupMember.group_id)),
        "member",
        _make_entity("user", str(groupMember.user_id)),
    )
    submission_tuples = [
        _make_tuple(
            _make_entity("submission", str(submission.id)),
            "group",
            _make_entity("group", str(groupMember.group_id)),
        )
        for submission in submissions
    ]
    return [group_member_relation_tuple] + submission_tuples, []


def _create_group_supervisor(
    groupSupervisor: GroupMember,
) -> tuple[list[p.Tuple], list[p.Attribute]]:
    group_supervisor_relation_tuple = _make_tuple(
        _make_entity("group", str(groupSupervisor.group_id)),
        "supervisor",
        _make_entity("user", str(groupSupervisor.user_id)),
    )
    return [group_supervisor_relation_tuple], []


def _create_group(group: Group) -> tuple[list[p.Tuple], list[p.Attribute]]:
    tuples = [
        _make_tuple(
            _make_entity("group", str(group.id)),
            "project",
            _make_entity("project", str(group.project_id)),
        )
    ]
    attributes = []
    for member in group.members:
        member_tuples, member_attributes = _create_group_member(member)
        tuples.extend(member_tuples)
        attributes.extend(member_attributes)

    return tuples, attributes


def _create_user_role(userRole: UserRole) -> tuple[list[p.Tuple], list[p.Attribute]]:
    """This is the role assignment link"""
    assignee_link = _make_tuple(
        _make_entity("role", str(userRole.role_id)),
        "assignee",
        _make_entity("user", str(userRole.user_id)),
    )
    return [assignee_link], []


def _create_file(file: FileORM) -> tuple[list[p.Tuple], list[p.Attribute]]:
    file_problem_link = _make_tuple(
        _make_entity("file", str(file.id)),
        file.parent_type,
        _make_entity(file.parent_type, str(file.parent_id)),
    )
    return [file_problem_link], []
