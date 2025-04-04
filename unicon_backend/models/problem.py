from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Self, cast

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
import sqlalchemy.orm as sa_orm
from pydantic import model_validator
from sqlmodel import Field, Relationship

from unicon_backend.evaluator.problem import Problem
from unicon_backend.evaluator.tasks import task_classes
from unicon_backend.evaluator.tasks.base import TaskEvalResult, TaskEvalStatus, TaskType
from unicon_backend.evaluator.tasks.programming.base import (
    ProgrammingTask,
    SocketResult,
    Testcase,
    TestcaseResult,
)
from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.lib.helpers import partition
from unicon_backend.models.utils import _timestamp_column
from unicon_backend.schemas.group import UserPublicWithRolesAndGroups
from unicon_backend.schemas.problem import MiniProblemPublic

if TYPE_CHECKING:
    from unicon_backend.evaluator.tasks.base import Task
    from unicon_backend.models.file import FileORM
    from unicon_backend.models.organisation import Project
    from unicon_backend.models.user import UserORM


class ProblemBase(CustomSQLModel):
    id: int
    name: str
    description: str
    project_id: int


class ProblemORM(CustomSQLModel, table=True):
    __tablename__ = "problem"

    id: int = Field(primary_key=True)
    name: str
    description: str
    restricted: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})

    # The time at which the problem is available to users.
    started_at: datetime = Field(sa_column=_timestamp_column(nullable=False, default=False))
    # After ended at: A submission is considered late.
    ended_at: datetime | None = Field(sa_column=_timestamp_column(nullable=True, default=False))
    # After closed at: Submissions are no longer accepted.
    closed_at: datetime | None = Field(sa_column=_timestamp_column(nullable=True, default=False))

    published: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    leaderboard_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})

    project_id: int = Field(foreign_key="project.id")

    tasks: sa_orm.Mapped[list["TaskORM"]] = Relationship(
        back_populates="problem",
        sa_relationship_kwargs={"order_by": "TaskORM.order_index"},
        cascade_delete=True,
    )
    supporting_files: sa_orm.Mapped[list["FileORM"]] = Relationship(
        sa_relationship_kwargs={
            "backref": "problem",
            "primaryjoin": "and_(foreign(ProblemORM.id) == FileORM.parent_id, FileORM.parent_type == 'problem')",
            "single_parent": True,
            "uselist": True,
            "cascade": "all, delete-orphan",
            "viewonly": True,
        },
    )
    project: sa_orm.Mapped["Project"] = Relationship(back_populates="problems")
    submissions: sa_orm.Mapped[list["SubmissionORM"]] = Relationship(
        back_populates="problem", cascade_delete=True
    )

    @classmethod
    def from_problem(cls, problem: "Problem") -> "ProblemORM":
        tasks_orm: list[TaskORM] = [TaskORM.from_task(task) for task in problem.tasks]
        return cls(
            name=problem.name,
            description=problem.description,
            tasks=tasks_orm,
            restricted=problem.restricted,
            leaderboard_enabled=problem.leaderboard_enabled,
            published=problem.published,
            started_at=problem.started_at,
            ended_at=problem.ended_at,
            closed_at=problem.closed_at,
        )

    def to_problem(self) -> "Problem":
        return Problem.model_validate(
            {
                "id": self.id,
                "restricted": self.restricted,
                "leaderboard_enabled": self.leaderboard_enabled,
                "name": self.name,
                "description": self.description,
                "tasks": [task_orm.to_task() for task_orm in self.tasks],
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "closed_at": self.closed_at,
                "published": self.published,
                "supporting_files": self.supporting_files,
            }
        )


class TaskORM(CustomSQLModel, table=True):
    __tablename__ = "task"

    id: int = Field(primary_key=True)

    title: str
    description: str | None = Field(nullable=True, default=None)

    type: TaskType = Field(sa_column=sa.Column(pg.ENUM(TaskType), nullable=False))
    autograde: bool
    other_fields: dict = Field(default_factory=dict, sa_column=sa.Column(pg.JSONB))
    updated_version_id: int | None = Field(nullable=True, default=None)

    order_index: int
    problem_id: int = Field(foreign_key="problem.id", primary_key=True)

    problem: sa_orm.Mapped[ProblemORM] = Relationship(back_populates="tasks")
    task_attempts: sa_orm.Mapped[list["TaskAttemptORM"]] = Relationship(
        back_populates="task", cascade_delete=True
    )

    max_attempts: int | None = Field(nullable=True, default=None)

    min_score_to_pass: int | None = Field(nullable=True, default=None)

    @classmethod
    def from_task(cls, task: "Task") -> "TaskORM":
        def _convert_task_to_orm(
            id: int,
            type: TaskType,
            title: str,
            description: str | None,
            autograde: bool,
            order_index: int,
            max_attempts: int | None,
            min_score_to_pass: int | None,
            **other_fields,
        ):
            return TaskORM(
                id=id,
                type=type,
                title=title,
                description=description,
                autograde=autograde,
                order_index=order_index,
                max_attempts=max_attempts,
                min_score_to_pass=min_score_to_pass,
                other_fields=other_fields,
            )

        return _convert_task_to_orm(**task.model_dump(serialize_as_any=True))

    def to_task(self) -> "Task":
        return task_classes[self.type].model_validate(
            {
                "id": self.id,
                "type": self.type,
                "title": self.title,
                "description": self.description,
                "autograde": self.autograde,
                "order_index": self.order_index,
                "problem_id": self.problem_id,
                "max_attempts": self.max_attempts,
                "updated_version_id": self.updated_version_id,
                "min_score_to_pass": self.min_score_to_pass,
                **self.other_fields,
            },
        )


