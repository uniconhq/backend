"""Making a workflow. Anyone signed in may make one under their own name, or
under an org where they hold the manager role or above; forge decides which
and makes it, private, before the route answers.
"""

from fastapi import APIRouter, status
from forge.api import workflows
from forge.api.workflows import NewWorkflow

from unicon.api.deps import CurrentSession
from unicon.schemas.workflows import CreateWorkflow, Workflow

CREATED = status.HTTP_201_CREATED

router = APIRouter(tags=["workflows"])


@router.post(
    "/workflows",
    operation_id="createWorkflow",
    summary="Make a workflow",
    status_code=CREATED,
    response_model=Workflow,
)
async def create_workflow(session: CurrentSession, body: CreateWorkflow) -> NewWorkflow:
    """Under the caller's own username, or an org where they hold the manager
    role or above, with its first commit written as the caller.
    """
    return await workflows.create(session, body.owner, body.name)
