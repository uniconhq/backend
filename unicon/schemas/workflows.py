"""What the workflow routes take and answer with. Forge checks the owner,
the name and who may do what; these models say what shape each body has. A
workflow goes out by the owner and the name a person calls it by,
`<owner>/<name>`, and never by its id at the forge, which is built from an
org's key. A definition travels as the text of its `workflow.yaml`, with the
token it was read with, which a save carries back; none saves a file that
is not there yet. A primitive goes out with its declared ports, so the
editor's palette shows each with its type and its marks.
"""

from typing import Any, Literal, Self

from forge.api.blocks import Better
from forge.api.workflows import Box as ForgeBox
from forge.api.workflows import BoxInput as ForgeBoxInput
from forge.api.workflows import BoxOutput as ForgeBoxOutput
from forge.api.workflows import (
    Draft,
    FromInput,
    FromMax,
    FromSum,
    LimitFrom,
    Port,
    PrimitiveVersion,
    Visibility,
    WorkflowSummary,
    WorkflowView,
)
from pydantic import BaseModel, Field, model_validator

from unicon.schemas.exact import Exact
from unicon.schemas.publications import FileChange


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
    none for one that is not there yet. `revision` names the saved repository,
    including its files, for publishing exactly that save.
    """

    content: str
    token: str | None
    revision: str | None = None

    @classmethod
    def of(cls, draft: Draft) -> Self:
        return cls(content=draft.text, token=draft.token, revision=draft.revision)


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
    the token is none. `changes` writes its own files in the same commit.
    Whatever it holds saves, problems and all.
    """

    content: str
    token: str | None

    changes: list[FileChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_change_per_path(self) -> Self:
        paths = [change.path for change in self.changes]
        if len(set(paths)) != len(paths):
            raise ValueError("Each file can appear only once in a save.")
        return self


class VersionContent(BaseModel):
    """A workflow's `workflow.yaml` at one version."""

    content: str


class CreateVersion(BaseModel):
    """A name to freeze the saved draft under, `v` and a whole number from
    1 with no leading zero, such as `v1` or `v10`, and the token
    the caller saved it with, so the version is of that save; with none, of
    whatever is saved now. `revision` also checks that the files have not moved.
    """

    version: str
    token: str | None = None
    revision: str | None = None


class Version(BaseModel):
    version: str


class CheckDefinition(BaseModel):
    """A `workflow.yaml` to check as a version would be, writing nothing.
    `owner` and `name`, when both are given, name the workflow this text is
    a draft of, so a draft that would hold that workflow is refused.
    """

    content: str
    owner: str | None = None
    name: str | None = None


class DefinitionProblem(BaseModel):
    """One problem: its YAML path in `workflow.yaml`, `steps[1].with.binary`,
    and what is wrong there. The path is empty for the file as a whole.
    `step` is the flat step a problem inside a box belongs to, when the path
    can only name the box; none otherwise.
    """

    path: str
    message: str
    step: str | None = None


class Checked(BaseModel):
    """Every problem a version would be refused for; none means it would be
    made.
    """

    problems: list[DefinitionProblem]


class BoxInput(BaseModel):
    """One input of a run workflow drawn as a box."""

    name: str
    type: str
    options: list[str] | None
    optional: bool
    title: str | None
    unit: str | None

    @classmethod
    def of(cls, found: ForgeBoxInput) -> Self:
        return cls(
            name=found.name,
            type=found.type,
            options=None if found.options is None else list(found.options),
            optional=found.optional,
            title=found.title,
            unit=found.unit,
        )


class BoxOutput(BaseModel):
    """One output of a run workflow drawn as a box. `type` and a number's
    meaning are null while the port is not known. A port carries no title
    and no unit.
    """

    name: str
    type: str | None
    title: str | None
    unit: str | None
    better: Better | None
    at_least: Exact | None
    at_most: Exact | None

    @classmethod
    def of(cls, found: ForgeBoxOutput) -> Self:
        return cls(
            name=found.name,
            type=found.type,
            title=found.title,
            unit=found.unit,
            better=found.better,
            at_least=found.at_least,
            at_most=found.at_most,
        )


class WorkflowBox(BaseModel):
    """A workflow version as a box. `run` is false for a workflow of the
    test format, and then both lists are empty. `description` is what the
    workflow says it does, or null when it says nothing.
    """

    run: bool
    inputs: list[BoxInput]
    outputs: list[BoxOutput]
    newer_version: str | None
    description: str | None

    @classmethod
    def of(cls, found: ForgeBox) -> Self:
        return cls(
            run=found.run,
            inputs=[BoxInput.of(item) for item in found.inputs],
            outputs=[BoxOutput.of(item) for item in found.outputs],
            newer_version=found.newer_version,
            description=found.description,
        )


class SetVisibility(BaseModel):
    """Private, shared or public. Private and public empty the list of
    readers; shared keeps it.
    """

    visibility: Visibility


class Reader(BaseModel):
    """Someone a workflow is shared with, by their username."""

    username: str


class PrimitivePort(BaseModel):
    """One port: its type, the options an enum takes, the names a
    `named_files` port's files must have, whether it may be left out, on an
    input whether the primitive runs what arrives there and whether it
    keeps it from the program it runs, on a `number` output which way is
    `better` and the bounds every value lies within, both inclusive, on a
    `programs` port the `inputs` each program takes and the `outputs` the
    primitive gives of each, and a sentence saying what it takes or gives
    back, none when the primitive gives none. The `outcome` port may carry
    `outcomes`: each outcome the step can report, in the declaration's
    order, with a line saying when (`accepted`: "the source compiles"), for
    the step's drawer to say what it reports; none when the primitive does
    not say, and on every other port.
    """

    type: str
    options: list[str] | None
    optional: bool
    runs: bool | None
    secret: bool
    description: str | None = None
    outcomes: dict[str, str] | None = None
    names: list[str] | None = None
    better: Better | None = None
    at_least: Exact | None = None
    at_most: Exact | None = None
    inputs: dict[str, PrimitivePort] | None = None
    outputs: dict[str, PrimitivePort] | None = None

    @classmethod
    def of(cls, port: Port) -> Self:
        return cls(
            type=port.type.value,
            options=list(port.options) if port.options is not None else None,
            optional=port.optional,
            runs=port.runs,
            secret=port.secret,
            description=port.description,
            outcomes=dict(port.outcomes) if port.outcomes is not None else None,
            names=list(port.names) if port.names is not None else None,
            better=port.better,
            at_least=port.at_least,
            at_most=port.at_most,
            inputs=_ports(port.inputs),
            outputs=_ports(port.outputs),
        )


def _ports(ports: dict[str, Port] | None) -> dict[str, PrimitivePort] | None:
    if ports is None:
        return None
    return {name: PrimitivePort.of(port) for name, port in ports.items()}


class LimitSource(BaseModel):
    """A container limit raised to `n * scale + add` when that is more,
    `scale` and `add` exactly as the declaration writes them, `n` read
    from exactly one of `input`, a number input; `sum`, the sum of a number
    input over every program of a programs port, `<port>.<input>`; and
    `max`, the largest of one. The other two are null.
    """

    input: str | None = None
    sum: str | None = None
    max: str | None = None
    scale: Exact
    add: Exact

    @classmethod
    def of(cls, source: LimitFrom) -> Self:
        match source:
            case FromInput():
                return cls(input=source.input, scale=source.scale, add=source.add)
            case FromSum():
                return cls(sum=source.sum, scale=source.scale, add=source.add)
            case FromMax():
                return cls(max=source.max, scale=source.scale, add=source.add)


Limit = Literal["time_ms", "cpu_ms", "memory_mb", "pids", "output_mb", "gpus"]


class PrimitiveForm(BaseModel):
    """One way to use a primitive that declares several. The editor shows
    `description`; the ports and limits are what a step of this form gives
    and takes. Nothing here is the step's choice of form: the save picks it.
    """

    description: str | None = None
    outputs_from: Literal["manifest", "programs"] | None = None
    limits: dict[Limit, int] = Field(default_factory=dict)
    limits_from: dict[Limit, LimitSource] = Field(default_factory=dict)
    inputs: dict[str, PrimitivePort] = Field(default_factory=dict)
    outputs: dict[str, PrimitivePort] = Field(default_factory=dict)

    @classmethod
    def of(cls, form: Any) -> Self:
        return cls(
            description=form.description,
            outputs_from=form.outputs_from,
            limits=form.limits.as_mapping(),
            limits_from={
                limit: LimitSource.of(source) for limit, source in form.limits_from.items()
            },
            inputs={name: PrimitivePort.of(port) for name, port in form.inputs.items()},
            outputs={name: PrimitivePort.of(port) for name, port in form.outputs.items()},
        )


class Primitive(BaseModel):
    """One version of a primitive, `ref` being what a step's `use:` names.
    Its declaration is in `title` and `description`, what the editor shows
    of it, and in `batch`, `network`, `limits`, `limits_from`, `inputs` and
    `outputs`, or in `forms` when the primitive declares several and those
    four stay empty; a version in a format the platform no longer reads has
    none of them and `problem` instead, so no step uses it.
    """

    ref: str
    name: str
    version: str
    title: str | None = None
    description: str | None = None
    batch: bool = False
    network: bool = False
    limits: dict[Limit, int] = Field(default_factory=dict)
    limits_from: dict[Limit, LimitSource] = Field(default_factory=dict)
    inputs: dict[str, PrimitivePort] = Field(default_factory=dict)
    outputs: dict[str, PrimitivePort] = Field(default_factory=dict)
    forms: dict[str, PrimitiveForm] = Field(default_factory=dict)
    problem: str | None = None

    @classmethod
    def of(cls, found: PrimitiveVersion) -> Self:
        declared = found.declaration
        if declared is None:
            return cls(ref=found.ref, name=found.name, version=found.version, problem=found.problem)
        if declared.forms:
            limits = {}
            limits_from = {}
            inputs = {}
            outputs = {}
        else:
            assert declared.limits is not None
            limits = declared.limits.as_mapping()
            limits_from = {
                limit: LimitSource.of(source) for limit, source in declared.limits_from.items()
            }
            inputs = {name: PrimitivePort.of(port) for name, port in declared.inputs.items()}
            outputs = {name: PrimitivePort.of(port) for name, port in declared.outputs.items()}
        return cls(
            ref=found.ref,
            name=found.name,
            version=found.version,
            title=declared.title,
            description=declared.description,
            batch=declared.batch,
            network=declared.network,
            limits=limits,
            limits_from=limits_from,
            inputs=inputs,
            outputs=outputs,
            forms={name: PrimitiveForm.of(form) for name, form in declared.forms.items()},
        )