class SubmissionAttemptLink(CustomSQLModel, table=True):
    __tablename__ = "submission_attempt"

    submission_id: int = Field(foreign_key="submission.id", primary_key=True)
    task_attempt_id: int = Field(foreign_key="task_attempt.id", primary_key=True)


class SubmissionBase(CustomSQLModel):
    __tablename__ = "submission"

    id: int = Field(primary_key=True)
    problem_id: int = Field(foreign_key="problem.id")
    user_id: int = Field(foreign_key="user.id")

    submitted_at: datetime | None = Field(sa_column=_timestamp_column(nullable=False, default=True))


class SubmissionORM(SubmissionBase, table=True):
    task_attempts: sa_orm.Mapped[list["TaskAttemptORM"]] = Relationship(
        link_model=SubmissionAttemptLink,
        back_populates="submissions",
    )
    problem: sa_orm.Mapped[ProblemORM] = Relationship(back_populates="submissions")
    user: sa_orm.Mapped["UserORM"] = Relationship(back_populates="submissions")


class SubmissionPublic(SubmissionBase):
    task_attempts: list["TaskAttemptPublic"]
    user: UserPublicWithRolesAndGroups
    problem: MiniProblemPublic


class TaskAttemptBase(CustomSQLModel):
    id: int
    user_id: int
    task_id: int
    task_type: TaskType
    other_fields: dict


class TaskAttemptPublic(TaskAttemptBase):
    task_results: list["TaskResult"]
    task: "TaskORM"
    has_private_failure: bool = Field(default=False)


class TaskAttemptResult(TaskAttemptBase):
    task_results: list["TaskResult"]
    has_private_failure: bool = Field(default=False)


class TaskAttemptORM(CustomSQLModel, table=True):
    __tablename__ = "task_attempt"
    __table_args__ = (
        sa.ForeignKeyConstraint(["task_id", "problem_id"], ["task.id", "task.problem_id"]),
    )

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", nullable=False)
    task_id: int
    problem_id: int

    submitted_at: datetime = Field(sa_column=_timestamp_column(nullable=False, default=True))

    task_type: TaskType = Field(sa_column=sa.Column(pg.ENUM(TaskType), nullable=False))

    # TODO: figure out polymorphism to stop abusing JSONB
    other_fields: dict = Field(default_factory=dict, sa_column=sa.Column(pg.JSONB))

    submissions: sa_orm.Mapped[list[SubmissionORM]] = Relationship(
        back_populates="task_attempts",
        link_model=SubmissionAttemptLink,
    )
    task: sa_orm.Mapped[TaskORM] = Relationship(back_populates="task_attempts")
    task_results: sa_orm.Mapped[list["TaskResultORM"]] = Relationship(
        back_populates="task_attempt", cascade_delete=True
    )
    user: sa_orm.Mapped["UserORM"] = Relationship(back_populates="task_attempts")

    def clone(self, new_task_id: int) -> "TaskAttemptORM":
        return TaskAttemptORM(
            user_id=self.user_id,
            task_id=new_task_id,
            problem_id=self.problem_id,
            submitted_at=self.submitted_at,
            task_type=self.task_type,
            other_fields=self.other_fields,
        )

    def redact_private_fields(self) -> bool:
        """Redacts private testcases and private socket fields from task results.
        Return true if there was a private field/testcase that failed, false otherwise."""
        # We do not redact non-programming tasks for now
        # (as without the expected answer, what would we display on the frontend?)
        # Revisit this line if we want to hide the answer (and have plans for when to show it again after a submission.)
        if self.task_type != TaskType.PROGRAMMING:
            return False

        task = cast(ProgrammingTask, self.task.to_task())
        testcase_id_to_testcase_map = {testcase.id: testcase for testcase in task.testcases}
        filtered_results: list[TaskResultORM] = []

        has_failure = False
        for result in self.task_results:
            # if pending, there is nothing to redact.
            if result.status == TaskEvalStatus.PENDING:
                filtered_results.append(result)
                continue

            parsedResult = ProgrammingTaskResult.model_validate(result)
            if not parsedResult.result:
                filtered_results.append(result)
                continue

            # First pass: if the entire testcase is private, redact the entire result
            private_tcs, public_tcs = partition(
                lambda tc: testcase_id_to_testcase_map[tc.id].is_private,
                parsedResult.result or [],
            )
            if any(
                any(not result.correct for result in (testcaseResult.results or []))
                for testcaseResult in private_tcs
            ):
                has_failure = True

            parsedResult.result = cast(list[TestcaseResult], public_tcs)

            # Second pass: if the output socket is private, redact the output socket
            def _is_private_output_socket(socket: SocketResult, testcase: Testcase) -> bool:
                output_node = testcase.output_step
                output_socket = next(
                    (
                        output_socket
                        for output_socket in output_node.inputs
                        if output_socket.id == socket.id
                    ),
                    None,
                )
                return not output_socket.public if output_socket else False

            for testcaseResult in parsedResult.result:
                testcase = testcase_id_to_testcase_map[testcaseResult.id]
                if not testcaseResult.results:
                    continue
                private_sockets, public_sockets = partition(
                    partial(
                        lambda socketResult, testcase: _is_private_output_socket(
                            socketResult, testcase
                        ),
                        testcase=testcase,
                    ),
                    testcaseResult.results,
                )
                if any(not socketResult.correct for socketResult in private_sockets):
                    has_failure = True

                testcaseResult.results = cast(list[SocketResult], public_sockets)

            # Redact stdout and stderr.
            for testcaseResult in parsedResult.result:
                testcaseResult.stdout = ""
                testcaseResult.stderr = ""

            result.result = parsedResult.result
        return has_failure


