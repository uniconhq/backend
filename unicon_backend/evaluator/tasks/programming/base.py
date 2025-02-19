from functools import cached_property
from logging import getLogger
from operator import attrgetter
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, RootModel, model_validator

from unicon_backend.evaluator.tasks import Task, TaskEvalResult, TaskEvalStatus, TaskType
from unicon_backend.evaluator.tasks.programming.artifact import File, PrimitiveData
from unicon_backend.evaluator.tasks.programming.security import mpi_sandbox
from unicon_backend.evaluator.tasks.programming.steps import (
    ComputeGraph,
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
from unicon_backend.workers.publisher import task_publisher

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


class ProgrammingTask(Task[list[RequiredInput], JobId]):
    type: Literal[TaskType.PROGRAMMING]
    environment: ComputeContext
    # Required inputs are files submitted by the normal user. Template files are shown here.
    required_inputs: list[RequiredInput]
    testcases: list[Testcase]

    def run(self, user_inputs: list[RequiredInput]) -> TaskEvalResult[JobId]:
        # Check if all required inputs are provided
        for required_input in self.required_inputs:
            if not any(required_input.id == user_input.id for user_input in user_inputs):
                raise ValueError(f"Required input {required_input.id} not provided")

        runner_programs: list[RunnerProgram] = []
        for testcase in sorted(self.testcases, key=attrgetter("order_index")):
            testcase.attach_user_inputs(user_inputs)
            assembled_program = mpi_sandbox(testcase.run())

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
                            File(path="__entrypoint.py", content=assembled_program.code)
                        ),
                    ],
                )
            )

        runner_job = RunnerJob.create(runner_programs, self.environment)
        task_publisher.publish(runner_job.model_dump_json(serialize_as_any=True))

        return TaskEvalResult(task_id=self.id, status=TaskEvalStatus.PENDING, result=runner_job.id)

    def validate_user_input(self, user_input: Any) -> list[RequiredInput]:
        if type(user_input) is not list:
            raise ValueError("User input must be a list of required inputs")

        # insert the path back into the File object
        id_to_path = {
            file.id: file.data.path for file in self.required_inputs if isinstance(file.data, File)
        }
        for required_input in user_input:
            if required_input["id"] in id_to_path:
                required_input["data"]["path"] = id_to_path[required_input["id"]]

        return RootModel[list[RequiredInput]].model_validate(user_input).root
