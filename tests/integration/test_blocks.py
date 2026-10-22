"""The catalogue of blocks, read with no session: each block once, with its
words and its forms, `min` given numbers or a group's runs, and the fold
names stage 4 gave gone.
"""

import httpx


async def test_a_visitor_reads_every_block_once_with_its_forms(
    client: httpx.AsyncClient,
) -> None:
    client.cookies.clear()

    answer = await client.get("/api/v1/blocks")

    assert answer.status_code == 200
    found = {block["name"]: block for block in answer.json()}
    assert len(found) == len(answer.json())
    assert {"add", "if", "min", "max", "sum", "count"} <= set(found)
    assert not {"min_runs", "max_runs", "sum_runs", "count_runs"} & set(found)
    assert found["min"]["words"] == "the least of its inputs, or of a column over a group's runs"
    assert [form["given"] for form in found["min"]["forms"]] == ["numbers", "a group's runs"]
    numbers, runs = found["min"]["forms"]
    assert numbers["inputs"] == {
        "of": {"kind": "number", "least": 2, "most": None, "optional": False, "per_run": False}
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
    }
    assert found["count"]["forms"][0]["inputs"]["weights"]["kind"] == "weights"