class TaskResultBase(CustomSQLModel):
    __tablename__ = "task_result"

    id: int = Field(primary_key=True)

    task_attempt_id: int = Field(foreign_key="task_attempt.id")
    task_type: TaskType = Field(sa_column=sa.Column(pg.ENUM(TaskType), nullable=False))

    started_at: datetime = Field(sa_column=_timestamp_column(nullable=False, default=True))
    completed_at: datetime | None = Field(sa_column=_timestamp_column(nullable=True, default=False))

    job_id: str | None = Field(nullable=True)

    status: TaskEvalStatus = Field(sa_column=sa.Column(pg.ENUM(TaskEvalStatus), nullable=False))
    # TODO: Handle non-JSON result types for non-programming tasks
    result: Any = Field(default_factory=dict, sa_column=sa.Column(pg.JSONB))
    error: str | None = Field(nullable=True)


class TaskResultPublic(TaskResultBase):
    pass


class TaskResultORM(TaskResultBase, table=True):
    __tablename__ = "task_result"

    task_attempt: sa_orm.Mapped[TaskAttemptORM] = Relationship(back_populates="task_results")

    @classmethod
    def from_task_eval_result(
        cls, eval_result: "TaskEvalResult", attempt_id: int, task_type: TaskType
    ) -> "TaskResultORM":
        is_pending = eval_result.status == TaskEvalStatus.PENDING
        started_at = sa.func.now()
        completed_at = None if is_pending else sa.func.now()
        result = (
            eval_result.result.model_dump(mode="json")
            if not is_pending and eval_result.result
            else None
        )
        # NOTE: We assume that the job_id is always the result of a pending evaluation
        job_id = eval_result.result if is_pending else None

        return cls(
            task_attempt_id=attempt_id,
            task_type=task_type,
            started_at=started_at,
            completed_at=completed_at,
            status=eval_result.status,
            error=eval_result.error,
            result=result,
            job_id=job_id,
        )

    def clone(self):
        return TaskResultORM(
            task_type=self.task_type,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=self.status,
            error=self.error,
            result=self.result,
            job_id=self.job_id,
        )


"""
Below classes are for parsing/validating task results with pydantic
"""


class MultipleChoiceTaskResult(TaskResultPublic):
    result: bool

    @model_validator(mode="after")
    def validate_task_type(self) -> Self:
        if not self.task_type == TaskType.MULTIPLE_CHOICE:
            raise ValueError(f"Task type must be {TaskType.MULTIPLE_CHOICE}")
        return self


class MultipleResponseTaskResultType(CustomSQLModel):
    correct_choices: list[str]
    incorrect_choices: list[str]
    num_choices: int


class MultipleResponseTaskResult(TaskResultPublic):
    result: MultipleResponseTaskResultType | None

    @model_validator(mode="after")
    def validate_task_type(self) -> Self:
        if not self.task_type == TaskType.MULTIPLE_RESPONSE:
            raise ValueError(f"Task type must be {TaskType.MULTIPLE_RESPONSE}")
        return self


class ProgrammingTaskResult(TaskResultPublic):
    result: list[TestcaseResult] | None  # TODO: handle this one properly

    @model_validator(mode="after")
    def validate_task_type(self) -> Self:
        if not self.task_type == TaskType.PROGRAMMING:
            raise ValueError(f"Task type must be {TaskType.PROGRAMMING}")
        return self


class ShortAnswerTaskResult(TaskResultPublic):
    result: str | None  # TODO: check this one

    @model_validator(mode="after")
    def validate_task_type(self) -> Self:
        if not self.task_type == TaskType.SHORT_ANSWER:
            raise ValueError(f"Task type must be {TaskType.SHORT_ANSWER}")
        return self


type TaskResult = (
    MultipleChoiceTaskResult
    | MultipleResponseTaskResult
    | ProgrammingTaskResult
    | ShortAnswerTaskResult
)
