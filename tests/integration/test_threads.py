"""Announcements and clarifications over HTTP, the forge's push telling the
streams what it changed, and the stream itself. An organiser posts, edits
and closes an announcement and a contestant reads the open ones beside the
contest's home and a task's page. A contestant asks a question, an
organiser sees it in the inbox, replies, marks it answered, which takes it
out of the inbox, and unmarks it; the contestant's follow-up on an answered
question opens it again; and an answer made public reaches every
contestant. Someone who is not an approved contestant asks nothing, and an
empty title is refused naming it. A signed push is answered and then
publishes the id of the thread it names. The stream needs a session, and
writes each nudge as an event named by its kind with the id as its data.
"""

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx
import psycopg
from forge.api.live import Nudge, NudgeKind
from forge.testing import FakeForge, Setup

from tests.integration.conftest import CONTEST, ORIGIN, TASK, enter, sign_in_as
from unicon.api.v1.live import _events

NOTE = {"title": "Welcome", "body": "Good luck."}


async def test_an_organiser_announces_and_a_contestant_reads_the_open_ones(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 7)
    on_contest = await client.post(f"{CONTEST}/announcements", json=NOTE, headers=ORIGIN)
    on_task = await client.post(
        f"{TASK}/announcements", json={"title": "On sum", "body": "Read n first."}, headers=ORIGIN
    )
    old = await client.post(
        f"{CONTEST}/announcements", json={"title": "Old", "body": "o"}, headers=ORIGIN
    )
    edited = await client.patch(
        f"{CONTEST}/announcements/{on_contest.json()['number']}",
        json={"title": "Welcome all", "body": "Good luck, all."},
        headers=ORIGIN,
    )
    closed = await client.post(
        f"{CONTEST}/announcements/{old.json()['number']}/close", headers=ORIGIN
    )
    managed = await client.get(f"{CONTEST}/announcements")
    empty = await client.post(
        f"{CONTEST}/announcements", json={"title": " ", "body": "b"}, headers=ORIGIN
    )
    await sign_in_as(client, entered, 20)
    home = await client.get(f"{CONTEST}/home/announcements")
    page = await client.get(f"{TASK}/page/announcements")

    assert on_contest.status_code == 201, on_contest.text
    assert on_task.status_code == 201, on_task.text
    assert edited.json()["title"] == "Welcome all"
    assert closed.json()["closed"] is True
    assert [(note["title"], note["closed"]) for note in managed.json()] == [
        ("Welcome all", False),
        ("Old", True),
    ]
    assert (empty.status_code, empty.json()["code"], empty.json()["field"]) == (
        422,
        "invalid_message",
        "title",
    )
    assert [(note["title"], note["where"]["task"]) for note in home.json()] == [
        ("Welcome all", None),
        ("On sum", "sum"),
    ]
    assert [note["title"] for note in page.json()] == ["On sum"]


