"""Continuity check: cited canon, validated quotes, bounded findings."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.core.continuity import CONTINUITY_MAX_FINDINGS
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database


class ContinuityProvider:
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


TEXT = (
    "Mira rode through the dawn gate. "
    "The gate key hung at her belt."
)


def _chapter_with_canon(client: TestClient, *, text: str = TEXT):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "objectives": "Mira enters the city."},
    ).json()
    saved = client.patch(
        f"/api/chapters/{chapter['id']}",
        json={"content": text},
    )
    assert saved.status_code == 200, saved.text
    character = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "Mira"},
    ).json()
    state = client.post(
        f"/api/projects/{project['id']}/character-states",
        json={
            "character_id": character["id"],
            "chapter_id": chapter["id"],
            "location": "the siege camp",
        },
    )
    assert state.status_code == 201, state.text
    return project, chapter


def _finding(**overrides) -> dict:
    finding = {
        "kind": "location",
        "severity": "high",
        "quote": "Mira rode through the dawn gate.",
        "source": "C1",
        "explanation": "Mira is still in the siege camp.",
        "suggestion": "Move the ride after the camp scene.",
    }
    finding.update(overrides)
    return finding


def test_findings_keep_only_cited_canon_and_unique_quotes(tmp_path: Path) -> None:
    provider = ContinuityProvider(
        json.dumps(
            {
                "findings": [
                    _finding(),
                    _finding(),
                    _finding(source="C99", quote="The gate key hung at her belt."),
                    _finding(quote="Mira flew over the wall."),
                    _finding(
                        quote="The gate key hung at her belt.",
                        severity="SEVERE",
                        kind="vibes",
                    ),
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter_with_canon(client)

        response = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": "fake-model"}
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["canon_count"] == 1
        findings = payload["findings"]
        assert [finding["id"] for finding in findings] == [1, 2]
        assert findings[0]["source_id"] == "C1"
        assert "Mira" in findings[0]["source"]
        assert "chapter 1" in findings[0]["source"]
        assert findings[0]["severity"] == "high"
        assert findings[1]["severity"] == "medium"
        assert findings[1]["kind"] == "other"

        prompt = provider.requests[0].prompt
        assert "C1: Character state · Mira" in prompt
        assert TEXT in prompt
        assert "Return the JSON continuity report." in prompt
        assert len(provider.requests) == 1


def test_findings_are_capped_and_idempotent(tmp_path: Path) -> None:
    text = " ".join(f"Sentence {index} happens." for index in range(1, 9))
    provider = ContinuityProvider(
        json.dumps(
            {
                "findings": [
                    _finding(quote=f"Sentence {index} happens.")
                    for index in range(1, 9)
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter_with_canon(client, text=text)

        payload = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": "fake-model"}
        ).json()

        assert len(payload["findings"]) == CONTINUITY_MAX_FINDINGS


def test_an_empty_chapter_is_refused(tmp_path: Path) -> None:
    provider = ContinuityProvider(json.dumps({"findings": []}))
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters", json={"title": "Empty"}
        ).json()

        response = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": "fake-model"}
        )

        assert response.status_code == 400
        assert "before checking" in response.json()["detail"]
        assert provider.requests == []


def test_a_chapter_without_canon_is_refused(tmp_path: Path) -> None:
    provider = ContinuityProvider(json.dumps({"findings": []}))
    with _client(tmp_path, provider) as client:
        project = client.post("/api/projects", json={"name": "Ashfall"}).json()
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters", json={"title": "Alone"}
        ).json()
        client.patch(f"/api/chapters/{chapter['id']}", json={"content": TEXT})

        response = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": "fake-model"}
        )

        assert response.status_code == 400
        assert "character state" in response.json()["detail"]
        assert provider.requests == []


def test_a_malformed_report_and_missing_model_are_reported(tmp_path: Path) -> None:
    provider = ContinuityProvider("Looks consistent to me.")
    with _client(tmp_path, provider) as client:
        _, chapter = _chapter_with_canon(client)

        malformed = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": "fake-model"}
        )
        assert malformed.status_code == 502
        assert "continuity JSON" in malformed.json()["detail"]

        unmodelled = client.post(
            f"/api/chapters/{chapter['id']}/continuity", json={"model": ""}
        )
        assert unmodelled.status_code == 400
        assert "model" in unmodelled.json()["detail"]
        assert len(provider.requests) == 1
