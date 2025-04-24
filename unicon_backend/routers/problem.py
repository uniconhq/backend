from datetime import UTC, datetime
from http import HTTPStatus
from itertools import groupby
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import RootModel
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, func, select

from unicon_backend.constants import MINIO_BUCKET
from unicon_backend.dependencies.auth import get_current_user
from unicon_backend.dependencies.common import get_db_session
from unicon_backend.dependencies.problem import (
    get_problem_by_id,
    get_task_by_id,
    get_task_versions,
    is_task_attempt_invalidated,
    parse_python_functions_from_file_content,
)
from unicon_backend.evaluator.problem import Problem, UserInput
from unicon_backend.evaluator.tasks.base import Task, TaskEvalResult, TaskEvalStatus, TaskType
from unicon_backend.evaluator.tasks.programming.base import ProgrammingTask, TestcaseResult
from unicon_backend.evaluator.tasks.programming.visitors import ParsedFunction
from unicon_backend.lib.file import delete_file, upload_fastapi_file
from unicon_backend.lib.permissions import (
    permission_check,
    permission_create,
    permission_delete,
    permission_list_for_subject,
    permission_update,
)
from unicon_backend.models import (
    ProblemORM,
    SubmissionORM,
    TaskResultORM,
)
from unicon_backend.models.file import SGT, FileORM
from unicon_backend.models.links import GroupMember
from unicon_backend.models.problem import (
    SubmissionPublic,
    TaskAttemptORM,
    TaskAttemptPublic,
    TaskAttemptResult,
    TaskORM,
)
from unicon_backend.models.user import UserORM
from unicon_backend.runner import PythonVersion, Status
from unicon_backend.schemas.problem import (
    Leaderboard,
    LeaderboardUser,
    LeaderboardUserTaskResult,
    ParseRequest,
    ProblemPublic,
    ProblemUpdate,
    TaskUpdate,
)
from unicon_backend.workers.task_publisher import task_publisher

router = APIRouter(prefix="/problems", tags=["problem"], dependencies=[Depends(get_current_user)])


def run_programming_task(task: ProgrammingTask, input: Any) -> TaskEvalResult:
    # NOTE: It is safe to ignore type checking here because the type of task is determined by the "type" field
    # As long as the "type" field is set correctly, the type of task will be inferred correctly
    runner_job = task.create_runner_job(task.validate_user_input(input))  # type: ignore
    task_publisher.publish_runner_job(runner_job)
    return TaskEvalResult(task_id=task.id, status=TaskEvalStatus.PENDING_PUSH, result=runner_job.id)


def run_as_programming_task(task: Task, input: Any) -> TaskEvalResult:
    programming_task = ProgrammingTask.model_validate(task.model_dump())
    return run_programming_task(programming_task, input)


@router.get("/python-versions", response_model=list[str], summary="Get available Python versions")
def get_python_versions():
    return PythonVersion.list()


@router.get("/{id}", summary="Get a problem definition")
def get_problem(
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
) -> ProblemPublic:
    permissions = permission_list_for_subject(problem_orm, user)
    if not permission_check(problem_orm, "view", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="User does not have permission to view problem"
        )

    problem = problem_orm.to_problem()
    if not permissions["view_hidden_details"]:
        # NOTE: if we ever change this to be related to a database orm,
        # we need to ensure that the redacted fields are not saved to the database.
        # Set autoflush of the db_session to false if we ever do that.
        problem.redact_private_fields()
    return ProblemPublic.model_validate(problem, update=permissions)


@router.get("/{id}/tasks/{task_id}", response_model=Task)
def get_problem_task(
    id: int,
    task_id: int,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
):
    permissions = permission_list_for_subject(problem_orm, user)
    if not permission_check(problem_orm, "view", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="User does not have permission to view problem"
        )

    task = get_task_by_id(task_id, id, db_session)
    task_dto = task.to_task()

    if not task:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Task not found")

    if not permissions["view_hidden_details"]:
        # NOTE: Do not persist this change to the database!
        task_dto.redact_private_fields()

    return task_dto


@router.get(
    "/{id}/tasks/{task_id}/versions",
    response_model=list[int],
    summary="Get task versions from before this task",
)
def get_problem_task_versions(
    id: int,
    task_id: int,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
):
    if not permission_check(problem_orm, "view", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="User does not have permission to view problem"
        )

    return get_task_versions(task_id, id, db_session)


