"""Timeline validation: recorded story days against chapter order."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import ModelInfo
from novellire.storage.database import Database


class UnusedProvider:
    """Timeline validation never calls a model; fail loudly if it does."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("timeline validation must not run inference")


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(
            settings=settings,
            database=Database(tmp_path / "data" / "novellire.db"),
            provider=UnusedProvider(),
        )
    )


def _project(client: TestClient, name: str = "Ashfall") -> int:
    return client.post("/api/projects", json={"name": name}).json()["id"]


def _chapter(
    client: TestClient, project_id: int, title: str, story_day: int | None = None
) -> dict:
    payload: dict[str, object] = {"title": title}
    if story_day is not None:
        payload["story_day"] = story_day
    response = client.post(
        f"/api/projects/{project_id}/chapters", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_anchors_report_elapsed_story_days(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        _chapter(client, project_id, "The Gate", 0)
        _chapter(client, project_id, "The Key", 2)
        _chapter(client, project_id, "The Well", 2)

        validation = client.get(f"/api/projects/{project_id}/timeline").json()

        assert validation["counts"] == {
            "chapters": 3,
            "anchored": 3,
            "unanchored": 0,
            "findings": 0,
        }
        assert [anchor["story_day"] for anchor in validation["anchors"]] == [0, 2, 2]
        assert [anchor["elapsed"] for anchor in validation["anchors"]] == [None, 2, 0]
        assert validation["findings"] == []


def test_a_chapter_running_backwards_is_reported(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        _chapter(client, project_id, "The Gate", 0)
        _chapter(client, project_id, "The Key", 5)
        _chapter(client, project_id, "The Well", 3)

        validation = client.get(f"/api/projects/{project_id}/timeline").json()

        assert validation["counts"]["findings"] == 1
        finding = validation["findings"][0]
        assert finding["kind"] == "out_of_order"
        assert finding["severity"] == "high"
        assert finding["position"] == 3
        assert finding["story_day"] == 3
        assert finding["previous_position"] == 2
        assert finding["previous_day"] == 5
        assert "flashback" in finding["detail"]


def test_unanchored_chapters_are_counted_not_flagged(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        _chapter(client, project_id, "The Gate", 1)
        _chapter(client, project_id, "The Key")
        _chapter(client, project_id, "The Well", 4)

        validation = client.get(f"/api/projects/{project_id}/timeline").json()

        assert validation["counts"]["anchored"] == 2
        assert validation["counts"]["unanchored"] == 1
        assert validation["findings"] == []
        assert validation["anchors"][1]["story_day"] is None
        assert validation["anchors"][1]["elapsed"] is None
        assert validation["anchors"][2]["elapsed"] == 3


def test_a_story_day_can_be_changed_and_cleared(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        chapter = _chapter(client, project_id, "The Gate")

        updated = client.patch(
            f"/api/chapters/{chapter['id']}", json={"story_day": 7}
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["story_day"] == 7

        cleared = client.patch(
            f"/api/chapters/{chapter['id']}", json={"story_day": None}
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["story_day"] is None

        rejected = client.patch(
            f"/api/chapters/{chapter['id']}", json={"story_day": -1}
        )
        assert rejected.status_code == 400
        assert "zero or greater" in rejected.json()["detail"]


def test_an_unknown_project_is_reported(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/projects/999/timeline")

        assert response.status_code == 404
        assert "project" in response.json()["detail"].lower()
