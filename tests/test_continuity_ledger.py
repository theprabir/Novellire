"""Continuity ledger: recorded timeline, knowledge changes, thread provenance."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database
from novellire.storage.event_repository import EventDraft, EventRepository


class UnusedProvider:
    """The ledger never calls a model; fail loudly if it does."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("the continuity ledger must not run inference")


def _client(tmp_path: Path, database: Database) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(settings=settings, database=database, provider=UnusedProvider())
    )


def _project_with_chapters(client: TestClient, titles: list[str]) -> tuple[int, list]:
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapters = [
        client.post(
            f"/api/projects/{project['id']}/chapters", json={"title": title}
        ).json()
        for title in titles
    ]
    return project["id"], chapters


def _character(client: TestClient, project_id: int, name: str) -> int:
    return client.post(
        f"/api/projects/{project_id}/characters", json={"name": name}
    ).json()["id"]


def _state(
    client: TestClient,
    project_id: int,
    *,
    character_id: int,
    chapter_id: int,
    **fields,
) -> None:
    response = client.post(
        f"/api/projects/{project_id}/character-states",
        json={"character_id": character_id, "chapter_id": chapter_id, **fields},
    )
    assert response.status_code == 201, response.text


def test_the_ledger_reports_timeline_events_and_threads(tmp_path: Path) -> None:
    database = Database((tmp_path / "data" / "novellire.db"))
    with _client(tmp_path, database) as client:
        project_id, chapters = _project_with_chapters(client, ["The Gate", "The Key"])
        events = EventRepository(database)
        events.replace_for_chapter(
            project_id,
            chapters[0]["id"],
            [
                EventDraft(
                    summary="Orin arrives with the key.",
                    characters=("Orin",),
                    locations=("the gate",),
                    threads=("Who forged the key?",),
                )
            ],
            model="fake-model",
        )
        events.replace_for_chapter(
            project_id,
            chapters[1]["id"],
            [
                EventDraft(
                    summary="Mira hides the key.",
                    threads=("who forged the key?", "What does it open?"),
                )
            ],
            model="fake-model",
        )

        ledger = client.get(f"/api/projects/{project_id}/continuity").json()

        assert ledger["counts"]["chapters"] == 2
        assert ledger["counts"]["events"] == 2
        assert ledger["counts"]["threads"] == 2
        assert [row["position"] for row in ledger["timeline"]] == [1, 2]
        assert ledger["timeline"][1]["events"][0]["summary"] == "Mira hides the key."
        threads = {thread["thread"]: thread for thread in ledger["threads"]}
        assert "Who forged the key?" in threads
        forged = threads["Who forged the key?"]
        assert forged["event_count"] == 2
        assert [row["position"] for row in forged["chapters"]] == [1, 2]


def test_the_ledger_shows_which_state_fields_changed(tmp_path: Path) -> None:
    database = Database((tmp_path / "data" / "novellire.db"))
    with _client(tmp_path, database) as client:
        project_id, chapters = _project_with_chapters(client, ["The Gate", "The Key"])
        mira = _character(client, project_id, "Mira")
        _state(
            client,
            project_id,
            character_id=mira,
            chapter_id=chapters[0]["id"],
            location="the siege camp",
            knowledge="Orin has not arrived.",
        )
        _state(
            client,
            project_id,
            character_id=mira,
            chapter_id=chapters[1]["id"],
            location="the gate",
            knowledge="The key opens the northern gate.",
        )

        ledger = client.get(f"/api/projects/{project_id}/continuity").json()

        assert ledger["counts"]["states"] == 2
        character = ledger["characters"][0]
        assert character["name"] == "Mira"
        first, second = character["snapshots"]
        assert sorted(first["changed"]) == ["knowledge", "location"]
        assert sorted(second["changed"]) == ["knowledge", "location"]
        assert second["knowledge"] == "The key opens the northern gate."
        assert second["chapter_position"] == 2


def test_an_empty_project_has_an_empty_ledger(tmp_path: Path) -> None:
    database = Database((tmp_path / "data" / "novellire.db"))
    with _client(tmp_path, database) as client:
        project = client.post("/api/projects", json={"name": "Empty"}).json()

        ledger = client.get(f"/api/projects/{project['id']}/continuity").json()

        assert ledger["counts"] == {
            "chapters": 0,
            "events": 0,
            "states": 0,
            "threads": 0,
        }
        assert ledger["timeline"] == []
        assert ledger["characters"] == []
        assert ledger["threads"] == []


def test_an_unknown_project_is_reported(tmp_path: Path) -> None:
    database = Database((tmp_path / "data" / "novellire.db"))
    with _client(tmp_path, database) as client:
        response = client.get("/api/projects/999/continuity")

        assert response.status_code == 404
        assert "project" in response.json()["detail"].lower()
