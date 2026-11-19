"""Pre-draft discussion: bounded questions, refusals, and no writes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.core.discussion import DISCUSS_PLAN_CHARS, DISCUSS_MAX_QUESTIONS
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class DiscussionProvider:
    """Provider stub that returns one fixed discussion payload."""

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
    app = create_app(
        settings=settings,
        database=Database(settings.database_path),
        provider=provider,
    )
    return TestClient(app)


def _chapter(client: TestClient, *, objectives: str = "", status: str = "planned"):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "objectives": objectives, "status": status},
    ).json()
    return project, chapter


PLAN = "1. Mira waits at the gate.\n2. Orin arrives with the key."


def test_discussion_returns_bounded_deduplicated_questions(tmp_path: Path) -> None:
    provider = DiscussionProvider(
        json.dumps(
            {
                "ready": False,
                "summary": "The plan needs a decision about the key.",
                "questions": [
                    {
                        "question": "Does Orin know Mira is at the gate?",
                        "why": "His first line changes completely.",
                    },
                    {
                        "question": "does orin know mira is at the gate?",
                        "why": "Duplicate wording.",
                    },
                    {"question": "   ", "why": "Empty questions are dropped."},
                    "What does the key open?",
                ],
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapter = _chapter(client, objectives=PLAN)

        response = client.post(
            f"/api/chapters/{chapter['id']}/discuss", json={"model": "fake-model"}
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ready"] is False
        assert payload["summary"].startswith("The plan needs a decision")
        questions = payload["questions"]
        assert [question["id"] for question in questions] == [1, 2]
        assert questions[0]["question"] == "Does Orin know Mira is at the gate?"
        assert questions[1]["question"] == "What does the key open?"
        assert questions[1]["why"] == ""

        prompt = provider.requests[0].prompt
        assert PLAN in prompt
        assert "Return the JSON discussion." in prompt
        assert len(provider.requests) == 1

        stored = client.get(f"/api/projects/{project['id']}/chapters").json()
        assert stored[0]["objectives"].strip() == PLAN


def test_a_plan_without_beats_is_refused(tmp_path: Path) -> None:
    provider = DiscussionProvider(json.dumps({"ready": True}))
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter(client)

        response = client.post(
            f"/api/chapters/{chapter['id']}/discuss", json={"model": "fake-model"}
        )

        assert response.status_code == 400, response.text
        assert "scene plan" in response.json()["detail"]
        assert provider.requests == []


def test_an_oversized_plan_or_missing_model_is_refused(tmp_path: Path) -> None:
    provider = DiscussionProvider(json.dumps({"ready": True}))
    plan = "beat " * (DISCUSS_PLAN_CHARS // 5 + 50)
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter(client, objectives=plan)

        oversized = client.post(
            f"/api/chapters/{chapter['id']}/discuss", json={"model": "fake-model"}
        )
        assert oversized.status_code == 400
        assert f"{DISCUSS_PLAN_CHARS:,}" in oversized.json()["detail"]

        planned = client.post(
            f"/api/projects/{chapter['project_id']}/chapters",
            json={"title": "Second Gate", "objectives": PLAN},
        ).json()
        unmodelled = client.post(
            f"/api/chapters/{planned['id']}/discuss", json={"model": ""}
        )
        assert unmodelled.status_code == 400
        assert "model" in unmodelled.json()["detail"]

        assert provider.requests == []


def test_a_malformed_discussion_is_reported(tmp_path: Path) -> None:
    provider = DiscussionProvider("Sure, here are some questions...")
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter(client, objectives=PLAN)

        response = client.post(
            f"/api/chapters/{chapter['id']}/discuss", json={"model": "fake-model"}
        )

        assert response.status_code == 502, response.text
        assert "plan-discussion JSON" in response.json()["detail"]


def test_questions_are_capped_at_the_discussion_limit(tmp_path: Path) -> None:
    provider = DiscussionProvider(
        json.dumps(
            {
                "ready": False,
                "questions": [
                    {"question": f"Question {index}?", "why": "Because."}
                    for index in range(1, DISCUSS_MAX_QUESTIONS + 4)
                ],
            }
        )
    )
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter(client, objectives=PLAN)

        payload = client.post(
            f"/api/chapters/{chapter['id']}/discuss", json={"model": "fake-model"}
        ).json()

        assert len(payload["questions"]) == DISCUSS_MAX_QUESTIONS
