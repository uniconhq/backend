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
