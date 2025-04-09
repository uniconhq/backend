from functools import cached_property
from logging import getLogger
from operator import attrgetter
from typing import Any, Literal, Self, cast
from uuid import uuid4

from pydantic import BaseModel, Field, RootModel, model_validator

from unicon_backend.evaluator.tasks import Task, TaskEvalResult, TaskEvalStatus, TaskType
from unicon_backend.evaluator.tasks.programming.artifact import File, PrimitiveData
from unicon_backend.evaluator.tasks.programming.harness import gbl_except_hook, mpi_sandbox
from unicon_backend.evaluator.tasks.programming.steps import (
    ComputeGraph,
    InputSocket,
    InputStep,
    OutputStep,
    StepType,
)
from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.runner import (
    ComputeContext,
    JobId,
    ProgramResult,
    RunnerFile,
    RunnerJob,
    RunnerProgram,
)
from unicon_backend.workers.task_publisher import task_publisher

logger = getLogger(__name__)


class SocketResult(CustomSQLModel):
    """
    This class is used to store whether the result of an output socket is right or wrong.
    Note that whether or not to show this information (public) and other variables should be derived from data in Testcase.
    """

    id: str
    value: Any
    correct: bool


class TestcaseResult(ProgramResult):
    results: list[SocketResult] | None = None


class RequiredInput(BaseModel):
    id: str
    data: PrimitiveData | File

    label: str = ""


class Testcase(ComputeGraph):
    id: str
    order_index: int
    is_private: bool = Field(default=False)
    name: str = Field(default="")

    # Awarded score for getting AC on this testcase
    score: int = Field(default=1)

    # if is_private is set to True, the testcase will not be shown to the user
    # so the value of this won't matter
    show_node_graph: bool = Field(default=True)

    @model_validator(mode="after")
    def check_exactly_one_output_step(self) -> Self:
        num_output_steps: int = len([node for node in self.nodes if node.type == StepType.OUTPUT])
        if num_output_steps != 1:
            raise ValueError(f"Expected exactly 1 output step, found {num_output_steps}")
        return self

    @cached_property
    def output_step(self) -> OutputStep:
        return cast(OutputStep, next(node for node in self.nodes if node.type == StepType.OUTPUT))

    def attach_user_inputs(self, user_inputs: list[RequiredInput]) -> None:
        user_input_step: InputStep | None = None
        for node in filter(lambda node: node.type == StepType.INPUT, self.nodes):
            if (input_step := cast(InputStep, node)).is_user:
                user_input_step = input_step

        assert user_input_step is not None

        for user_input_socket in user_input_step.outputs:
            user_input_socket.data = next(
                usr_in.data for usr_in in user_inputs if usr_in.id == user_input_socket.id
            )

    def redact_private_fields(self) -> None:
        if self.show_node_graph:
            input_steps = cast(
                list[InputStep], list(filter(lambda node: node.type == StepType.INPUT, self.nodes))
            )
            # We redact private fields of the input and output sockets and the edges pointing to them.
            private_fields = [
                socket.id for socket in self.output_step.data_in if not socket.public
            ] + [
                socket.id
                for input_step in input_steps
                for socket in input_step.outputs
                if not socket.public
            ]
            self.edges = [
                edge
                for edge in self.edges
                if not (
                    edge.to_node_id == self.output_step.id and edge.to_socket_id in private_fields
                )
            ]

            for input_step in input_steps:
                input_step.redact_private_fields()
        else:
            # We redact all nodes and edges except the output node.
            output_nodes = [self.output_step]
            self.edges = []
            self.nodes = output_nodes

        self.output_step.redact_private_fields()


class ProgrammingTask(Task[list[RequiredInput], JobId]):
    type: Literal[TaskType.PROGRAMMING]
    environment: ComputeContext
    # Required inputs are files submitted by the normal user. Template files are shown here.
    required_inputs: list[RequiredInput]
    testcases: list[Testcase]
    files: list[File]

    @property
    def max_score(self) -> int:
        return sum(testcase.score for testcase in self.testcases)

    def redact_private_fields(self) -> None:
        self.testcases = [testcase for testcase in self.testcases if not testcase.is_private]
        # show files that are public within testcases
        redacted_file_ids: set[str] = set()
        for testcase in self.testcases:
            for node in filter(lambda node: node.type == StepType.INPUT, testcase.nodes):
                for output in node.outputs:
                    if isinstance(output.data, File) and not cast("InputSocket", output).public:
                        redacted_file_ids.add(output.data.id)

        self.files = [file for file in self.files if file.id not in redacted_file_ids]
        for testcase in self.testcases:
            testcase.redact_private_fields()

    def run(self, user_inputs: list[RequiredInput]) -> TaskEvalResult[JobId]:
        # Check if all required inputs are provided
        for required_input in self.required_inputs:
            if not any(required_input.id == user_input.id for user_input in user_inputs):
                raise ValueError(f"Required input {required_input.id} not provided")

        runner_programs: list[RunnerProgram] = []
        for testcase in sorted(self.testcases, key=attrgetter("order_index")):
            testcase.attach_user_inputs(user_inputs)
            assembled_program = gbl_except_hook(mpi_sandbox(testcase.run()))

            logger.debug(f"Assembled Program:\n{assembled_program}")

            graph_files: list[RunnerFile] = []
            for node in filter(lambda node: node.type == StepType.INPUT, testcase.nodes):
                graph_files.extend(
                    RunnerFile.from_file(output.data)
                    for output in node.outputs
                    if isinstance(output.data, File)
                )

            runner_programs.append(
                RunnerProgram(
                    id=testcase.id,
                    order_index=testcase.order_index,
                    entrypoint="__entrypoint.py",
                    # TODO: instead of always passing in user_input, we can refactor in the future
                    # to let ComputeGraph derive all the files needed to run the testcase
                    files=[
                        *graph_files,
                        RunnerFile.from_file(
                            File(
                                id=str(uuid4()),
                                path="__entrypoint.py",
                                content=assembled_program.code,
                                size_limit=0,
                            )
                        ),
                    ],
                )
            )

        runner_job = RunnerJob.create(runner_programs, self.environment)
        task_publisher.publish(runner_job.model_dump_json(serialize_as_any=True))

        return TaskEvalResult(task_id=self.id, status=TaskEvalStatus.PENDING, result=runner_job.id)

    def validate_user_input(self, user_inputs: Any) -> list[RequiredInput]:
        if type(user_inputs) is not list:
            raise ValueError("User input must be a list of required inputs")

        parsed_user_inputs = RootModel[list[RequiredInput]].model_validate(user_inputs).root

        # insert the path back into the File object
        id_to_file = {
            file.id: file.data for file in self.required_inputs if isinstance(file.data, File)
        }

        for user_input in parsed_user_inputs:
            if user_input.id not in id_to_file:
                continue

            if not isinstance(user_input.data, File):
                raise ValueError(f"Expected File for input {user_input.id}")

            user_file = user_input.data
            task_file = id_to_file[user_input.id]
            user_file.path = task_file.path
            user_file.id = task_file.id

            # if the size_limit != 0, enforce it
            if task_file.size_limit and task_file.size_limit < user_input.data.size_in_kb:
                raise ValueError(
                    f"File {task_file.path} exceeds size limit. ({task_file.size_limit} KB)"
                )

        return parsed_user_inputs