def calculate_score(task: ProgrammingTask, attempt: TaskAttemptORM):
    result = attempt.task_results[-1]
    id_to_testcase = {testcase.id: testcase for testcase in task.testcases}
    score = 0
    testcase_results = RootModel[list[TestcaseResult]].model_validate(result.result).root
    for testcase_result in testcase_results:
        if testcase_result.status == Status.OK:
            testcase_score = id_to_testcase[testcase_result.id].score
            score += testcase_score
    return score


@router.get(
    "/{id}/leaderboard",
    summary="Get leaderboard for a problem",
    response_model=Leaderboard,
)
def get_problem_leaderboard(
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(problem_orm, "view", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to view problem",
        )

    if not problem_orm.leaderboard_enabled:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Leaderboard is not enabled for this problem",
        )

    # 1. Query all attempts
    tasks = problem_orm.tasks
    task_ids = [task.id for task in tasks if task.type == TaskType.PROGRAMMING]
    task_id_to_programming_task = {
        task.id: cast("ProgrammingTask", task.to_task())
        for task in tasks
        if task.type == TaskType.PROGRAMMING
    }
    task_attempts = db_session.scalars(
        select(TaskAttemptORM)
        .where(TaskAttemptORM.problem_id == problem_orm.id)
        .where(col(TaskAttemptORM.task_id).in_(task_ids))
        .options(selectinload(TaskAttemptORM.task_results), selectinload(TaskAttemptORM.user))
        .order_by(col(TaskAttemptORM.user_id), col(TaskAttemptORM.task_id), col(TaskAttemptORM.id))
    ).all()

    # 2. Tally score per user per task (score, attempts, datetime of last included attempt)
    leaderboard: list[LeaderboardUser] = []
    for user_id, user_attempts_iter in groupby(task_attempts, lambda attempt: attempt.user_id):
        user_result: list[LeaderboardUserTaskResult] = []
        user_attempts = list(user_attempts_iter)
        username = user_attempts[0].user.username
        for task_id, task_attempts_iter in groupby(user_attempts, lambda attempt: attempt.task_id):
            task_attempts = list(task_attempts_iter)
            score, attempts, date = None, 0, None
            task = task_id_to_programming_task[task_id]
            for index, attempt in enumerate(task_attempts):
                if not attempt.task_results or all(
                    result.status != "SUCCESS" for result in attempt.task_results
                ):
                    continue

                attempt_score = calculate_score(task, attempt)
                # Similar to codeforces, attempts that are after the attempt with maximum score do not count to the attempt total.
                if score is None or attempt_score > score:
                    score = attempt_score
                    attempts = index + 1
                    date = attempt.submitted_at
            score = score if score is not None else 0

            user_result.append(
                LeaderboardUserTaskResult(
                    task_id=task_id,
                    score=score,
                    attempts=attempts,
                    latest_attempt_date=date,
                    passed=(
                        task.min_score_to_pass
                        if task.min_score_to_pass is not None
                        else task.max_score
                    )
                    <= score,
                )
            )
        missing_task_ids = set(task_id_to_programming_task.keys()) - set(
            task_attempt.task_id for task_attempt in user_attempts
        )
        for task_id in missing_task_ids:
            user_result.append(
                LeaderboardUserTaskResult(
                    task_id=task_id,
                    score=0,
                    attempts=0,
                    passed=False,
                )
            )

        user_result.sort(key=lambda result: result.task_id)

        leaderboard.append(
            LeaderboardUser(
                id=user_id,
                username=username,
                task_results=user_result,
                solved=sum(result.passed for result in user_result),
            )
        )

    # 3. Sort by total tasks solved, total points earned, then by datetime, then username
    min_datetime = datetime.min.replace(tzinfo=UTC).astimezone(SGT)
    leaderboard.sort(
        key=lambda user_result: (
            -user_result.solved,
            -sum(result.score for result in user_result.task_results),
            max(
                (result.latest_attempt_date or min_datetime for result in user_result.task_results),
                default=min_datetime,
            ),
            user_result.username,
        ),
    )

    return Leaderboard(tasks=list(task_id_to_programming_task.values()), results=leaderboard)


@router.post("/{id}/tasks", summary="Add a task to a problem")
def add_task_to_problem(
    task: Task,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to add task to problem",
        )

    new_task_id = (
        db_session.scalar(select(func.max(TaskORM.id)).where(TaskORM.problem_id == problem_orm.id))
        or 0
    ) + 1
    taskOrm = TaskORM.from_task(task)
    taskOrm.id = new_task_id
    taskOrm.order_index = max((task.order_index for task in problem_orm.tasks), default=-1) + 1

    problem_orm.tasks.append(taskOrm)
    db_session.add(problem_orm)
    db_session.commit()
    return


