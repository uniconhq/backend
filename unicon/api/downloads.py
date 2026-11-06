"""The addresses the download door (`unicon/api/door.py`) serves files at,
built here alone so no page builds one. An address names the org, contest
and task by the names it was reached by, as the door reads them back, and
each part of a path is quoted on its own so a name stays one segment.
"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from forge.api.types import Scope

DOWNLOADS = "/-/downloads"
INPUTS = "inputs"
RUNS = "runs"


def quoted(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/"))


def task_downloads(scope: Scope) -> str:
    """Where the door serves a task's files from. `scope` is the task as
    the route's path named it, so its label holds the names."""
    assert scope.label is not None, "a task scope read from a path is labelled"
    return f"{DOWNLOADS}/{quoted(scope.label)}"


def task_file(scope: Scope, version: str | None, path: str) -> str | None:
    """One of a task's files at a version; none without a version."""
    if version is None:
        return None
    return f"{task_downloads(scope)}/versions/{quote(version, safe='')}/{quoted(path)}"


def _workflow(owner: str, name: str) -> str:
    return f"{DOWNLOADS}/workflows/{quote(owner, safe='')}/{quote(name, safe='')}"


def workflow_draft(owner: str, name: str, path: str) -> str:
    return f"{_workflow(owner, name)}/draft/{quoted(path)}"


def workflow_version(owner: str, name: str, version: str, path: str) -> str:
    return f"{_workflow(owner, name)}/versions/{quote(version, safe='')}/{quoted(path)}"


def submitted(inputs: Mapping[str, Any], at: str) -> dict[str, Any]:
    """A submission's inputs as `submission.json` holds them, each file a
    path and its address below `at`, the submission's own address; a part's
    the same. Anything but a path is dropped, so no address comes from the
    file itself."""
    return {name: _addressed(given, at) for name, given in inputs.items()}


def _addressed(given: Any, at: str) -> Any:
    if not isinstance(given, dict):
        return given
    files, parts = given.get("files"), given.get("parts")
    moved = dict(given)
    if isinstance(files, list):
        paths = [path for path in files if isinstance(path, str)]
        moved["files"] = [{"path": path, "href": f"{at}/{quoted(path)}"} for path in paths]
    if isinstance(parts, dict):
        moved["parts"] = {number: _addressed(part, at) for number, part in parts.items()}
    return moved
