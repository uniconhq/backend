from http import HTTPStatus
from typing import Annotated

import libcst
from fastapi import Depends, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from unicon_backend.dependencies.common import get_db_session
from unicon_backend.evaluator.tasks.programming.visitors import ParsedFunction, TypingCollector
from unicon_backend.models.problem import ProblemORM, TaskORM


def get_task_by_id(
    id: int,
    problem_id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
) -> TaskORM:
    if (
        task_orm := db_session.scalar(
            select(TaskORM).where(TaskORM.id == id).where(TaskORM.problem_id == problem_id)
        )
    ) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Task not found!")
    return task_orm


def get_task_versions(
    task_id: int, problem_id: int, db_session: Annotated[Session, Depends(get_db_session)]
) -> list[int]:
    task_data = db_session.exec(
        select(TaskORM.id, TaskORM.updated_version_id).where(TaskORM.problem_id == problem_id)
    ).all()

    if not any(task_id == row[0] for row in task_data):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Task not found")

    updated_version_to_old_task_data = {row[1]: row for row in task_data if row[1] is not None}
    old_to_new_task_data = {row[0]: row for row in task_data if row[1] is not None}

    # Build the full chain of tasks
    all_versions = [task_id]

    # First, go backwards in history to find older versions
    current = task_id
    while current in updated_version_to_old_task_data:
        old_task_id, _ = updated_version_to_old_task_data[current]
        if old_task_id in all_versions:
            break  # Prevent infinite loops
        all_versions.append(old_task_id)
        current = old_task_id

    # Then, go forwards to find newer versions
    current = task_id
    while current in old_to_new_task_data:
        _, new_task_id = old_to_new_task_data[current]
        if new_task_id in all_versions:
            break  # Prevent infinite loops
        all_versions.insert(0, new_task_id)  # Add to beginning of list
        current = new_task_id

    return all_versions


def get_problem_by_id(
    id: int,
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ProblemORM:
    if (
        problem_orm := db_session.scalar(
            select(ProblemORM)
            .where(ProblemORM.id == id)
            .options(selectinload(ProblemORM.tasks.and_(col(TaskORM.updated_version_id) == None)))
        )
    ) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Problem definition not found!")
    return problem_orm


def parse_python_functions_from_file_content(content: str) -> list[ParsedFunction]:
    try:
        module = libcst.parse_module(content)
    except libcst.ParserSyntaxError as e:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Invalid Python code!") from e

    visitor = TypingCollector()
    module.visit(visitor)
    return visitor.results
