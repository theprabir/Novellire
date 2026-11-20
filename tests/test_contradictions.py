"""Contradiction detection: deterministic canon audit and cited read-only scan."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database
from novellire.storage.event_repository import EventDraft, EventRepository


class UnusedProvider:
    """The deterministic audit must never run inference."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("the contradiction audit must not run inference")


class ScanProvider:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.requests = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return GenerationResult(text=self.text, model="fake-model", duration_ms=5)


def _client(tmp_path: Path, provider, database: Database | None = None) -> TestClient:  # noqa: ANN001
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(
            settings=settings,
            database=database or Database(settings.database_path),
            provider=provider,
        )
    )


def _project(client: TestClient, *, chapters: int = 1):
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


def _relationship(
    client: TestClient,
    project_id: int,
    first: int,
    second: int,
    *,
    relation_type: str,
    status: str = "",
) -> dict:  # noqa: ANN202
    created = client.post(
        f"/api/projects/{project_id}/relationship-records",
        json={
            "character_a_id": first,
            "character_b_id": second,
            "relation_type": relation_type,
            "description": "Recorded for the audit.",
        },
    )
    assert created.status_code == 201, created.text
    record = created.json()
    if status:
        changed = client.patch(
            f"/api/relationship-records/{record['id']}/status",
            json={"status": status},
        )
        assert changed.status_code == 200, changed.text
        record = changed.json()
    return record


def _event(
    database: Database,
    project_id: int,
    chapter_id: int,
    *,
    summary: str,
    threads: tuple[str, ...],
) -> None:
    EventRepository(database).replace_for_chapter(
        project_id,
        chapter_id,
        [EventDraft(summary=summary, threads=threads)],
        model="fake-model",
    )


def test_audit_reports_conflicting_relationship_types(tmp_path: Path) -> None:
    provider = UnusedProvider()
    with _client(tmp_path, provider) as client:
        project, _ = _project(client)
        mira = _character(client, project["id"], "Mira")
        orin = _character(client, project["id"], "Orin")
        _relationship(
            client, project["id"], mira, orin, relation_type="ally", status="approved"
        )
        _relationship(
            client, project["id"], orin, mira, relation_type="rival", status="proposed"
        )
        rejected = _relationship(
            client, project["id"], mira, orin, relation_type="debt", status="rejected"
        )
        assert rejected["status"] == "rejected"

        response = client.get(f"/api/projects/{project['id']}/contradictions")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"] == {
            "relationships": 2,
            "thread_resolutions": 0,
            "findings": 1,
        }
        finding = payload["findings"][0]
        assert finding["kind"] == "conflicting_relationships"
        assert finding["severity"] == "high"
        assert "ally" in finding["summary"] and "rival" in finding["summary"]
        assert len(finding["sources"]) == 2
        assert all("Relationship #" in source for source in finding["sources"])


def test_audit_reports_a_thread_raised_after_its_resolution(tmp_path: Path) -> None:
    provider = UnusedProvider()
    database = Database(tmp_path / "data" / "novellire.db")
    with _client(tmp_path, provider, database) as client:
        project, chapters = _project(client, chapters=3)
        _event(
            database,
            project["id"],
            chapters[0]["id"],
            summary="Orin arrives with the key.",
            threads=("Who forged the key?",),
        )
        _event(
            database,
            project["id"],
            chapters[1]["id"],
            summary="Mira hides the key.",
            threads=("who forged the key?",),
        )
        _event(
            database,
            project["id"],
            chapters[2]["id"],
            summary="The smith confesses.",
            threads=("Who forged the key?",),
        )

        resolved = client.put(
            f"/api/projects/{project['id']}/threads",
            json={
                "thread": "Who forged the key?",
                "status": "resolved",
                "note": "The smith forged it.",
                "chapter_id": chapters[1]["id"],
            },
        )
        assert resolved.status_code == 200, resolved.text

        payload = client.get(
            f"/api/projects/{project['id']}/contradictions"
        ).json()
        assert payload["counts"]["thread_resolutions"] == 1
        assert payload["counts"]["findings"] == 1
        finding = payload["findings"][0]
        assert finding["kind"] == "thread_after_resolution"
        assert finding["severity"] == "medium"
        assert "chapter 2" in finding["summary"]
        assert len(finding["sources"]) == 2
        assert "chapter 3" in finding["sources"][1]

        later = client.put(
            f"/api/projects/{project['id']}/threads",
            json={
                "thread": "Who forged the key?",
                "status": "resolved",
                "chapter_id": chapters[2]["id"],
            },
        )
        assert later.status_code == 200, later.text
        settled = client.get(
            f"/api/projects/{project['id']}/contradictions"
        ).json()
        assert settled["findings"] == []


