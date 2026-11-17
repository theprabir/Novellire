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


def test_parse_chapter_map_accepts_a_continuation() -> None:
    entries = parse_chapter_map(
        "## Chapter 15: Return\nBack to the archive.\n\n"
        "## Chapter 16: The Record\nThe name is gone."
    )

    assert [entry.number for entry in entries] == [15, 16]
    assert entries[0].title == "Return"


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


def test_outline_can_continue_after_existing_chapters(client) -> None:
    project = client.post("/api/projects", json={"name": "Continued"}).json()
    for index in range(1, 3):
        client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": f"Written {index}", "content": f"Prose {index}."},
        )
    client.put(
        f"/api/projects/{project['id']}/documents/chapter_map",
        json={"content": "Chapter 3: Next\nPlan.\n\nChapter 4: Later\nPlan."},
    )

    preview = client.get(f"/api/projects/{project['id']}/outline/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["create_count"] == 2

    applied = client.post(f"/api/projects/{project['id']}/outline/apply")
    assert applied.status_code == 200, applied.text
    chapters = client.get(f"/api/projects/{project['id']}/chapters").json()
    assert [chapter["title"] for chapter in chapters] == [
        "Written 1",
        "Written 2",
        "Next",
        "Later",
    ]


def test_outline_cannot_skip_the_next_chapter(client) -> None:
    project = client.post("/api/projects", json={"name": "Skipped"}).json()
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Written", "content": "Prose."},
    )
    client.put(
        f"/api/projects/{project['id']}/documents/chapter_map",
        json={"content": "Chapter 3: Too Far\nPlan."},
    )

    response = client.get(f"/api/projects/{project['id']}/outline/preview")

    assert response.status_code == 400
    assert "next chapter is 2" in response.json()["detail"]