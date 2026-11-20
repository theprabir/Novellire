"""Canon-change review: earlier state records superseded with provenance."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class UnusedProvider:
    """Review, marking, and the ledger never call a model."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("canon-change review must not run inference")


class QuietProvider:
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


def _project(client: TestClient, *, chapters: int) -> tuple[dict, list]:
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    rows = [
        client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": f"Scene {index}"},
        ).json()
        for index in range(1, chapters + 1)
    ]
    return project, rows


def _character(client: TestClient, project_id: int, name: str) -> int:
    response = client.post(
        f"/api/projects/{project_id}/characters", json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _state(
    client: TestClient,
    project_id: int,
    *,
    character_id: int,
    chapter_id: int,
    **fields,
) -> dict:  # noqa: ANN202
    response = client.post(
        f"/api/projects/{project_id}/character-states",
        json={"character_id": character_id, "chapter_id": chapter_id, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_review_lists_changed_records_and_skips_unchanged_pairs(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, UnusedProvider()) as client:
        project, chapters = _project(client, chapters=3)
        mira = _character(client, project["id"], "Mira")
        first = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[0]["id"],
            location="the camp",
            knowledge="Orin has not arrived.",
        )
        second = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[1]["id"],
            location="the gate",
            knowledge="The key opens the gate.",
        )
        _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[2]["id"],
            location="the gate",
            knowledge="The key opens the gate.",
        )

        payload = client.get(f"/api/projects/{project['id']}/supersessions").json()

        assert payload["counts"] == {
            "characters": 1,
            "changes": 1,
            "superseded": 0,
            "pending": 1,
        }
        change = payload["changes"][0]
        assert change["earlier_id"] == first["id"]
        assert change["later_id"] == second["id"]
        assert change["character_name"] == "Mira"
        assert change["earlier_chapter_position"] == 1
        assert change["later_chapter_position"] == 2
        assert sorted(change["changed"]) == ["knowledge", "location"]
        assert change["earlier_details"]["location"] == "the camp"
        assert change["later_details"]["location"] == "the gate"
        assert change["superseded"] is False
        assert change["note"] == ""


def test_superseded_record_is_kept_in_the_ledger_but_not_cited_as_canon(
    tmp_path: Path,
) -> None:
    provider = QuietProvider(json.dumps({"findings": []}))
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client, chapters=2)
        mira = _character(client, project["id"], "Mira")
        earlier = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[0]["id"],
            location="the camp",
            knowledge="Orin has not arrived.",
        )
        later = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[1]["id"],
            location="the gate",
            knowledge="The key opens the gate.",
        )
        client.patch(
            f"/api/chapters/{chapters[1]['id']}",
            json={"content": "Mira reaches the gate at dusk."},
        )

        marked = client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={
                "earlier_id": earlier["id"],
                "later_id": later["id"],
                "note": "Mira left the camp in chapter one.",
            },
        )
        assert marked.status_code == 200, marked.text
        assert marked.json()["superseded"] is True
        assert marked.json()["decision"]["record_kind"] == "state"

        review = client.get(f"/api/projects/{project['id']}/supersessions").json()
        assert review["counts"]["pending"] == 0
        assert review["counts"]["superseded"] == 1
        assert review["changes"][0]["note"] == "Mira left the camp in chapter one."

        ledger = client.get(f"/api/projects/{project['id']}/continuity").json()
        snapshots = ledger["characters"][0]["snapshots"]
        assert len(snapshots) == 2
        assert snapshots[0]["superseded"] is True
        assert snapshots[0]["superseded_by_chapter_position"] == 2
        assert snapshots[0]["superseded_by_chapter_title"] == "Scene 2"
        assert snapshots[0]["supersession_note"] == "Mira left the camp in chapter one."
        assert snapshots[0]["location"] == "the camp"
        assert snapshots[1]["superseded"] is False

        checked = client.post(
            f"/api/chapters/{chapters[1]['id']}/continuity",
            json={"model": "fake-model"},
        )
        assert checked.status_code == 200, checked.text
        prompt = provider.requests[0].prompt
        assert "location: the gate" in prompt
        assert "the camp" not in prompt


def test_marking_again_updates_the_note_and_undo_clears_it(tmp_path: Path) -> None:
    with _client(tmp_path, UnusedProvider()) as client:
        project, chapters = _project(client, chapters=2)
        mira = _character(client, project["id"], "Mira")
        earlier = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[0]["id"],
            location="the camp",
        )
        later = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[1]["id"],
            location="the gate",
        )

        payload = {
            "earlier_id": earlier["id"],
            "later_id": later["id"],
            "superseded": True,
        }
        client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={**payload, "note": "First note."},
        )
        client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={**payload, "note": "Corrected note."},
        )

        review = client.get(f"/api/projects/{project['id']}/supersessions").json()
        assert review["counts"]["changes"] == 1
        assert review["counts"]["superseded"] == 1
        assert review["changes"][0]["note"] == "Corrected note."

        undone = client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={**payload, "superseded": False},
        )
        assert undone.status_code == 200, undone.text
        assert undone.json() == {"superseded": False, "decision": None}

        review = client.get(f"/api/projects/{project['id']}/supersessions").json()
        assert review["counts"]["superseded"] == 0
        assert review["changes"][0]["note"] == ""
        ledger = client.get(f"/api/projects/{project['id']}/continuity").json()
        assert ledger["characters"][0]["snapshots"][0]["superseded"] is False


def test_supersession_validates_the_pair_and_the_project(tmp_path: Path) -> None:
    with _client(tmp_path, UnusedProvider()) as client:
        project, chapters = _project(client, chapters=2)
        mira = _character(client, project["id"], "Mira")
        orin = _character(client, project["id"], "Orin")
        first = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[0]["id"],
            location="the camp",
        )
        second = _state(
            client,
            project["id"],
            character_id=mira,
            chapter_id=chapters[1]["id"],
            location="the gate",
        )
        other_character = _state(
            client,
            project["id"],
            character_id=orin,
            chapter_id=chapters[1]["id"],
            location="the keep",
        )

        mixed = client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={"earlier_id": first["id"], "later_id": other_character["id"]},
        )
        assert mixed.status_code == 400
        assert "same character" in mixed.json()["detail"]

        reversed_pair = client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={"earlier_id": second["id"], "later_id": first["id"]},
        )
        assert reversed_pair.status_code == 400

        other = client.post("/api/projects", json={"name": "Elsewhere"}).json()
        other_chapter = client.post(
            f"/api/projects/{other['id']}/chapters", json={"title": "Far away"}
        ).json()
        foreign = client.post(
            f"/api/projects/{other['id']}/characters", json={"name": "Orin"}
        ).json()
        foreign_state = _state(
            client,
            other["id"],
            character_id=foreign["id"],
            chapter_id=other_chapter["id"],
            location="the void",
        )

        cross_project = client.put(
            f"/api/projects/{project['id']}/supersessions",
            json={"earlier_id": first["id"], "later_id": foreign_state["id"]},
        )
        assert cross_project.status_code == 404

        missing = client.get("/api/projects/999/supersessions")
        assert missing.status_code == 404