def test_an_empty_audit_uses_no_model_and_the_scan_needs_canon(
    tmp_path: Path,
) -> None:
    provider = UnusedProvider()
    with _client(tmp_path, provider) as client:
        project, _ = _project(client)

        audit = client.get(f"/api/projects/{project['id']}/contradictions").json()
        assert audit["counts"] == {
            "relationships": 0,
            "thread_resolutions": 0,
            "findings": 0,
        }
        assert audit["findings"] == []

        scan = client.post(
            f"/api/projects/{project['id']}/contradictions/scan",
            json={"model": "fake-model"},
        )
        assert scan.status_code == 400
        assert "two canon facts" in scan.json()["detail"]

        missing = client.get("/api/projects/999/contradictions")
        assert missing.status_code == 404


def test_scan_keeps_only_findings_that_cite_two_records(tmp_path: Path) -> None:
    provider = ScanProvider(
        json.dumps(
            {
                "findings": [
                    {
                        "kind": "location",
                        "severity": "critical",
                        "source_a": "c1",
                        "source_b": "C2",
                        "summary": "Mira is in two places at once.",
                        "detail": "Two state records disagree.",
                        "suggestion": "Correct the later snapshot.",
                    },
                    {
                        "kind": "timeline",
                        "severity": "high",
                        "source_a": "C1",
                        "source_b": "C1",
                        "summary": "A record contradicts itself.",
                    },
                    {
                        "kind": "plot",
                        "severity": "high",
                        "source_a": "C1",
                        "source_b": "C99",
                        "summary": "An invented record.",
                    },
                    {
                        "kind": "plot",
                        "severity": "high",
                        "source_a": "C2",
                        "source_b": "C1",
                        "summary": "The same pair, reversed.",
                    },
                    {
                        "kind": "plot",
                        "severity": "low",
                        "source_a": "C1",
                        "source_b": "C2",
                        "summary": "   ",
                    },
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = _character(client, project["id"], "Mira")
        orin = _character(client, project["id"], "Orin")
        for character_id, location in ((mira, "the gate"), (orin, "the keep")):
            created = client.post(
                f"/api/projects/{project['id']}/character-states",
                json={
                    "character_id": character_id,
                    "chapter_id": chapters[0]["id"],
                    "location": location,
                },
            )
            assert created.status_code == 201, created.text

        response = client.post(
            f"/api/projects/{project['id']}/contradictions/scan",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["canon_count"] >= 2
        findings = payload["findings"]
        assert len(findings) == 1
        finding = findings[0]
        assert finding["source_a"] == "C1"
        assert finding["source_b"] == "C2"
        labels = finding["source_a_label"] + finding["source_b_label"]
        assert "Mira" in labels and "Orin" in labels
        assert finding["summary"] == "Mira is in two places at once."

        prompt = provider.requests[0].prompt
        assert "C1:" in prompt and "C2:" in prompt
        assert "Return the JSON contradiction report." in prompt

        states = client.get(
            f"/api/projects/{project['id']}/character-states"
        ).json()
        assert len(states) == 2


def test_scan_reports_bad_json_and_an_unknown_project(tmp_path: Path) -> None:
    provider = ScanProvider("No contradictions.")
    with _client(tmp_path, provider) as client:
        project, chapters = _project(client)
        mira = _character(client, project["id"], "Mira")
        orin = _character(client, project["id"], "Orin")
        for character_id in (mira, orin):
            client.post(
                f"/api/projects/{project['id']}/character-states",
                json={
                    "character_id": character_id,
                    "chapter_id": chapters[0]["id"],
                    "status": "wounded",
                },
            )

        malformed = client.post(
            f"/api/projects/{project['id']}/contradictions/scan",
            json={"model": "fake-model"},
        )
        assert malformed.status_code == 502
        assert "contradiction JSON" in malformed.json()["detail"]

        missing = client.post(
            "/api/projects/999/contradictions/scan", json={"model": "fake-model"}
        )
        assert missing.status_code == 404
