"""A contest's or a task's files, read and written as the organiser: a
folder's entries, one file at a version, the history, a write and a
rollback. The same five routes are served under the contest and the task
prefixes, made by `router_at`, so each kind gets its own operation names.
Reading needs the observer role at the place and writing the manager role.
The history names each change's `author` by username beside `author_id`,
whether or not they still hold a role there, so a page names every author
without a route that names users.

A write carries the token the file was read with, and one that has moved
since is answered `conflict` with nothing written. A write to a contest's
file answers with the version it made and, for `contest.yaml`, the notes its
boards report, as a task's save answers its own. A write to a task's file is a save
of the task and answers as the save does, with a publication or a draft,
and may name, in place of content, a file the organiser uploaded for that
path, whose pointer it writes. A rollback writes the file as it was at an
older version back as a new change, so it answers as a write does. A file
that is an upload is read and listed with `upload`, the size and digest of
what it holds.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from forge.api import contests, files, tasks
from forge.api.access import Organiser
from forge.api.publications import Draft, Published
from forge.api.types import ContestId, Role, ScopeKind, TaskId, Uploaded, VersionId

from unicon.api.guard import PREFIX, require
from unicon.schemas.files import (
    FileContent,
    RollbackFile,
    WriteFile,
    WriteTaskFile,
    Written,
    token_of,
)
from unicon.schemas.publications import SaveResult


def router_at(kind: ScopeKind) -> APIRouter:
    """The file routes under the prefix of `kind`, a contest or a task."""
    name = kind.value.capitalize()
    router = APIRouter(prefix=PREFIX[kind], tags=["files"])
    Observer = Annotated[Organiser, Depends(require(Role.OBSERVER, kind))]
    Manager = Annotated[Organiser, Depends(require(Role.MANAGER, kind))]
    answer = SaveResult if kind is ScopeKind.TASK else Written

    @router.get("/tree", operation_id=f"list{name}Tree", summary="A folder's entries")
    async def list_tree(
        organiser: Observer,
        path: Annotated[str, Query(description="The folder; the top when empty")] = "",
    ) -> tuple[files.TreeEntry, ...]:
        return await files.tree(organiser, _place(organiser), path)

    @router.get(
        "/files/{path:path}", operation_id=f"read{name}File", summary="One file at a version"
    )
    async def read_file(
        organiser: Observer,
        path: str,
        at: Annotated[str | None, Query(description="A version; the latest when absent")] = None,
    ) -> FileContent:
        file = await files.read(
            organiser, _place(organiser), path, VersionId(at) if at is not None else None
        )
        return FileContent.of(file)

    @router.get("/history", operation_id=f"list{name}History", summary="Every change, newest first")
    async def list_history(
        organiser: Observer,
        path: Annotated[str | None, Query(description="One file; every file when absent")] = None,
    ) -> tuple[files.Change, ...]:
        return await files.history(organiser, _place(organiser), path)

    write = router.put(
        "/files/{path:path}",
        operation_id=f"write{name}File",
        summary="Write one file",
        response_model=answer,
    )
    if kind is ScopeKind.TASK:

        @write
        async def write_task_file(
            organiser: Manager, path: str, body: WriteTaskFile
        ) -> Written | Published | Draft:
            """A save of the task. A file named by its `upload` is one the
            caller uploaded for this path: one that is not theirs for it is
            `invalid_inputs`, and one whose bytes have not arrived
            `upload_not_ready`.
            """
            content = body.edit_content()
            if isinstance(content, Uploaded):
                return await files.write_upload(
                    organiser,
                    tasks.task_id_of(organiser.scope),
                    path,
                    content.upload,
                    token_of(body.token),
                    message=body.message,
                    confirm=body.confirm,
                    keep_as_draft=body.keep_as_draft,
                )
            return await _write(organiser, path, content, body)

    else:

        @write
        async def write_contest_file(
            organiser: Manager, path: str, body: WriteFile
        ) -> Written | Published | Draft:
            return await _write(organiser, path, body.data(), body)

    @router.post(
        "/files/{path:path}/rollback",
        operation_id=f"rollBack{name}File",
        summary="Write a file back as it was at an older version",
        response_model=answer,
    )
    async def roll_back_file(
        organiser: Manager, path: str, body: RollbackFile
    ) -> Written | Published | Draft:
        result = await files.rollback(
            organiser,
            _place(organiser),
            path,
            VersionId(body.version),
            token_of(body.token),
            message=body.message,
            confirm=body.confirm,
            keep_as_draft=body.keep_as_draft,
        )
        return _answered(result)

    return router


async def _write(
    organiser: Organiser, path: str, content: bytes, body: WriteFile | WriteTaskFile
) -> Written | Published | Draft:
    result = await files.write(
        organiser,
        _place(organiser),
        path,
        content,
        token_of(body.token),
        message=body.message,
        confirm=body.confirm,
        keep_as_draft=body.keep_as_draft,
    )
    return _answered(result)


def _place(organiser: Organiser) -> ContestId | TaskId:
    scope = organiser.scope
    if scope.kind is ScopeKind.TASK:
        return tasks.task_id_of(scope)
    return contests.contest_id_of(scope)


def _answered(result: files.Written | Published | Draft) -> Written | Published | Draft:
    if isinstance(result, Published | Draft):
        return result
    return Written(version=result.version, notes=list(result.notes))
