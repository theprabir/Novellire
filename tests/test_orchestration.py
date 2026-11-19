"""Bounded scene-by-scene drafting: the server owns the loop."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.core.orchestration import MAX_SEQUENCE_SCENES, scene_beats
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class BeatProvider:
    """Provider stub that answers each scene with the next queued text."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.requests = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        text = self.texts.pop(0) if self.texts else "A quiet beat."
        return GenerationResult(text=text, model="fake-model", duration_ms=5)


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


def test_scene_beats_split_numbered_and_bulleted_plans() -> None:
    plan = (
        "1. Mira enters the square.\n"
        "   She is watched.\n"
        "- Orin waits by the gate.\n"
        "- The bell rings.\n"
    )

    assert scene_beats(plan) == [
        "Mira enters the square. She is watched.",
        "Orin waits by the gate.",
        "The bell rings.",
    ]
    assert scene_beats("One paragraph.\n\nAnother paragraph.") == [
        "One paragraph.",
        "Another paragraph.",
    ]
    assert scene_beats("   ") == []


def test_a_scene_plan_is_drafted_one_inference_at_a_time(tmp_path: Path) -> None:
    provider = BeatProvider(["Mira crosses the square.", "Orin shuts the gate."])
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "title": "The Gate",
                "objectives": "1. Mira crosses the square.\n2. Orin shuts the gate.",
                "target_word_count": 900,
            },
        ).json()

        response = client.post(
            f"/api/chapters/{chapter['id']}/draft-sequence",
            json={"model": "fake-model", "target_words": 400},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["output"] == (
            "Mira crosses the square.\n\nOrin shuts the gate."
        )
        assert payload["word_count"] == 8
        assert [scene["index"] for scene in payload["scenes"]] == [1, 2]
        assert payload["scenes"][1]["beat"] == "Orin shuts the gate."

        assert len(provider.requests) == 2
        assert "Scene 1 of 2. Mira crosses the square." in provider.requests[0].prompt
        assert "Scene 2 of 2. Orin shuts the gate." in provider.requests[1].prompt

        manuscript = client.get(
            f"/api/projects/{project['id']}/manuscript"
        ).json()
        assert manuscript["chapters"][0]["content"] == ""


def test_a_chapter_without_a_scene_plan_is_refused(tmp_path: Path) -> None:
    provider = BeatProvider([])
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": "The Gate"},
        ).json()

        response = client.post(
            f"/api/chapters/{chapter['id']}/draft-sequence",
            json={"model": "fake-model"},
        )

        assert response.status_code == 400, response.text
        assert "scene plan" in response.json()["detail"]
        assert provider.requests == []


def test_an_approved_chapter_is_not_drafted(tmp_path: Path) -> None:
    provider = BeatProvider([])
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "title": "The Gate",
                "objectives": "1. Mira crosses the square.",
                "status": "approved",
            },
        ).json()

        response = client.post(
            f"/api/chapters/{chapter['id']}/draft-sequence",
            json={"model": "fake-model"},
        )

        assert response.status_code == 400, response.text
        assert "approved" in response.json()["detail"]
        assert provider.requests == []


def test_a_plan_over_the_scene_limit_is_refused(tmp_path: Path) -> None:
    provider = BeatProvider([])
    beats = "\n".join(
        f"{index}. Beat {index}." for index in range(1, MAX_SEQUENCE_SCENES + 2)
    )
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": "The Gate", "objectives": beats},
        ).json()

        response = client.post(
            f"/api/chapters/{chapter['id']}/draft-sequence",
            json={"model": "fake-model"},
        )

        assert response.status_code == 400, response.text
        assert str(MAX_SEQUENCE_SCENES) in response.json()["detail"]
        assert provider.requests == []
