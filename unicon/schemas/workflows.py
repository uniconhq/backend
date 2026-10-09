"""What the workflow routes take and answer with. Forge checks the owner,
the name and who may do what; these models say what shape each body has. A
workflow goes out by the owner and the name a person calls it by,
`<owner>/<name>`, and never by its id at the forge, which is built from an
org's key. A definition travels as the text of its `workflow.yaml`, with the
token it was read with, which a save carries back; none saves a file that
is not there yet. A primitive goes out with its declared ports, so the
editor's palette shows each with its type and its marks.
"""

from typing import Literal, Self

from forge.api.workflows import (
    Draft,
    Port,
    PrimitiveVersion,
    Visibility,
    WorkflowSummary,
    WorkflowView,
)
from pydantic import BaseModel, Field


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


class CopyWorkflow(BaseModel):
    """A copy to make of `source`, `<owner>/<name>@<version>`, as `name`
    under `owner`, which follows the rule for making one.
    """

    source: str
    owner: str
    name: str


class CombineWorkflows(BaseModel):
    """A workflow to make as `name` under `owner` from two or more
    `sources`, each `<owner>/<name>@<version>`, inlined in their order.
    """

    sources: list[str] = Field(min_length=1, max_length=20)
    owner: str
    name: str


class WorkflowItem(BaseModel):
    """A workflow a person may read: its visibility, its versions in natural
    order, and whether they may edit it.
    """

    owner: str
    name: str
    visibility: Visibility
    versions: list[str]
    editable: bool

    @classmethod
    def of(cls, summary: WorkflowSummary) -> Self:
        return cls(
            owner=summary.owner,
            name=summary.name,
            visibility=summary.visibility,
            versions=list(summary.versions),
            editable=summary.editable,
        )


class Definition(BaseModel):
    """A `workflow.yaml` as text, and the token a save of it carries back:
    none for one that is not there yet.
    """

    content: str
    token: str | None

    @classmethod
    def of(cls, draft: Draft) -> Self:
        return cls(content=draft.text, token=draft.token)


class WorkflowPage(WorkflowItem):
    """A workflow as its page shows it. For someone who may edit it, `draft`,
    its `workflow.yaml` now, and `readers`, the usernames it is shared with;
    for anyone else, no draft and no readers.
    """

    draft: Definition | None
    readers: list[str]

    @classmethod
    def of_view(cls, view: WorkflowView) -> Self:
        item = WorkflowItem.of(view.summary)
        return cls(
            **item.model_dump(),
            draft=Definition.of(view.draft) if view.draft is not None else None,
            readers=[reader.username for reader in view.readers],
        )


class SaveDefinition(BaseModel):
    """A draft to write over the one read with `token`, or to create when
    the token is none. Whatever it holds saves, problems and all.
    """

    content: str
    token: str | None


class VersionContent(BaseModel):
    """A workflow's `workflow.yaml` at one version."""

    content: str


class CreateVersion(BaseModel):
    """A name to freeze the saved draft under, such as `v1`."""

    version: str


class Version(BaseModel):
    version: str


class CheckDefinition(BaseModel):
    """A `workflow.yaml` to check as a version would be, writing nothing."""

    content: str


class DefinitionProblem(BaseModel):
    """One problem: its YAML path in `workflow.yaml`, `steps[1].with.binary`,
    and what is wrong there. The path is empty for the file as a whole.
    """

    path: str
    message: str


class Checked(BaseModel):
    """Every problem a version would be refused for; none means it would be
    made.
    """

    problems: list[DefinitionProblem]


class SetVisibility(BaseModel):
    """Private, shared or public. Private and public empty the list of
    readers; shared keeps it.
    """

    visibility: Visibility


class Reader(BaseModel):
    """Someone a workflow is shared with, by their username."""

    username: str


class PrimitivePort(BaseModel):
    """One port: its type, the options an enum takes, whether it may be left
    out, and on an input whether the primitive runs what arrives there and
    whether it keeps it from the program it runs.
    """

    type: str
    options: list[str] | None
    optional: bool
    runs: bool | None
    secret: bool

    @classmethod
    def of(cls, port: Port) -> Self:
        return cls(
            type=port.type.value,
            options=list(port.options) if port.options is not None else None,
            optional=port.optional,
            runs=port.runs,
            secret=port.secret,
        )


class LimitSource(BaseModel):
    """A container limit raised to `input * scale + add` when that is more."""

    input: str
    scale: float
    add: float


Limit = Literal["time_ms", "cpu_ms", "memory_mb", "pids", "output_mb", "gpus"]


class Primitive(BaseModel):
    """One version of a primitive, `ref` being what a step's `use:` names.
    Its declaration is in `batch`, `network`, `limits`, `limits_from`,
    `inputs` and `outputs`; a version in a format the platform no longer
    reads has none of them and `problem` instead, so no step uses it.
    """

    ref: str
    name: str
    version: str
    batch: bool = False
    network: bool = False
    limits: dict[Limit, int] = Field(default_factory=dict)
    limits_from: dict[Limit, LimitSource] = Field(default_factory=dict)
    inputs: dict[str, PrimitivePort] = Field(default_factory=dict)
    outputs: dict[str, PrimitivePort] = Field(default_factory=dict)
    problem: str | None = None

    @classmethod
    def of(cls, found: PrimitiveVersion) -> Self:
        declared = found.declaration
        if declared is None:
            return cls(ref=found.ref, name=found.name, version=found.version, problem=found.problem)
        return cls(
            ref=found.ref,
            name=found.name,
            version=found.version,
            batch=declared.batch,
            network=declared.network,
            limits=declared.limits.as_mapping(),
            limits_from={
                limit: LimitSource(input=source.input, scale=source.scale, add=source.add)
                for limit, source in declared.limits_from.items()
            },
            inputs={name: PrimitivePort.of(port) for name, port in declared.inputs.items()},
            outputs={name: PrimitivePort.of(port) for name, port in declared.outputs.items()},
        )