@router.put("/{id}/tasks/{task_id}", summary="Update a task in a problem")
def update_task(
    data: TaskUpdate,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
    task_id: int,
):
    # Only allow a task update if:
    # 1. The user has edit permission on the problem
    # 2. The task exists and is of the same task type.
    if not permission_check(problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to add task to problem",
        )

    old_task_orm = next((task for task in problem_orm.tasks if task.id == task_id), None)
    if not old_task_orm or old_task_orm.updated_version_id is not None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Task not found in problem definition",
        )

    if old_task_orm.type != data.task.type:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Task type cannot be changed",
        )

    new_task_orm = TaskORM.from_task(data.task)
    new_task_orm.id = max((task.id for task in problem_orm.tasks), default=-1) + 1
    new_task_orm.problem_id = old_task_orm.problem_id

    db_session.add(new_task_orm)
    db_session.commit()
    db_session.refresh(new_task_orm)

    # Ensure the old task is "soft deleted" by updating the updated_version_id to the new task id
    # Then, duplicate the task attempts to the new task
    old_task_orm.updated_version_id = new_task_orm.id
    new_task_orm.order_index = old_task_orm.order_index

    # If code below this throws an error, ensure that the old task will at least be hidden
    db_session.add(old_task_orm)
    db_session.commit()
    db_session.refresh(old_task_orm)

    if data.rerun:
        new_task_orm.triggered_rerun = True
        new_task_orm.task_attempts = [
            task_attempt.clone(new_task_orm.id)
            # NOTE: Ensure that the order of task attempts is preserved
            for task_attempt in sorted(old_task_orm.task_attempts, key=lambda attempt: attempt.id)
        ]
        for task_attempt in new_task_orm.task_attempts:
            user_input = task_attempt.other_fields.get("user_input")
            task_result: TaskEvalResult = run_as_programming_task(
                new_task_orm.to_task(), user_input
            )
            task_result_orm: TaskResultORM = TaskResultORM.from_task_eval_result(
                task_result, attempt_id=task_attempt.id, task_type=new_task_orm.type
            )
            task_attempt.task_results.append(task_result_orm)
            db_session.add(task_result_orm)

    # Unmark the old task attempts as submission
    for task_attempt in old_task_orm.task_attempts:
        task_attempt.marked_for_submission = False
        task_attempt.submissions.clear()
        db_session.add(task_attempt)

    db_session.add(new_task_orm)
    db_session.commit()


@router.patch("/{id}", summary="Update a problem definition")
def update_problem(
    existing_problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    new_problem: ProblemUpdate,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
) -> Problem:
    if not permission_check(existing_problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to update problem",
        )

    old_copy = existing_problem_orm.model_copy()

    existing_problem_orm.name = new_problem.name
    existing_problem_orm.description = new_problem.description
    existing_problem_orm.published = new_problem.published
    existing_problem_orm.restricted = new_problem.restricted
    existing_problem_orm.started_at = new_problem.started_at
    existing_problem_orm.ended_at = new_problem.ended_at
    existing_problem_orm.closed_at = new_problem.closed_at
    existing_problem_orm.leaderboard_enabled = new_problem.leaderboard_enabled

    # Update task order
    if not set(task_order.id for task_order in new_problem.task_order) == set(
        task.id for task in existing_problem_orm.tasks
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Task order does not match problem tasks",
        )

    map_task_id_to_order_index = {
        task_order.id: task_order.order_index for task_order in new_problem.task_order
    }

    for task in existing_problem_orm.tasks:
        task.order_index = map_task_id_to_order_index[task.id]
        db_session.add(task)

    db_session.add(existing_problem_orm)
    db_session.commit()
    db_session.refresh(existing_problem_orm)

    permission_update(old_copy, existing_problem_orm)

    return existing_problem_orm.to_problem()


@router.post("/{id}/files")
async def upload_files_to_problem(
    db_session: Annotated[Session, Depends(get_db_session)],
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    files: list[UploadFile],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to upload files to problem",
        )

    file_models: list[FileORM] = []
    for file in files:
        key = await upload_fastapi_file(file)
        file_models.append(
            FileORM(
                path=file.filename,
                on_minio=True,
                key=key,
                content="",
                parent_type="problem",
                parent_id=problem_orm.id,
            )
        )

    db_session.add_all(file_models)
    db_session.commit()
    for file_model in file_models:
        permission_create(file_model)


