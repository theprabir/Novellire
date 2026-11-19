"""State proposals: validated names and fields, applied only on request."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class ProposalProvider:
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


TEXT = "Mira reaches the gate. The key is warm in her hand."


def _project(client: TestClient, *, content: str = TEXT):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "The Gate"}
    ).json()
    saved = client.patch(f"/api/chapters/{chapter['id']}", json={"content": content})
    assert saved.status_code == 200, saved.text
    return project, chapter


def _mira(client: TestClient, project_id: int) -> int:
    response = client.post(
        f"/api/projects/{project_id}/characters",
        json={"name": "Mira", "aliases": ["Captain Vale"]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_proposals_resolve_names_and_drop_unknowns(tmp_path: Path) -> None:
    provider = ProposalProvider(
        json.dumps(
            {
                "updates": [
                    {
                        "character": "Mira",
                        "location": "the gate",
                        "status": "",
                        "goals": "",
                        "knowledge": "The key opens the northern gate.",
                    },
                    {
                        "character": "  captain   vale ",
                        "location": "elsewhere",
                    },
                    {"character": "Ghost", "location": "the void"},
                    {"character": "Mira", "location": "", "knowledge": ""},
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapter = _project(client)
        _mira(client, project["id"])

        response = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        proposals = response.json()["proposals"]
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal["character_name"] == "Mira"
        assert proposal["location"] == "the gate"
        assert proposal["existing_state_id"] is None
        assert "The key opens the northern gate." in proposal["knowledge"]

        prompt = provider.requests[0].prompt
        assert "Mira" in prompt
        assert "Captain Vale" in prompt
        assert "Return the JSON state updates." in prompt


def test_proposals_refuse_a_chapter_without_characters(tmp_path: Path) -> None:
    provider = ProposalProvider(json.dumps({"updates": []}))
    with _client(tmp_path, provider) as client:
        _, chapter = _project(client)

        response = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals",
            json={"model": "fake-model"},
        )

        assert response.status_code == 400
        assert "characters" in response.json()["detail"]
        assert provider.requests == []


def test_proposals_refuse_an_empty_chapter_and_report_bad_json(tmp_path: Path) -> None:
    provider = ProposalProvider("No changes.")
    with _client(tmp_path, provider) as client:
        project, chapter = _project(client, content="")
        _mira(client, project["id"])

        empty = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals",
            json={"model": "fake-model"},
        )
        assert empty.status_code == 400
        assert provider.requests == []

        client.patch(f"/api/chapters/{chapter['id']}", json={"content": TEXT})
        malformed = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals",
            json={"model": "fake-model"},
        )
        assert malformed.status_code == 502
        assert "state-update JSON" in malformed.json()["detail"]


def test_applying_creates_then_updates_one_snapshot(tmp_path: Path) -> None:
    provider = ProposalProvider(
        json.dumps(
            {
                "updates": [
                    {
                        "character": "Mira",
                        "location": "the gate",
                        "knowledge": "The key opens the gate.",
                    }
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapter = _project(client)
        mira = _mira(client, project["id"])

        first = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals/apply",
            json={
                "updates": [
                    {
                        "character_id": mira,
                        "location": "the gate",
                        "knowledge": "The key opens the gate.",
                    }
                ]
            },
        )
        assert first.status_code == 200, first.text
        assert len(first.json()["states"]) == 1
        assert first.json()["states"][0]["chapter_position"] == 1

        second = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals/apply",
            json={
                "updates": [
                    {
                        "character_id": mira,
                        "location": "the keep",
                        "knowledge": "The key opens the northern gate.",
                    }
                ]
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["states"][0]["location"] == "the keep"

        states = client.get(f"/api/projects/{project['id']}/character-states").json()
        assert len(states) == 1
        assert states[0]["location"] == "the keep"

        proposals = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals",
            json={"model": "fake-model"},
        ).json()["proposals"]
        assert proposals[0]["existing_state_id"] == states[0]["id"]


def test_apply_validates_characters_and_empty_updates(tmp_path: Path) -> None:
    provider = ProposalProvider(json.dumps({"updates": []}))
    with _client(tmp_path, provider) as client:
        project, chapter = _project(client)
        other = client.post("/api/projects", json={"name": "Elsewhere"}).json()
        foreign = client.post(
            f"/api/projects/{other['id']}/characters", json={"name": "Orin"}
        ).json()

        empty = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals/apply",
            json={"updates": []},
        )
        assert empty.status_code == 400

        unknown = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals/apply",
            json={
                "updates": [
                    {"character_id": foreign["id"], "location": "the gate"}
                ]
            },
        )
        assert unknown.status_code == 400

        blank = client.post(
            f"/api/chapters/{chapter['id']}/state-proposals/apply",
            json={"updates": [{"character_id": 9999}]},
        )
        assert blank.status_code == 400
