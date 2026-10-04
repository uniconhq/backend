"""What the workflow routes take and answer with. Forge checks the owner and
the name; these models say what shape the body has. A workflow goes out by
the owner and the name a person calls it by, `<owner>/<name>`, and never by
its id at the forge, which is built from an org's key.
"""

from pydantic import BaseModel


class CreateWorkflow(BaseModel):
    """A workflow to make under `owner`: the caller's own username, or the
    name of an org where they hold the manager role or above.
    """

    owner: str
    name: str


class Workflow(BaseModel):
    """A workflow, by its owner and its name."""

    owner: str
    name: str