@router.delete("/{id}/files/{file_id}")
def delete_file_from_problem(
    file_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to upload files to problem",
        )

    file = db_session.scalar(select(FileORM).where(FileORM.id == file_id))
    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")

    delete_file(MINIO_BUCKET, file.key)

    db_session.delete(file)
    db_session.commit()
    permission_delete(file)
    return


@router.delete("/{id}/tasks/{task_id}", summary="Delete a task from a problem")
def delete_task(
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
    task_id: int,
):
    if not permission_check(problem_orm, "edit", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to delete task from problem",
        )

    task = next((task for task in problem_orm.tasks if task.id == task_id), None)
    if task is None or task.updated_version_id is not None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Task not found in problem definition"
        )

    db_session.delete(task)
    db_session.commit()
    return


@router.post(
    "/{id}/tasks/{task_id}", summary="Submit a task attempt", response_model=TaskAttemptPublic
)
def submit_problem_task_attempt(
    user_input: UserInput,
    task_id: int,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    if not permission_check(problem_orm, "make_submission", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to submit task attempt",
        )

    task = next((task for task in problem_orm.tasks if task.id == task_id), None)
    if not task:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Task not found in problem definition"
        )

    can_submit_without_limit = permission_check(problem_orm, "make_submission_without_limit", user)
    if not can_submit_without_limit:
        attempt_count_query = (
            select(func.count())
            .select_from(TaskAttemptORM)
            .where(
                (TaskAttemptORM.user_id == user.id)
                & (TaskAttemptORM.problem_id == problem_orm.id)
                & (TaskAttemptORM.task_id == task_id)
            )
        )
        attempt_count = db_session.scalar(attempt_count_query) or 0
        if task.max_attempts is not None and attempt_count >= task.max_attempts:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="User has reached the maximum number of attempts for this task",
            )

    problem: Problem = problem_orm.to_problem()
    if task_id not in problem.task_index:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Task not found in problem definition"
        )

    task_type = problem.task_index[task_id].type
    # TODO: Retrieve expected answers (https://github.com/uniconhq/unicon-backend/issues/12)
    task_attempt_orm: TaskAttemptORM = TaskAttemptORM(
        user_id=user.id,
        problem_id=problem_orm.id,
        task_id=task_id,
        task_type=task_type,
        other_fields={"user_input": user_input.value},
    )

    try:
        task_result: TaskEvalResult = run_as_programming_task(task.to_task(), user_input.value)
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(e)) from e

    task_result_orm: TaskResultORM = TaskResultORM.from_task_eval_result(
        task_result, attempt_id=task_attempt_orm.id, task_type=task_type
    )
    task_attempt_orm.task_results.append(task_result_orm)

    db_session.add_all([task_result_orm, task_attempt_orm])
    db_session.commit()
    db_session.refresh(task_attempt_orm)

    return task_attempt_orm


def _get_task_attempt(attempt_id: int, db_session: Session, user: UserORM) -> TaskAttemptORM:
    task_attempt = db_session.scalar(
        select(TaskAttemptORM)
        .where(TaskAttemptORM.id == attempt_id)
        .options(
            selectinload(TaskAttemptORM.task_results),
            selectinload(TaskAttemptORM.task).selectinload(TaskORM.problem),
        )
    )

    if not task_attempt:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Task attempt not found in database"
        )

    # TODO: proper permission check
    if task_attempt.user_id != user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to access task attempt",
        )

    return task_attempt


