"""Persistent chapter-scoped chat with Plan and Write modes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationChunk, GenerationResult, ModelInfo
from novellire.storage.database import Database


def _client(tmp_path: Path, provider) -> TestClient:  # noqa: ANN001
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    app = create_app(
        settings=settings,
        database=Database(settings.database_path),
        provider=provider,
    )
    return TestClient(app)


def test_plan_chat_persists_messages_and_respects_author_notes(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text=(
                "Mira should keep the letter hidden.\n\n"
                "<planning_notes>\n"
                "- Mira hides the letter from Orin.\n"
                "- The gate stays locked.\n"
                "</planning_notes>"
            ),
            model="fake-model",
            duration_ms=10,
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post(
            "/api/projects", json={"name": "Ashfall", "genre": "Mystery"}
        ).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "title": "The Letter",
                "content": "Mira finds a letter beneath the gate.",
            },
        ).json()
        client.put(
            f"/api/projects/{project['id']}/documents/master_bible",
            json={"content": "The star is dimming over Ashfall."},
        )

        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "plan", "chapter_id": chapter["id"]},
        )
        assert thread.status_code == 201, thread.text
        thread = thread.json()
        assert thread["planning_notes"] == ""
        assert thread["mode"] == "plan"

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={
                "instructions": "Should Mira show the letter to Orin?",
                "model": "fake-model",
                "context_window": 2048,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["assistant"]["content"] == (
            "Mira should keep the letter hidden."
        )
        assert payload["thread"]["planning_notes"] == (
            "- Mira hides the letter from Orin.\n- The gate stays locked."
        )
        assert payload["thread"]["planning_notes_source"] == "model"
        assert payload["thread"]["title"] == "Should Mira show the letter to Orin?"
        assert payload["context"]["chapters"] == []

        prompt = provider.requests[0].prompt
        assert "Master story bible:\nThe star is dimming over Ashfall." in prompt
        assert "Current chapter text:\nMira finds a letter beneath the gate." in prompt
        assert "Conversation so far:\nNo earlier messages." in prompt

        bundle = client.get(f"/api/chat/threads/{thread['id']}").json()
        assert [message["role"] for message in bundle["messages"]] == [
            "user",
            "assistant",
        ]

        saved = client.patch(
            f"/api/chat/threads/{thread['id']}",
            json={"planning_notes": "- Author note: keep the letter hidden."},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["planning_notes_source"] == "author"

        again = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={"instructions": "What next?", "model": "fake-model"},
        )
        assert again.status_code == 200, again.text
        assert again.json()["thread"]["planning_notes"] == (
            "- Author note: keep the letter hidden."
        )
        assert again.json()["thread"]["planning_notes_source"] == "author"
        assert "Conversation so far:\nAuthor: Should Mira show" in provider.requests[
            1
        ].prompt


def test_write_chat_uses_chapter_prose_and_context(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="Mira stepped through the gate.",
            model="fake-model",
            duration_ms=10,
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "title": "The Gate",
                "content": "Mira waits before the locked gate.",
            },
        ).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "write", "chapter_id": chapter["id"]},
        ).json()

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={
                "instructions": "Draft her first attempt to open it.",
                "model": "fake-model",
                "target_words": 350,
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["assistant"]["content"] == (
            "Mira stepped through the gate."
        )
        prompt = provider.requests[0].prompt
        assert "Current chapter text:\nMira waits before the locked gate." in prompt
        assert "Target length: about 350 words." in prompt
        assert "Write the requested prose now." in prompt


class StreamingProvider:
    """Provider stub that streams fixed chunks instead of generating at once."""

    def __init__(self, chunks: list[GenerationChunk]) -> None:
        self.chunks = chunks
        self.requests = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201 - must not be used
        raise AssertionError("the stream endpoint should stream")

    def generate_stream(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        yield from self.chunks


def _events(response) -> list[dict]:  # noqa: ANN001
    return [
        json.loads(line)
        for line in response.text.splitlines()
        if line.strip()
    ]


def test_chat_stream_streams_deltas_and_stores_the_reply(
    tmp_path: Path,
) -> None:
    provider = StreamingProvider(
        [
            GenerationChunk(text="Mira waits. "),
            GenerationChunk(text="The gate stays shut."),
            GenerationChunk(model="fake-model", done=True),
        ]
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": "The Gate", "content": "Mira waits."},
        ).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "plan", "chapter_id": chapter["id"]},
        ).json()

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages/stream",
            json={"instructions": "What happens next?", "model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        events = _events(response)
        assert events[0]["type"] == "start"
        assert events[0]["user"]["content"] == "What happens next?"
        deltas = "".join(
            event["text"] for event in events if event["type"] == "delta"
        )
        assert deltas == "Mira waits. The gate stays shut."
        done = events[-1]
        assert done["type"] == "done"
        assert done["assistant"]["content"] == (
            "Mira waits. The gate stays shut."
        )
        assert done["assistant"]["model"] == "fake-model"

        bundle = client.get(f"/api/chat/threads/{thread['id']}").json()
        assert [message["role"] for message in bundle["messages"]] == [
            "user",
            "assistant",
        ]


def test_chat_stream_falls_back_to_a_single_delta(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="One complete reply.", model="fake-model", duration_ms=5
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads", json={"mode": "plan"}
        ).json()

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages/stream",
            json={"instructions": "Summarise.", "model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        events = _events(response)
        assert [event["type"] for event in events] == ["start", "delta", "done"]
        assert events[1]["text"] == "One complete reply."


def test_chat_stream_validates_before_streaming(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory()
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads", json={"mode": "plan"}
        ).json()

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages/stream",
            json={"instructions": "   ", "model": "fake-model"},
        )

        assert response.status_code == 400
        assert "Write a message" in response.json()["detail"]


def test_chat_mode_can_switch_within_a_conversation(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="Mira steps through the gate.", model="fake-model", duration_ms=5
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "plan"},
        ).json()
        assert thread["mode"] == "plan"

        switched = client.patch(
            f"/api/chat/threads/{thread['id']}", json={"mode": "write"}
        )
        assert switched.status_code == 200, switched.text
        assert switched.json()["mode"] == "write"

        reply = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={
                "instructions": "Draft the opening.",
                "model": "fake-model",
                "target_words": 240,
            },
        )
        assert reply.status_code == 200, reply.text
        assert "Target length: about 240 words." in provider.requests[0].prompt

        invalid = client.patch(
            f"/api/chat/threads/{thread['id']}", json={"mode": "edit"}
        )
        assert invalid.status_code == 422


def test_write_reply_can_be_inserted_into_its_chapter(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="Mira steps through the gate.", model="fake-model", duration_ms=5
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": "The Gate", "content": "Mira waits."},
        ).json()
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "write", "chapter_id": chapter["id"]},
        ).json()
        sent = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={"instructions": "Draft the crossing.", "model": "fake-model"},
        )
        assert sent.status_code == 200, sent.text
        reply = sent.json()["assistant"]

        appended = client.post(
            f"/api/chat/threads/{thread['id']}/messages/{reply['id']}/insert",
            json={"replace": False},
        )
        assert appended.status_code == 200, appended.text
        assert appended.json()["content"] == (
            "Mira waits.\n\nMira steps through the gate."
        )
        assert appended.json()["word_count"] == 7

        revisions = client.get(
            f"/api/chapters/{chapter['id']}/revisions"
        ).json()
        assert len(revisions) == 1
        assert revisions[0]["word_count"] == 2

        replaced = client.post(
            f"/api/chat/threads/{thread['id']}/messages/{reply['id']}/insert",
            json={"replace": True},
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["content"] == "Mira steps through the gate."


def test_insert_respects_the_approval_lock(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(
            text="A new ending.", model="fake-model", duration_ms=5
        )
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "title": "The Gate",
                "content": "Mira waits.",
                "status": "approved",
            },
        ).json()
        assert chapter["status"] == "approved"
        thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "write", "chapter_id": chapter["id"]},
        ).json()
        sent = client.post(
            f"/api/chat/threads/{thread['id']}/messages",
            json={"instructions": "Draft it.", "model": "fake-model"},
        )
        reply = sent.json()["assistant"]

        response = client.post(
            f"/api/chat/threads/{thread['id']}/messages/{reply['id']}/insert",
            json={"replace": False},
        )

        assert response.status_code == 400
        assert "approved" in response.json()["detail"]
        unchanged = client.get(
            f"/api/projects/{project['id']}/manuscript"
        ).json()["chapters"][0]
        assert unchanged["content"] == "Mira waits."


def test_insert_requires_a_chapter_scoped_write_thread(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory(
        result=GenerationResult(text="Some prose.", model="fake-model", duration_ms=5)
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": "The Gate"},
        ).json()

        plan_thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "plan", "chapter_id": chapter["id"]},
        ).json()
        plan_reply = client.post(
            f"/api/chat/threads/{plan_thread['id']}/messages",
            json={"instructions": "What next?", "model": "fake-model"},
        ).json()["assistant"]
        plan_insert = client.post(
            f"/api/chat/threads/{plan_thread['id']}/messages/{plan_reply['id']}/insert",
            json={"replace": False},
        )
        assert plan_insert.status_code == 400
        assert "Write mode" in plan_insert.json()["detail"]

        wide_thread = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "write"},
        ).json()
        wide_reply = client.post(
            f"/api/chat/threads/{wide_thread['id']}/messages",
            json={"instructions": "Draft.", "model": "fake-model"},
        ).json()["assistant"]
        wide_insert = client.post(
            f"/api/chat/threads/{wide_thread['id']}/messages/{wide_reply['id']}/insert",
            json={"replace": False},
        )
        assert wide_insert.status_code == 400
        assert "project-wide" in wide_insert.json()["detail"]

        other = client.post(
            f"/api/projects/{project['id']}/chat/threads",
            json={"mode": "write", "chapter_id": chapter["id"]},
        ).json()
        foreign = client.post(
            f"/api/chat/threads/{other['id']}/messages/{wide_reply['id']}/insert",
            json={"replace": False},
        )
        assert foreign.status_code == 404


def test_chat_rejects_a_chapter_from_another_project(
    tmp_path: Path, fake_provider_factory
) -> None:
    provider = fake_provider_factory()
    with _client(tmp_path, provider) as client:
        first = client.post("/api/projects", json={"name": "First"}).json()
        second = client.post("/api/projects", json={"name": "Second"}).json()
        chapter = client.post(
            f"/api/projects/{first['id']}/chapters",
            json={"title": "Mine", "content": "Text."},
        ).json()

        response = client.post(
            f"/api/projects/{second['id']}/chat/threads",
            json={"mode": "plan", "chapter_id": chapter["id"]},
        )

        assert response.status_code == 400
        assert "another project" in response.json()["detail"]
