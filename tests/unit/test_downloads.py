"""The download door's addresses name a task by the names its route was
reached by, not its keys, which the door would not find."""

from forge.api.types import Scope

from unicon.api.downloads import submitted, task_downloads, task_file


def test_a_tasks_address_is_by_its_names_each_part_quoted() -> None:
    scope = Scope("k1", "k2", "k3", label="acme/spring/sum")

    assert task_downloads(scope) == "/-/downloads/acme/spring/sum"
    assert task_file(scope, "abc", "data/a b.txt") == (
        "/-/downloads/acme/spring/sum/versions/abc/data/a%20b.txt"
    )
    assert task_file(scope, None, "task.yaml") is None
    assert submitted({"code": {"files": ["files/a#b.py"]}}, "/at") == {
        "code": {"files": [{"path": "files/a#b.py", "href": "/at/files/a%23b.py"}]}
    }
