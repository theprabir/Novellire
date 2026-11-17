"""Chapter Map parsing and outline sync."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import GenerationDefaults, Settings
from novellire.core.outline import parse_chapter_map
from novellire.errors import InvalidInputError
from novellire.storage.database import Database


@pytest.fixture()
def client(tmp_path: Path, fake_provider) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
    )
    app = create_app(
        settings=settings,
        database=Database(settings.database_path),
        provider=fake_provider,
    )
    with TestClient(app) as test_client:
        yield test_client


def test_parse_chapter_map_reads_headings_and_plans() -> None:
    entries = parse_chapter_map(
        """# Chapter 1: The Missing Face
Naina finds a photograph.

## Chapter 2 — The Gate
The gate opens.
"""
    )

    assert [entry.number for entry in entries] == [1, 2]
    assert entries[0].title == "The Missing Face"
    assert entries[0].objectives == "Naina finds a photograph."
    assert entries[1].title == "The Gate"
    assert entries[1].objectives == "The gate opens."


def test_parse_chapter_map_accepts_bold_headings() -> None:
    entries = parse_chapter_map("**Chapter 1: Arrival**\nStart here.")

    assert entries[0].title == "Arrival"
    assert entries[0].objectives == "Start here."


def test_parse_chapter_map_rejects_gaps() -> None:
    with pytest.raises(InvalidInputError, match="without gaps"):
        parse_chapter_map("Chapter 1: One\n\nChapter 3: Three")


def test_parse_chapter_map_rejects_duplicates() -> None:
    with pytest.raises(InvalidInputError, match="unique"):
        parse_chapter_map("Chapter 1: One\n\nChapter 1: Again")


def test_parse_chapter_map_requires_headings() -> None:
    with pytest.raises(InvalidInputError, match="No chapters"):
        parse_chapter_map("Just notes without a chapter heading.")


def test_outline_preview_and_apply_create_missing_chapters(client) -> None:
    project = client.post("/api/projects", json={"name": "Outline"}).json()
    client.put(
        f"/api/projects/{project['id']}/documents/chapter_map",
        json={
            "content": (
                "## Chapter 1: The Missing Face\nOpen with the photograph.\n\n"
                "## Chapter 2: The Gate\nEnd on the gate opening."
            )
        },
    )

    preview = client.get(f"/api/projects/{project['id']}/outline/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["create_count"] == 2

    applied = client.post(f"/api/projects/{project['id']}/outline/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["created_count"] == 2

    chapters = client.get(f"/api/projects/{project['id']}/chapters").json()
    assert [chapter["position"] for chapter in chapters] == [1, 2]
    assert [chapter["title"] for chapter in chapters] == [
        "The Missing Face",
        "The Gate",
    ]
    assert chapters[1]["objectives"] == "End on the gate opening."

    again = client.get(f"/api/projects/{project['id']}/outline/preview")
    assert again.json()["create_count"] == 0
    assert again.json()["existing_count"] == 2


def test_outline_apply_preserves_existing_authored_chapter(client) -> None:
    project = client.post("/api/projects", json={"name": "Outline"}).json()
    existing = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "My Own Opening", "content": "Authored prose."},
    ).json()
    client.put(
        f"/api/projects/{project['id']}/documents/chapter_map",
        json={"content": "Chapter 1: Outline Title\nPlan.\n\nChapter 2: Next\nPlan."},
    )

    applied = client.post(f"/api/projects/{project['id']}/outline/apply").json()

    assert applied["created_count"] == 1
    chapters = client.get(f"/api/projects/{project['id']}/chapters").json()
    assert chapters[0]["id"] == existing["id"]
    assert chapters[0]["title"] == "My Own Opening"
    assert chapters[0]["content"] == "Authored prose."
    assert chapters[1]["title"] == "Next"