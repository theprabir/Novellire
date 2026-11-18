"""Persistent chapter-scoped chat with Plan and Write modes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult
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
