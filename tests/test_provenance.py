"""Provenance on findings: every cited canon record names where it came from."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database
from novellire.storage.event_repository import EventDraft, EventRepository


class CitingProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return GenerationResult(text=self.text, model="fake-model", duration_ms=5)


def _client(tmp_path: Path, provider) -> TestClient:  # noqa: ANN001
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(
            settings=settings,
            database=Database(settings.database_path),
            provider=provider,
        )
    )


def _project(client: TestClient, *, chapters: int = 2):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    rows = [
        client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": f"Scene {index}"},
        ).json()
        for index in range(1, chapters + 1)
    ]
    return project, rows


def _state(
    client: TestClient, project_id: int, *, character_id: int, chapter_id: int, **fields
) -> dict:  # noqa: ANN202
    response = client.post(
        f"/api/projects/{project_id}/character-states",
        json={"character_id": character_id, "chapter_id": chapter_id, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_continuity_finding_carries_the_source_chapter_and_kind(
    tmp_path: Path,
) -> None:
    provider = CitingProvider(
        json.dumps(
            {
                "findings": [
                    {
                        "kind": "location",
                        "severity": "high",
                        "quote": "Mira rode through the dawn gate.",
                        "source": "C1",
                        "explanation": "Mira is still in the siege camp.",
                        "suggestion": "Move the ride after the camp scene.",
                    }
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = client.post(
            f"/api/projects/{project['id']}/characters", json={"name": "Mira"}
        ).json()
        _state(
            client,
            project["id"],
            character_id=mira["id"],
            chapter_id=chapters[0]["id"],
            location="the siege camp",
        )
        client.patch(
            f"/api/chapters/{chapters[1]['id']}",
            json={"content": "Mira rode through the dawn gate.", "status": "drafted"},
        )

        response = client.post(
            f"/api/chapters/{chapters[1]['id']}/continuity",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        finding = response.json()["findings"][0]
        assert finding["source_id"] == "C1"
        assert finding["source_kind"] == "state"
        assert finding["source_chapter_position"] == 1
        assert finding["source_chapter_title"] == "Scene 1"
        assert "chapter 1" in finding["source"]


def test_scan_findings_carry_provenance_for_both_records(tmp_path: Path) -> None:
    provider = CitingProvider(
        json.dumps(
            {
                "findings": [
                    {
                        "kind": "location",
                        "severity": "high",
                        "source_a": "C1",
                        "source_b": "C2",
                        "summary": "Mira is in two places at once.",
                        "detail": "Two records disagree.",
                    }
                ]
            }
        )
    )
    database = Database(tmp_path / "data" / "novellire.db")
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = client.post(
            f"/api/projects/{project['id']}/characters", json={"name": "Mira"}
        ).json()
        _state(
            client,
            project["id"],
            character_id=mira["id"],
            chapter_id=chapters[0]["id"],
            location="the siege camp",
        )
        EventRepository(database).replace_for_chapter(
            project["id"],
            chapters[1]["id"],
            [
                EventDraft(
                    summary="Mira reaches the gate.",
                    characters=("Mira",),
                    locations=("the gate",),
                )
            ],
            model="fake-model",
        )

        response = client.post(
            f"/api/projects/{project['id']}/contradictions/scan",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        finding = response.json()["findings"][0]
        sources = {
            finding["source_a"]: (
                finding["source_a_kind"],
                finding["source_a_chapter_position"],
                finding["source_a_chapter_title"],
            ),
            finding["source_b"]: (
                finding["source_b_kind"],
                finding["source_b_chapter_position"],
                finding["source_b_chapter_title"],
            ),
        }
        assert sources["C1"] == ("state", 1, "Scene 1")
        assert sources["C2"] == ("event", 2, "Scene 2")


def test_a_bible_record_has_a_kind_without_a_chapter(tmp_path: Path) -> None:
    provider = CitingProvider(
        json.dumps(
            {
                "findings": [
                    {
                        "kind": "world",
                        "severity": "medium",
                        "quote": "The gate opened at dawn.",
                        "source": "C1",
                        "explanation": "The gate is sealed.",
                    }
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        entry = client.post(
            f"/api/projects/{project['id']}/bible",
            json={
                "category": "world_building",
                "title": "The northern gate",
                "content": "The gate is sealed until the last chapter.",
            },
        )
        assert entry.status_code == 201, entry.text
        client.patch(
            f"/api/chapters/{chapters[1]['id']}",
            json={"content": "The gate opened at dawn.", "status": "drafted"},
        )

        response = client.post(
            f"/api/chapters/{chapters[1]['id']}/continuity",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        finding = response.json()["findings"][0]
        assert finding["source_kind"] == "bible"
        assert finding["source_chapter_position"] is None
        assert finding["source_chapter_title"] == ""
