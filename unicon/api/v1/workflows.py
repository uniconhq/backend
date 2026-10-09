"""Workflows for anyone signed in: making one, the ones they may read, one
as its page shows it, its definition at a version, saving its draft,
making a version, checking a definition on its own, its visibility and who
it is shared with, copying one and combining several; and the platform's
primitives with their declared ports.

Every route needs a session and no role: forge decides who may act on a
workflow, its owner or a manager or admin of the org that owns it, and
every change is made at the forge as the caller, so the forge's own check
is underneath. A workflow someone may not read is answered `not_found`, in
the same words as one that is not there. A draft saves with its problems; a
version of one is refused `invalid_definition`, with every problem at its
YAML path in `errors`, the same shape check answers with.
"""

from typing import Annotated

from fastapi import APIRouter, Path, status
from forge.api import workflows
from forge.api.types import ConflictToken

from unicon.api.deps import CurrentSession
from unicon.schemas.workflows import (
    CheckDefinition,
    Checked,
    CombineWorkflows,
    CopyWorkflow,
    CreateVersion,
    CreateWorkflow,
    Definition,
    DefinitionProblem,
    Primitive,
    Reader,
    SaveDefinition,
    SetVisibility,
    Version,
    VersionContent,
    Workflow,
    WorkflowItem,
    WorkflowPage,
)

CREATED = status.HTTP_201_CREATED
NO_CONTENT = status.HTTP_204_NO_CONTENT
WORKFLOW = "/workflows/{owner}/{name}"

router = APIRouter(tags=["workflows"])

Owner = Annotated[str, Path(description="An org's name or a person's username")]
Name = Annotated[str, Path(description="The workflow's name under its owner")]


@router.post(
    "/workflows",
    operation_id="createWorkflow",
    summary="Make a workflow",
    status_code=CREATED,
    response_model=Workflow,
)
async def create_workflow(session: CurrentSession, body: CreateWorkflow) -> Workflow:
    """Under the caller's own username, or an org where they hold the manager
    role or above, with its first commit written as the caller.
    """
    made = await workflows.create(session, body.owner, body.name)
    return Workflow(owner=made.owner, name=made.name)


@router.get("/workflows", operation_id="listWorkflows", summary="The workflows one may read")
async def list_workflows(session: CurrentSession) -> list[WorkflowItem]:
    """The caller's own, their orgs', those shared with them and the public
    ones, by owner and then name, each saying whether they may edit it.
    """
    return [WorkflowItem.of(found) for found in await workflows.listing(session)]


@router.post(
    "/workflows/check", operation_id="checkWorkflow", summary="Check a definition on its own"
)
async def check_workflow(session: CurrentSession, body: CheckDefinition) -> Checked:
    """Every problem a version of the definition would be refused for, each
    at its YAML path, against the primitives its steps use as the caller
    reads them. Nothing is written.
    """
    found = await workflows.check(session, body.content)
    return Checked(problems=[DefinitionProblem(**problem) for problem in found])


@router.post(
    "/workflow-copies",
    operation_id="copyWorkflow",
    summary="Copy a workflow at a version",
    status_code=CREATED,
    response_model=Workflow,
)
async def copy_workflow(session: CurrentSession, body: CopyWorkflow) -> Workflow:
    """A new private workflow under `owner` holding the source's files at
    its version, with nothing written about where they came from.
    """
    made = await workflows.copy(session, body.source, body.owner, body.name)
    return Workflow(owner=made.owner, name=made.name)


@router.post(
    "/workflow-combinations",
    operation_id="combineWorkflows",
    summary="Combine workflows into one",
    status_code=CREATED,
    response_model=Workflow,
)
async def combine_workflows(session: CurrentSession, body: CombineWorkflows) -> Workflow:
    """A new private workflow under `owner` inlining every source, a clash
    of names taking the first free `-2`, `-3`.
    """
    made = await workflows.combine(session, body.sources, body.owner, body.name)
    return Workflow(owner=made.owner, name=made.name)


@router.get(WORKFLOW, operation_id="getWorkflow", summary="A workflow as its page shows it")
async def get_workflow(session: CurrentSession, owner: Owner, name: Name) -> WorkflowPage:
    """Its visibility, versions and whether the caller may edit it; for one
    who may, its draft with the token a save carries and who reads it.
    """
    return WorkflowPage.of_view(await workflows.view(session, owner, name))


@router.put(f"{WORKFLOW}/draft", operation_id="saveWorkflow", summary="Save the draft")
async def save_workflow(
    session: CurrentSession, owner: Owner, name: Name, body: SaveDefinition
) -> Definition:
    """Write `workflow.yaml` as the caller over the one read with `token`,
    problems and all. `conflict` when it has changed since.
    """
    token = ConflictToken(body.token) if body.token is not None else None
    return Definition.of(await workflows.save(session, owner, name, body.content, token))


@router.post(
    f"{WORKFLOW}/versions",
    operation_id="createWorkflowVersion",
    summary="Freeze the saved draft under a version",
    status_code=CREATED,
)
async def create_workflow_version(
    session: CurrentSession, owner: Owner, name: Name, body: CreateVersion
) -> Version:
    """Made only when the saved draft passes every check a version must;
    otherwise `invalid_definition` with every problem in `errors`, and no
    version made. Given the token the draft was saved with, `conflict` when
    someone has saved since.
    """
    token = ConflictToken(body.token) if body.token is not None else None
    made = await workflows.create_version(session, owner, name, body.version, token)
    return Version(version=made)


@router.get(
    f"{WORKFLOW}/versions/{{version}}",
    operation_id="getWorkflowVersion",
    summary="The definition at a version",
)
async def get_workflow_version(
    session: CurrentSession, owner: Owner, name: Name, version: str
) -> VersionContent:
    """Read as the caller: `not_found` when there is no such version or they
    may not read it.
    """
    return VersionContent(
        content=await workflows.read_version(session, f"{owner}/{name}@{version}")
    )


@router.put(
    f"{WORKFLOW}/visibility",
    operation_id="setWorkflowVisibility",
    summary="Make it private, shared or public",
    status_code=NO_CONTENT,
)
async def set_workflow_visibility(
    session: CurrentSession, owner: Owner, name: Name, body: SetVisibility
) -> None:
    await workflows.set_visibility(session, owner, name, body.visibility)


@router.put(
    f"{WORKFLOW}/readers/{{username}}",
    operation_id="shareWorkflow",
    summary="Share it with a person",
)
async def share_workflow(
    session: CurrentSession, owner: Owner, name: Name, username: str
) -> Reader:
    """`conflict` while the workflow is public, which everyone reads."""
    shared = await workflows.share(session, owner, name, username)
    return Reader(username=shared.username)


@router.delete(
    f"{WORKFLOW}/readers/{{username}}",
    operation_id="unshareWorkflow",
    summary="Take a person's read away",
    status_code=NO_CONTENT,
)
async def unshare_workflow(
    session: CurrentSession, owner: Owner, name: Name, username: str
) -> None:
    await workflows.unshare(session, owner, name, username)


@router.get("/primitives", operation_id="listPrimitives", summary="The platform's primitives")
async def list_primitives(session: CurrentSession) -> list[Primitive]:
    """Every primitive at every version with its declared ports, for the
    editor's palette. Every primitive is public; a session is all it needs.
    """
    return [Primitive.of(found) for found in await workflows.primitives(session)]
