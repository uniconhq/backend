"""The catalogue of blocks, read with no session: each block once, with its
words and its forms, `min` given numbers or a group's runs, and the fold
names stage 4 gave gone; with the leaves, the facts a value may read and
the word that skips a run; a program's folder and language, and the
numbers written out alone, marked so.
"""

import httpx


async def test_a_visitor_reads_every_block_once_with_its_forms(
    client: httpx.AsyncClient,
) -> None:
    client.cookies.clear()

    answer = await client.get("/api/v1/blocks")

    assert answer.status_code == 200
    listed = answer.json()["blocks"]
    found = {block["name"]: block for block in listed}
    assert len(found) == len(listed)
    assert {"add", "if", "min", "max", "sum", "count"} <= set(found)
    assert not {"min_runs", "max_runs", "sum_runs", "count_runs"} & set(found)
    assert found["min"]["words"] == (
        "the least of its inputs, of a column over a group's runs, or of a value over a task's "
        "results"
    )
    assert [(form["given"], form["scope"]) for form in found["min"]["forms"]] == [
        ("numbers", "both"),
        ("a group's runs", "task"),
        ("a task's results", "leaderboard"),
    ]
    numbers, runs, results = found["min"]["forms"]
    assert results["inputs"]["over"]["kind"] == "results"
    assert found["latest"]["forms"][0]["gives"] == "submission"
    assert numbers["inputs"] == {
        "of": {
            "kind": "number",
            "least": 2,
            "most": None,
            "optional": False,
            "per_run": False,
            "plain": False,
        }
    }
    assert list(runs["inputs"]) == ["over", "of", "where", "missing"]
    assert runs["inputs"]["over"]["kind"] == "runs"
    assert runs["inputs"]["of"]["per_run"]
    assert runs["inputs"]["missing"] == {
        "kind": "missing",
        "least": None,
        "most": None,
        "optional": True,
        "per_run": False,
        "plain": False,
    }
    assert found["count"]["forms"][0]["inputs"]["weights"]["kind"] == "weights"
    assert answer.json()["leaves"] == ["runs", "run", "value", "fact", "text"]
    assert answer.json()["facts"] == ["seconds_late", "seconds", "compiled"]
    assert answer.json()["leaderboard_leaves"] == ["value", "results", "column", "name"]
    assert answer.json()["leaderboard_facts"] == [
        "attempt",
        "seconds",
        "seconds_late",
        "marked",
        "compiled",
    ]
    assert answer.json()["skip"] == "skip"
    assert answer.json()["languages"] == ["c", "cpp", "java", "python", "ipynb"]
    exec_inputs = found["exec"]["forms"][0]["inputs"]
    assert {name: each["kind"] for name, each in exec_inputs.items()} == {
        "program": "path",
        "language": "language",
        "over": "runs",
        "time_limit": "number",
        "memory_limit": "number",
    }
    assert exec_inputs["time_limit"]["plain"] and exec_inputs["time_limit"]["optional"]
    assert found["entered"]["forms"][0]["inputs"]["at_least"]["plain"]
