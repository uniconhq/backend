"""A primitive as the palette lists it: a limit raised from the sum or the
largest of a number over a programs port, and that port with the inputs
each program takes and the outputs given of each, a number output with
which way is better and its bounds.
"""

from forge.api.workflows import PrimitiveDeclaration, PrimitiveVersion

from unicon.schemas.workflows import Primitive

PROGRAMS = {
    "schema_version": 6,
    "image": "ghcr.io/uniconhq/primitive-exec@sha256:" + "0" * 64,
    "batch": True,
    "outputs_from": "programs",
    "limits": {
        "time_ms": 4000,
        "cpu_ms": 4000,
        "memory_mb": 512,
        "pids": 1056,
        "output_mb": 64,
        "gpus": 0,
    },
    "limits_from": {
        "time_ms": {"max": "programs.time_limit", "scale": 4000, "add": 6000},
        "memory_mb": {"sum": "programs.memory_limit", "add": 512},
    },
    "inputs": {
        "programs": {
            "type": "programs",
            "inputs": {
                "source": {"type": "folder", "runs": True},
                "language": {"type": "enum", "options": ["c", "python"]},
                "manifest": {"type": "file", "runs": False, "optional": True},
                "time_limit": "number",
                "memory_limit": "number",
            },
            "outputs": {
                "score": {"type": "number", "better": "higher", "at_least": 0, "at_most": 1}
            },
        }
    },
    "outputs": {"outcome": "outcome"},
}


def test_a_programs_port_and_its_limits_are_listed_whole() -> None:
    found = PrimitiveVersion("exec", "v2", PrimitiveDeclaration.model_validate(PROGRAMS))

    listed = Primitive.of(found).model_dump(mode="json")

    assert listed["limits_from"] == {
        "time_ms": {
            "input": None,
            "sum": None,
            "max": "programs.time_limit",
            "scale": "4000",
            "add": "6000",
        },
        "memory_mb": {
            "input": None,
            "sum": "programs.memory_limit",
            "max": None,
            "scale": "1",
            "add": "512",
        },
    }
    programs = listed["inputs"]["programs"]
    assert sorted(programs["inputs"]) == [
        "language",
        "manifest",
        "memory_limit",
        "source",
        "time_limit",
    ]
    assert programs["outputs"]["score"]["type"] == "number"
    assert (
        programs["outputs"]["score"]["better"],
        programs["outputs"]["score"]["at_least"],
        programs["outputs"]["score"]["at_most"],
    ) == ("higher", "0", "1")


def test_a_primitive_with_two_forms_lists_each_and_leaves_the_top_empty() -> None:
    limits = {
        "time_ms": 1,
        "cpu_ms": 1,
        "memory_mb": 1,
        "pids": 1,
        "output_mb": 1,
        "gpus": 0,
    }
    declared = PrimitiveDeclaration.model_validate(
        {
            "schema_version": 6,
            "image": "ghcr.io/uniconhq/primitive-two@sha256:" + "0" * 64,
            "forms": {
                "one": {
                    "limits": limits,
                    "inputs": {"program": "text"},
                    "outputs": {"outcome": "outcome"},
                },
                "several": {
                    "description": "Runs several.",
                    "limits": {**limits, "time_ms": 2},
                    "inputs": {"bundle": "text"},
                    "outputs": {"outcome": "outcome"},
                },
            },
        }
    )

    listed = Primitive.of(PrimitiveVersion("two", "v1", declared)).model_dump(mode="json")

    assert listed["limits"] == listed["limits_from"] == listed["inputs"] == listed["outputs"] == {}
    assert listed["forms"]["several"]["description"] == "Runs several."
    assert listed["forms"]["one"]["inputs"]["program"]["type"] == "text"
    assert listed["forms"]["several"]["limits"]["time_ms"] == 2