@router.post("/attempts/{attempt_id}/submit", summary="Mark a task attempt for submission")
def submit_task_attempt(
    attempt_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    task_attempt = _get_task_attempt(attempt_id, db_session, user)
    task_attempt.marked_for_submission = True
    # Check if there's a task attempt that is currently marked for submission
    existing_attempts = db_session.scalars(
        select(TaskAttemptORM)
        .where(TaskAttemptORM.id != task_attempt.id)
        .where(TaskAttemptORM.task_id == task_attempt.task_id)
        .where(TaskAttemptORM.user_id == user.id)
        .where(TaskAttemptORM.marked_for_submission == True)
    ).all()

    existing_attempt_ids = []
    if existing_attempts:
        for existing_attempt in existing_attempts:
            existing_attempt.marked_for_submission = False
            existing_attempt_ids.append(existing_attempt.id)
            db_session.add(existing_attempt)

    # Check if there is a current submission for this problem
    existing_submission = db_session.scalar(
        select(SubmissionORM)
        .where(SubmissionORM.problem_id == task_attempt.problem_id)
        .where(SubmissionORM.user_id == user.id)
    )

    new_submission_orm: SubmissionORM | None = None
    if existing_submission is None:
        # Create a new submission
        new_submission_orm = SubmissionORM(problem_id=task_attempt.problem_id, user_id=user.id)
        task_attempt.submissions.append(new_submission_orm)
        db_session.add(new_submission_orm)
    elif len(existing_submission.task_attempts) == 0:
        task_attempt.submissions.append(existing_submission)
    else:
        existing_submission.task_attempts = [
            *[
                existing_task_attempt
                for existing_task_attempt in existing_submission.task_attempts
                if existing_task_attempt.id not in existing_attempt_ids
            ],
            task_attempt,
        ]
        db_session.add(existing_submission)

    db_session.add(task_attempt)
    db_session.commit()

    if new_submission_orm:
        db_session.refresh(new_submission_orm)
        permission_create(new_submission_orm)


@router.post("/attempts/{attempt_id}/unsubmit", summary="Unmark a task attempt for submission")
def unsubmit_task_attempt(
    attempt_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    task_attempt = _get_task_attempt(attempt_id, db_session, user)
    task_attempt.marked_for_submission = False
    db_session.add(task_attempt)

    # Remove task attempt from submission
    existing_submission = db_session.scalar(
        select(SubmissionORM)
        .where(SubmissionORM.problem_id == task_attempt.problem_id)
        .where(SubmissionORM.user_id == user.id)
    )
    if existing_submission:
        existing_submission.task_attempts = [
            task_attempt
            for task_attempt in existing_submission.task_attempts
            if task_attempt.id != attempt_id
        ]
        db_session.add(existing_submission)

    db_session.commit()


@router.post(
    "/attempts/{attempt_id}/rerun",
    summary="Rerun a task attempt",
)
def rerun_task_attempt(
    attempt_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
):
    task_attempt = _get_task_attempt(attempt_id, db_session, user)

    task_result: TaskEvalResult = run_as_programming_task(
        task_attempt.task.to_task(), task_attempt.other_fields["user_input"]
    )
    task_result_orm: TaskResultORM = TaskResultORM.from_task_eval_result(
        task_result, attempt_id=task_attempt.id, task_type=task_attempt.task_type
    )
    task_attempt.task_results.append(task_result_orm)
    db_session.add(task_result_orm)
    db_session.commit()


@router.get(
    "/{id}/tasks/{task_id}/attempts/{user_id}",
    summary="Get results of all task attempts for a task",
    response_model=list[TaskAttemptResult],
)
def get_problem_task_attempt_results(
    task_id: int,
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    db_session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[UserORM, Depends(get_current_user)],
    user_id: int | None = None,
) -> list[TaskAttemptResult]:
    if (
        user_id is not None
        and user_id != current_user.id
        and not (
            permission_check(problem_orm.project, "view_others_submission", current_user)
            or permission_check(problem_orm, "view_supervised_submission_access", current_user)
        )
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to view others' task attempts",
        )

    task_ids = get_task_versions(task_id, problem_orm.id, db_session)
    task_attempts = db_session.scalars(
        select(TaskAttemptORM)
        .where(TaskAttemptORM.problem_id == problem_orm.id)
        .where(col(TaskAttemptORM.task_id).in_(task_ids))
        .where(TaskAttemptORM.user_id == (current_user.id if user_id is None else user_id))
        .options(selectinload(TaskAttemptORM.task_results))
        .options(selectinload(TaskAttemptORM.task))
        .order_by(col(TaskAttemptORM.id))
    ).all()

    db_session.close()
    can_view_details = permission_check(problem_orm, "view_hidden_details", current_user)
    has_private_failure: list[bool] = []
    with db_session.no_autoflush:
        if not can_view_details:
            for task_attempt in task_attempts:
                has_private_failure.append(task_attempt.redact_private_fields())

        return [
            TaskAttemptResult.model_validate(
                task_attempt,
                update={
                    "has_private_failure": False
                    if can_view_details
                    else has_private_failure[index],
                    "invalidated": is_task_attempt_invalidated(task_attempt, task_ids),
                },
            )
            for index, task_attempt in enumerate(task_attempts)
        ]


@router.post("/{id}/submit", summary="Make a problem submission", response_model=SubmissionPublic)
def make_submission(
    attempt_ids: list[int],
    problem_orm: Annotated[ProblemORM, Depends(get_problem_by_id)],
    user: Annotated[UserORM, Depends(get_current_user)],
    db_session: Annotated[Session, Depends(get_db_session)],
):
    if not permission_check(problem_orm, "make_submission", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to submit task attempt",
        )

    submission_orm = SubmissionORM(problem_id=problem_orm.id, user_id=user.id)

    _base_query = select(TaskAttemptORM).where(
        (TaskAttemptORM.user_id == user.id) & (TaskAttemptORM.problem_id == problem_orm.id)
    )
    if attempt_ids:
        query = _base_query.where(col(TaskAttemptORM.id).in_(attempt_ids))
    else:
        # Subquery to get the latest attempt ID for each task
        latest_attempts_query = (
            select(TaskAttemptORM.task_id, func.max(TaskAttemptORM.id).label("latest_attempt_id"))
            .where(_base_query.whereclause)  # type: ignore
            .group_by(col(TaskAttemptORM.task_id))
            .subquery()
        )
        query = _base_query.join(
            latest_attempts_query,
            (col(TaskAttemptORM.id) == latest_attempts_query.c.latest_attempt_id)
            & (col(TaskAttemptORM.task_id) == latest_attempts_query.c.task_id),
        )
    task_attempts = db_session.exec(query).all()

    # Verify that (1) all task attempts are associated to the user and present in the database,
    #             (2) all task attempts are for the same problem and
    #             (3) no >1 task attempts are for the same task
    if attempt_ids and (len(task_attempts) != len(attempt_ids)):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid task attempt IDs")

    _task_ids: set[int] = set()
    for task_attempt in task_attempts:
        if task_attempt.problem_id != problem_orm.id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid task attempts IDs: Found task attempts for different problem",
            )
        if task_attempt.task_id in _task_ids:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid task attempts IDs: Found multiple attempts for the same task",
            )
        _task_ids.add(task_attempt.task_id)

    for task_attempt in task_attempts:
        task_attempt.submissions.append(submission_orm)
        db_session.add(task_attempt)
    db_session.add(submission_orm)

    db_session.commit()
    db_session.refresh(submission_orm)

    permission_create(submission_orm)

    return submission_orm