async def test_a_question_is_asked_answered_followed_up_and_answered_publicly(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    asked = await client.post(
        f"{CONTEST}/questions",
        json={"title": "Input size?", "body": "How big is n?", "task": "sum"},
        headers=ORIGIN,
    )
    number = asked.json()["number"]
    question = f"{CONTEST}/clarifications/20/{number}"
    await sign_in_as(client, entered, 7)
    inbox = await client.get("/api/v1/orgs/acme/clarifications")
    replied = await client.post(f"{question}/replies", json={"body": "Up to 10^5."}, headers=ORIGIN)
    marked = await client.put(f"{question}/answered", headers=ORIGIN)
    answered_inbox = await client.get("/api/v1/orgs/acme/clarifications")
    everything = await client.get(f"{CONTEST}/clarifications")
    unmarked = await client.delete(f"{question}/answered", headers=ORIGIN)
    await client.put(f"{question}/answered", headers=ORIGIN)
    public = await client.post(
        f"{question}/announcement", json={"title": "On n", "body": "At most 10^5."}, headers=ORIGIN
    )
    await sign_in_as(client, entered, 20)
    followed = await client.post(
        f"{CONTEST}/questions/{number}/comments", json={"body": "And m?"}, headers=ORIGIN
    )
    mine = await client.get(f"{CONTEST}/questions")
    page = await client.get(f"{TASK}/page/announcements")

    assert asked.status_code == 201, asked.text
    assert (asked.json()["task"], asked.json()["asker"]) == ("sum", 20)
    assert [entry["number"] for entry in inbox.json()] == [number]
    assert (replied.json()["answered"], replied.json()["closed"]) == (False, False)
    assert (marked.json()["answered"], marked.json()["closed"]) == (True, True)
    assert answered_inbox.json() == []
    assert [entry["answered"] for entry in everything.json()] == [True]
    assert unmarked.json()["answered"] is False
    assert public.status_code == 201, public.text
    assert public.json()["answers"] == {"user_id": 20, "number": number}
    assert (followed.json()["answered"], followed.json()["closed"]) == (False, False)
    [own] = mine.json()
    assert [(message["from_asker"], message["body"]) for message in own["messages"]] == [
        (False, "Up to 10^5."),
        (True, "And m?"),
    ]
    [shown] = page.json()
    assert (shown["title"], shown["answers_question"], shown["answers"]) == ("On n", True, None)


async def test_only_an_approved_contestant_asks(
    client: httpx.AsyncClient, entered: FakeForge
) -> None:
    await sign_in_as(client, entered, 8)

    refused = await client.post(
        f"{CONTEST}/questions", json={"title": "t", "body": "b"}, headers=ORIGIN
    )
    mine = await client.get(f"{CONTEST}/questions")

    assert (refused.status_code, refused.json()["code"]) == (403, "not_approved")
    assert mine.json() == []


async def test_a_signed_push_is_answered_and_then_publishes_the_thread_it_names(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    push = entered.state.orgs["acme"].event_push
    assert push is not None
    url, secret = push
    body = json.dumps(
        {
            "repository": {"name": "spring.u20.desk", "owner": {"login": "acme"}},
            "issue": {"number": 1, "labels": [{"name": "clarification"}]},
        }
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    database = str(held_setup.settings.database_url).replace("postgresql+psycopg", "postgresql")
    async with await psycopg.AsyncConnection.connect(database, autocommit=True) as listening:
        await listening.execute("LISTEN unicon_live")

        answered = await client.post(
            urlsplit(url).path,
            content=body,
            headers={"X-Forgejo-Signature": signature, "X-Forgejo-Event": "issue_comment"},
        )
        heard = [notify.payload async for notify in listening.notifies(timeout=1.0)]

    assert answered.status_code == 204
    [payload] = heard
    assert json.loads(payload)["k"] == "clarification"
    assert json.loads(payload)["u"] == 20


async def test_the_stream_needs_a_session(client: httpx.AsyncClient) -> None:
    refused = await client.get("/api/v1/live")

    assert (refused.status_code, refused.json()["code"]) == (401, "unauthenticated")


async def test_the_stream_writes_each_nudge_as_an_event_named_by_its_kind() -> None:
    async def nudges() -> AsyncIterator[Nudge | None]:
        yield None
        yield Nudge(NudgeKind.GRADING, "0192f4a4-7b7e-7000-8000-000000000001")

    written = [chunk async for chunk in _events(nudges())]

    assert written == [
        "retry: 5000\n\n",
        ": still here\n\n",
        "event: grading\ndata: 0192f4a4-7b7e-7000-8000-000000000001\n\n",
    ]


async def test_a_contestant_entered_later_reads_the_announcements_too(
    client: httpx.AsyncClient, entered: FakeForge, held_setup: Setup
) -> None:
    await sign_in_as(client, entered, 7)
    await client.post(f"{CONTEST}/announcements", json=NOTE, headers=ORIGIN)
    entered.add_user(21, "dave")
    await enter(client, entered, held_setup, 21)

    home = await client.get(f"{CONTEST}/home/announcements")

    assert [note["title"] for note in home.json()] == ["Welcome"]
