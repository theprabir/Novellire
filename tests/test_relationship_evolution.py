"""Relationship evolution: resolved pairs, reviewed changes, chapter history."""

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


TEXT = "Mira refuses Orin's hand. The gate stays shut between them."


def _project(client: TestClient, *, content: str = TEXT, chapters: int = 1):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    rows = [
        client.post(
            f"/api/projects/{project['id']}/chapters", json={"title": f"Scene {index}"}
        ).json()
        for index in range(1, chapters + 1)
    ]
    saved = client.patch(f"/api/chapters/{rows[0]['id']}", json={"content": content})
    assert saved.status_code == 200, saved.text
    return project, rows


def _character(client: TestClient, project_id: int, name: str, aliases=()):  # noqa: ANN001, ANN202
    response = client.post(
        f"/api/projects/{project_id}/characters",
        json={"name": name, "aliases": list(aliases)},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _relationship(
    client: TestClient, project_id: int, first: int, second: int, *, status: str = ""
) -> dict:  # noqa: ANN202
    created = client.post(
        f"/api/projects/{project_id}/relationship-records",
        json={
            "character_a_id": first,
            "character_b_id": second,
            "relation_type": "ally",
            "description": "They hold the gate together.",
        },
    )
    assert created.status_code == 201, created.text
    record = created.json()
    if status:
        approved = client.patch(
            f"/api/relationship-records/{record['id']}/status",
            json={"status": status},
        )
        assert approved.status_code == 200, approved.text
        record = approved.json()
    return record


def test_proposals_resolve_pairs_and_match_recorded_relationships(tmp_path: Path) -> None:
    provider = ProposalProvider(
        json.dumps(
            {
                "relationships": [
                    {
                        "character_a": "orin",
                        "character_b": "  captain   vale ",
                        "relation_type": "Rival",
                        "description": "Orin no longer trusts Mira.",
                    },
                    {
                        "character_a": "Mira",
                        "character_b": "Mira",
                        "relation_type": "ally",
                        "description": "Mira trusts herself.",
                    },
                    {
                        "character_a": "Ghost",
                        "character_b": "Mira",
                        "relation_type": "ally",
                        "description": "Unknown character.",
                    },
                    {
                        "character_a": "Orin",
                        "character_b": "Captain Vale",
                        "relation_type": "ally",
                        "description": "A duplicate of the first pair.",
                    },
                    {
                        "character_a": "Mira",
                        "character_b": "Orin",
                        "relation_type": "ally",
                        "description": "   ",
                    },
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = _character(client, project["id"], "Mira", ["Captain Vale"])
        orin = _character(client, project["id"], "Orin")
        record = _relationship(
            client, project["id"], mira, orin, status="approved"
        )

        response = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        proposals = response.json()["proposals"]
        assert len(proposals) == 1
        proposal = proposals[0]
        assert (proposal["character_a_id"], proposal["character_b_id"]) == (
            min(mira, orin),
            max(mira, orin),
        )
        assert proposal["character_a_name"] == "Mira"
        assert proposal["character_b_name"] == "Orin"
        assert proposal["relation_type"] == "rival"
        assert proposal["description"] == "Orin no longer trusts Mira."
        assert proposal["existing_relationship_id"] == record["id"]
        assert proposal["existing_status"] == "approved"

        prompt = provider.requests[0].prompt
        assert "Mira" in prompt
        assert "Captain Vale" in prompt
        assert "They hold the gate together." in prompt
        assert "Return the JSON relationship changes." in prompt


def test_proposals_refuse_a_chapter_with_fewer_than_two_characters(
    tmp_path: Path,
) -> None:
    provider = ProposalProvider(json.dumps({"relationships": []}))
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        _character(client, project["id"], "Mira")

        response = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals",
            json={"model": "fake-model"},
        )

        assert response.status_code == 400
        assert "two characters" in response.json()["detail"]
        assert provider.requests == []


def test_proposals_refuse_an_empty_chapter_and_report_bad_json(
    tmp_path: Path,
) -> None:
    provider = ProposalProvider("No changes.")
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client, content="")
        _character(client, project["id"], "Mira")
        _character(client, project["id"], "Orin")

        empty = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals",
            json={"model": "fake-model"},
        )
        assert empty.status_code == 400
        assert provider.requests == []

        client.patch(f"/api/chapters/{chapters[0]['id']}", json={"content": TEXT})
        malformed = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals",
            json={"model": "fake-model"},
        )
        assert malformed.status_code == 502
        assert "relationship JSON" in malformed.json()["detail"]


def test_applying_records_one_snapshot_per_relationship_and_chapter(
    tmp_path: Path,
) -> None:
    provider = ProposalProvider(json.dumps({"relationships": []}))
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client, chapters=2)
        client.patch(f"/api/chapters/{chapters[1]['id']}", json={"content": TEXT})
        mira = _character(client, project["id"], "Mira")
        orin = _character(client, project["id"], "Orin")

        first = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": orin,
                        "character_b_id": mira,
                        "relation_type": "rival",
                        "description": "Orin stops trusting Mira.",
                    }
                ]
            },
        )
        assert first.status_code == 200, first.text
        assert first.json()["relationships"][0]["status"] == "proposed"
        assert first.json()["snapshots"][0]["chapter_position"] == 1

        second = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": mira,
                        "character_b_id": orin,
                        "relation_type": "debt",
                        "description": "Mira owes Orin a life.",
                    }
                ]
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["relationships"][0]["relation_type"] == "debt"

        third = client.post(
            f"/api/chapters/{chapters[1]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": mira,
                        "character_b_id": orin,
                        "relation_type": "ally",
                        "description": "They agree to hold the gate.",
                    }
                ]
            },
        )
        assert third.status_code == 200, third.text

        records = client.get(
            f"/api/projects/{project['id']}/relationship-records"
        ).json()
        assert len(records) == 1
        assert records[0]["description"] == "They agree to hold the gate."

        ledger = client.get(f"/api/projects/{project['id']}/continuity").json()
        assert ledger["counts"]["relationships"] == 1
        assert ledger["counts"]["relationship_changes"] == 2
        row = ledger["relationships"][0]
        assert row["character_a_name"] == "Mira"
        assert row["character_b_name"] == "Orin"
        assert [snapshot["chapter_position"] for snapshot in row["history"]] == [1, 2]
        assert sorted(row["history"][0]["changed"]) == ["description", "relation_type"]
        assert sorted(row["history"][1]["changed"]) == ["description", "relation_type"]
        assert row["history"][1]["relation_type"] == "ally"


def test_apply_validates_pairs_and_empty_updates(tmp_path: Path) -> None:
    provider = ProposalProvider(json.dumps({"relationships": []}))
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = _character(client, project["id"], "Mira")
        other = client.post("/api/projects", json={"name": "Elsewhere"}).json()
        foreign = _character(client, other["id"], "Orin")

        empty = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={"updates": []},
        )
        assert empty.status_code == 400

        same = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": mira,
                        "character_b_id": mira,
                        "relation_type": "ally",
                        "description": "Mira and herself.",
                    }
                ]
            },
        )
        assert same.status_code == 400

        unknown = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": mira,
                        "character_b_id": foreign,
                        "relation_type": "ally",
                        "description": "Not from this project.",
                    }
                ]
            },
        )
        assert unknown.status_code == 400

        bad_type = client.post(
            f"/api/chapters/{chapters[0]['id']}/relationship-proposals/apply",
            json={
                "updates": [
                    {
                        "character_a_id": mira,
                        "character_b_id": foreign,
                        "relation_type": "enemy",
                        "description": "Invalid type.",
                    }
                ]
            },
        )
        assert bad_type.status_code == 400