@router.get("/submissions/{submission_id}", summary="Get results of a submission")
def get_submission(
    submission_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
    user: Annotated[UserORM, Depends(get_current_user)],
    task_id: int | None = None,
) -> SubmissionPublic:
    query = (
        select(SubmissionORM)
        .where(SubmissionORM.id == submission_id)
        .options(
            selectinload(SubmissionORM.task_attempts).selectinload(TaskAttemptORM.task_results),
            selectinload(SubmissionORM.task_attempts).selectinload(TaskAttemptORM.task),
            selectinload(SubmissionORM.problem),
            selectinload(SubmissionORM.user)
            .selectinload(UserORM.group_members)
            .selectinload(GroupMember.group),
            selectinload(SubmissionORM.user).selectinload(UserORM.roles),
        )
    )

    if task_id is not None:
        query = query.where(TaskAttemptORM.task_id == task_id)

    # Execute query and handle not found case
    submission = db_session.scalar(query)
    if submission is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Submission not found")

    if not permission_check(submission, "view", user):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have permission to view submission",
        )

    can_view_details = permission_check(submission.problem, "view_hidden_details", user)
    if can_view_details:
        return SubmissionPublic.model_validate(submission)

    with db_session.no_autoflush:
        has_private_failure: list[bool] = []
        for task_attempt in submission.task_attempts:
            has_private_failure.append(task_attempt.redact_private_fields())

        # Redact the results and the task (that it derives the testcase from)
        result = SubmissionPublic.model_validate(submission)
        if not can_view_details:
            for index, task_attempt_public in enumerate(result.task_attempts):
                task_attempt_public.has_private_failure = has_private_failure[index]
                if task_attempt_public.task_type == TaskType.PROGRAMMING:
                    programming_task = task_attempt_public.task.to_task()
                    programming_task.redact_private_fields()
                    task_attempt_public.task = TaskORM.from_task(programming_task)
        return result


@router.post(
    "/parse-python-functions",
    summary="Get python functions from a file",
    response_model=list[ParsedFunction],
)
def parse_python_functions(
    data: ParseRequest,
):
    return parse_python_functions_from_file_content(data.content)
