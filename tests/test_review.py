"""Server-owned draft review: validated findings, refusals, and no writes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.core.review import REVIEW_SOURCE_CHARS
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class ReviewProvider:
    """Provider stub that returns one fixed review payload."""

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


def _project_chapter(client: TestClient, *, content: str = "", status: str = "drafting"):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "The Gate",
            "content": content,
            "status": status,
            "objectives": "1. Mira waits at the gate.",
        },
    ).json()
    return project, chapter


DRAFT = "Mira waited. The gate was open. The rain stopped."


def test_only_findings_that_quote_the_draft_once_are_kept(tmp_path: Path) -> None:
    provider = ReviewProvider(
        json.dumps(
            {
                "overall": "One continuity problem and one call for you.",
                "findings": [
                    {
                        "kind": "continuity",
                        "issue": "The gate contradicts canon.",
                        "quote": "The gate was open.",
                        "replacement": "The gate was barred.",
                        "reason": "Chapter 2 says it was barred.",
                    },
                    {
                        "kind": "prose",
                        "issue": "No actual change.",
                        "quote": "Mira waited.",
                        "replacement": "Mira waited.",
                        "reason": "Identical text is not a revision.",
                    },
                    {
                        "kind": "plan",
                        "issue": "Not in the draft.",
                        "quote": "Not in the draft.",
                        "replacement": "Anything.",
                        "reason": "Quotes must be verifiable.",
                    },
                    {
                        "kind": "unknown",
                        "issue": "The rain is a loose thread.",
                        "quote": "The rain stopped.",
                        "replacement": "",
                        "reason": "The author decides how to close it.",
                    },
                ],
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapter = _project_chapter(client, content="Mira waits by the gate.")

        response = client.post(
            f"/api/chapters/{chapter['id']}/review",
            json={"model": "fake-model", "draft": DRAFT},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["source"] == "draft"
        assert payload["reviewed_chars"] == len(DRAFT)
        assert payload["overall"].startswith("One continuity problem")
        findings = payload["findings"]
        assert [finding["id"] for finding in findings] == [1, 2]
        assert findings[0]["kind"] == "continuity"
        assert findings[0]["quote"] == "The gate was open."
        assert findings[0]["replacement"] == "The gate was barred."
        assert findings[1]["kind"] == "prose"
        assert findings[1]["replacement"] == ""

        prompt = provider.requests[0].prompt
        assert f"Draft to review:\n{DRAFT}" in prompt
        assert "Chapter plan:\n1. Mira waits at the gate." in prompt

        stored = client.get(f"/api/projects/{project['id']}/manuscript").json()
        assert stored["chapters"][0]["content"] == "Mira waits by the gate."


def test_a_saved_chapter_is_reviewed_without_a_draft(tmp_path: Path) -> None:
    provider = ReviewProvider(
        json.dumps({"overall": "Reads cleanly.", "findings": []})
    )
    with _client(tmp_path, provider) as client:
        _, chapter = _project_chapter(client, content="Mira waits by the gate.")

        response = client.post(
            f"/api/chapters/{chapter['id']}/review", json={"model": "fake-model"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["source"] == "chapter"
        assert response.json()["findings"] == []
        assert "Draft to review:\nMira waits by the gate." in provider.requests[0].prompt


def test_review_refuses_empty_oversized_or_unmodelled_prose(tmp_path: Path) -> None:
    provider = ReviewProvider(json.dumps({"overall": "", "findings": []}))
    with _client(tmp_path, provider) as client:
        _, empty = _project_chapter(client)

        missing = client.post(
            f"/api/chapters/{empty['id']}/review", json={"model": "fake-model"}
        )
        assert missing.status_code == 400
        assert "Add chapter text" in missing.json()["detail"]

        oversized = client.post(
            f"/api/chapters/{empty['id']}/review",
            json={"model": "fake-model", "draft": "word " * 4_000},
        )
        assert oversized.status_code == 400
        assert f"{REVIEW_SOURCE_CHARS:,}" in oversized.json()["detail"]

        unmodelled = client.post(
            f"/api/chapters/{empty['id']}/review",
            json={"model": "", "draft": "Mira waits."},
        )
        assert unmodelled.status_code == 400
        assert "model" in unmodelled.json()["detail"]

        assert provider.requests == []


def test_a_malformed_review_is_reported_without_touching_the_chapter(
    tmp_path: Path,
) -> None:
    provider = ReviewProvider("I am not able to return JSON today.")
    with _client(tmp_path, provider) as client:
        _, chapter = _project_chapter(client, content="Mira waits by the gate.")

        response = client.post(
            f"/api/chapters/{chapter['id']}/review", json={"model": "fake-model"}
        )

        assert response.status_code == 502, response.text
        assert "review JSON" in response.json()["detail"]

        stored = client.get(
            f"/api/projects/{chapter['project_id']}/manuscript"
        ).json()
        assert stored["chapters"][0]["content"] == "Mira waits by the gate."


def test_an_approved_chapter_can_still_be_reviewed(tmp_path: Path) -> None:
    provider = ReviewProvider(
        json.dumps({"overall": "Solid.", "findings": []})
    )
    with _client(tmp_path, provider) as client:
        _, chapter = _project_chapter(
            client, content="Mira waits by the gate.", status="approved"
        )

        response = client.post(
            f"/api/chapters/{chapter['id']}/review", json={"model": "fake-model"}
        )

        assert response.status_code == 200, response.text
        assert len(provider.requests) == 1
