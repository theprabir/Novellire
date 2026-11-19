"""Plot-thread management: resolve with provenance, reopen, and validate."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import ModelInfo
from novellire.storage.database import Database
from novellire.storage.event_repository import EventDraft, EventRepository


class UnusedProvider:
    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("thread management must not run inference")


def _client(tmp_path: Path, database: Database) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(settings=settings, database=database, provider=UnusedProvider())
    )


def _project_with_thread(tmp_path: Path) -> tuple[TestClient, Database, int, dict]:
    database = Database(tmp_path / "data" / "novellire.db")
    client = _client(tmp_path, database)
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "The Gate"}
    ).json()
    EventRepository(database).replace_for_chapter(
        project["id"],
        chapter["id"],
        [EventDraft(summary="Orin arrives with the key.", threads=("Who forged the key?",))],
        model="fake-model",
    )
    return client, database, project["id"], chapter


def test_resolving_a_thread_records_provenance(tmp_path: Path) -> None:
    client, _, project_id, chapter = _project_with_thread(tmp_path)
    with client:
        response = client.put(
            f"/api/projects/{project_id}/threads",
            json={
                "thread": "Who forged the key?",
                "status": "resolved",
                "note": "The smith confesses.",
                "chapter_id": chapter["id"],
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "resolved"
        assert payload["resolution"]["thread"] == "Who forged the key?"

        ledger = client.get(f"/api/projects/{project_id}/continuity").json()
        thread = ledger["threads"][0]
        assert thread["status"] == "resolved"
        assert thread["note"] == "The smith confesses."
        assert thread["resolved_chapter"] == {"position": 1, "title": "The Gate"}
        assert ledger["counts"]["open_threads"] == 0
        assert ledger["counts"]["threads"] == 1


def test_resolving_twice_updates_one_decision(tmp_path: Path) -> None:
    client, _, project_id, _ = _project_with_thread(tmp_path)
    with client:
        for note in ("First note.", "Second note."):
            client.put(
                f"/api/projects/{project_id}/threads",
                json={
                    "thread": "who forged the key?",
                    "status": "resolved",
                    "note": note,
                },
            )

        ledger = client.get(f"/api/projects/{project_id}/continuity").json()
        assert len(ledger["threads"]) == 1
        assert ledger["threads"][0]["note"] == "Second note."


def test_reopening_clears_the_decision(tmp_path: Path) -> None:
    client, _, project_id, _ = _project_with_thread(tmp_path)
    with client:
        client.put(
            f"/api/projects/{project_id}/threads",
            json={"thread": "Who forged the key?", "status": "resolved", "note": "Done."},
        )
        response = client.put(
            f"/api/projects/{project_id}/threads",
            json={"thread": "Who forged the key?", "status": "open"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "open", "resolution": None}
        ledger = client.get(f"/api/projects/{project_id}/continuity").json()
        thread = ledger["threads"][0]
        assert thread["status"] == "open"
        assert thread["note"] == ""
        assert ledger["counts"]["open_threads"] == 1


def test_invalid_thread_requests_are_refused(tmp_path: Path) -> None:
    client, _, project_id, _ = _project_with_thread(tmp_path)
    other = client.post("/api/projects", json={"name": "Elsewhere"}).json()
    other_chapter = client.post(
        f"/api/projects/{other['id']}/chapters", json={"title": "Other"}
    ).json()
    with client:
        empty = client.put(
            f"/api/projects/{project_id}/threads",
            json={"thread": "   ", "status": "resolved"},
        )
        assert empty.status_code == 400

        status = client.put(
            f"/api/projects/{project_id}/threads",
            json={"thread": "Who forged the key?", "status": "solved"},
        )
        assert status.status_code == 400

        foreign_chapter = client.put(
            f"/api/projects/{project_id}/threads",
            json={
                "thread": "Who forged the key?",
                "status": "resolved",
                "chapter_id": other_chapter["id"],
            },
        )
        assert foreign_chapter.status_code == 400

        missing = client.put(
            "/api/projects/999/threads",
            json={"thread": "Who forged the key?", "status": "resolved"},
        )
        assert missing.status_code == 404
