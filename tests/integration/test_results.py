"""Releasing a run task's results and taking a release back, over HTTP: each
route hands forge the task and the confirmation, and answers where the
task's results stand, with every action, who and when; one sent without
its confirmation is `confirmation_required` with the words to show; a task
that does not grade by runs has no results to release; and the task's
state says where its results stand.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from forge.api import results
from forge.api.errors import ConfirmationRequired
from forge.api.results import TAKE_BACK_WARNING, ResultsAction, ResultsState
from forge.testing import FakeForge

from tests.integration.conftest import ORIGIN, TASK, publish

AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)


async def test_a_task_never_released_says_so_and_one_not_graded_by_runs_has_none_to_release(
    client: httpx.AsyncClient, sum_task: FakeForge
) -> None:
    await publish(client)

    state = (await client.get(TASK)).json()
    released = await client.post(f"{TASK}/results/release", json={"confirm": True}, headers=ORIGIN)

    assert state["results"] == {"released": False, "history": []}
    assert released.status_code == 409
    assert released.json()["code"] == "not_a_run_task"


async def test_each_route_hands_forge_the_confirmation_and_answers_the_state(
    client: httpx.AsyncClient, sum_task: FakeForge, monkeypatch: pytest.MonkeyPatch
) -> None:
    handed: list[tuple[str, str, bool]] = []
    history: list[ResultsAction] = []

    def acting(name: str, act: str, words: str) -> Any:
        async def act_on(organiser: Any, task: str, *, confirmed: bool = False) -> bool:
            handed.append((name, task, confirmed))
            if not confirmed:
                raise ConfirmationRequired(words, action=name)
            history.append(ResultsAction(act, 7, "ada", AT))
            return True

        return act_on

    async def state(organiser: Any, task: str) -> ResultsState:
        return ResultsState(bool(history) and history[-1].action == "released", tuple(history))

    monkeypatch.setattr(results, "release", acting("release", "released", "Shown to all."))
    monkeypatch.setattr(
        results, "hide_again", acting("hide_again", "hidden_again", TAKE_BACK_WARNING)
    )
    monkeypatch.setattr(results, "state", state)

    asked = await client.post(f"{TASK}/results/release", json={}, headers=ORIGIN)
    released = await client.post(f"{TASK}/results/release", json={"confirm": True}, headers=ORIGIN)
    warned = await client.post(f"{TASK}/results/hide", json={}, headers=ORIGIN)
    hidden = await client.post(f"{TASK}/results/hide", json={"confirm": True}, headers=ORIGIN)

    assert (asked.status_code, asked.json()["code"]) == (409, "confirmation_required")
    assert (asked.json()["detail"], asked.json()["action"]) == ("Shown to all.", "release")
    assert released.json() == {
        "released": True,
        "history": [
            {"action": "released", "by": 7, "by_name": "ada", "at": "2026-09-26T14:00:00Z"}
        ],
    }
    assert warned.status_code == 409
    assert warned.json()["detail"] == (
        "Entrants may already have seen these results; hiding them again won't undo that."
    )
    assert hidden.json()["released"] is False
    assert handed == [
        ("release", "acme/spring/sum", False),
        ("release", "acme/spring/sum", True),
        ("hide_again", "acme/spring/sum", False),
        ("hide_again", "acme/spring/sum", True),
    ]
