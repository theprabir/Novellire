"""HTTP API tests against the FastAPI app and a stubbed provider."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import GenerationDefaults, Settings
from novellire.storage.database import Database


@pytest.fixture()
def client(tmp_path: Path, fake_provider) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
    )
    database = Database(settings.database_path)
    app = create_app(settings=settings, database=database, provider=fake_provider)
    with TestClient(app) as test_client:
        yield test_client


def create_project(client: TestClient, name: str = "Ashfall") -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "description": "A city beneath a dying star.",
            "genre": "Science fiction",
            "target_word_count": 90_000,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_reports_version_and_schema(client: TestClient) -> None:
    payload = client.get("/api/health").json()

    assert payload["status"] == "ok"
    assert payload["schema_version"] == 2
    assert payload["version"] == "0.2.1"


def test_meta_exposes_labels_for_the_client(client: TestClient) -> None:
    payload = client.get("/api/meta").json()

    assert {"key": "premise", "label": "Premise"} in payload["bible_categories"]
    assert any(item["key"] == "approved" for item in payload["work_statuses"])
    assert any(item["key"] == "character_arc" for item in payload["character_fields"])
    assert "violet" in payload["appearance_options"]["accents"]


def test_project_creation_sets_active_project(client: TestClient) -> None:
    project = create_project(client)

    listing = client.get("/api/projects").json()
    assert listing["active_project_id"] == project["id"]
    assert [item["name"] for item in listing["projects"]] == ["Ashfall"]


def test_duplicate_project_name_returns_conflict(client: TestClient) -> None:
    create_project(client)
    response = client.post("/api/projects", json={"name": "ashfall"})

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_project_validation_error_is_reported(client: TestClient) -> None:
    response = client.post("/api/projects", json={"name": "  "})

    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()


def test_tree_reports_structure_and_stats(client: TestClient) -> None:
    project = create_project(client)
    character = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "Mira Voss", "aliases": ["M", "the Courier"]},
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "The Sealed Vault",
            "viewpoint_character_id": character["id"],
            "target_word_count": 2_500,
        },
    ).json()
    client.post(
        f"/api/chapters/{chapter['id']}/scenes",
        json={"title": "Approach", "content": "Mira crossed the empty square."},
    )
    client.post(
        f"/api/projects/{project['id']}/bible",
        json={"category": "premise", "title": "The dying star", "content": "..."},
    )

    tree = client.get(f"/api/projects/{project['id']}/tree").json()

    assert tree["stats"] == {
        "words": 5,
        "chapters": 1,
        "scenes": 1,
        "characters": 1,
        "bible_entries": 1,
    }
    assert tree["chapters"][0]["title"] == "The Sealed Vault"
    assert tree["chapters"][0]["scenes"][0]["word_count"] == 5
    assert tree["characters"][0]["aliases"] == ["M", "the Courier"]


def test_manuscript_returns_ordered_prose(client: TestClient) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "The Vault"}
    ).json()
    for title, text in (("Approach", "First scene text."), ("Descent", "Second scene text.")):
        client.post(
            f"/api/chapters/{chapter['id']}/scenes",
            json={"title": title, "content": text},
        )

    manuscript = client.get(f"/api/projects/{project['id']}/manuscript").json()

    assert [scene["title"] for scene in manuscript["chapters"][0]["scenes"]] == [
        "Approach",
        "Descent",
    ]
    assert manuscript["chapters"][0]["word_count"] == 6


def test_story_bible_update_and_scoping(client: TestClient) -> None:
    project = create_project(client)
    entry = client.post(
        f"/api/projects/{project['id']}/bible",
        json={"category": "premise", "title": "Draft premise", "content": "Old"},
    ).json()

    updated = client.patch(
        f"/api/bible/{entry['id']}",
        json={"title": "The long fall", "content": "New"},
    )

    assert updated.status_code == 200
    assert updated.json()["title"] == "The long fall"
    assert client.get(f"/api/projects/{project['id']}/bible").json()[0]["content"] == "New"


def test_character_update_and_alias_replacement(client: TestClient) -> None:
    project = create_project(client)
    character = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "Mira", "personality": "Watchful"},
    ).json()

    patched = client.patch(
        f"/api/characters/{character['id']}", json={"goals": "Reach the vault"}
    ).json()
    aliased = client.put(
        f"/api/characters/{character['id']}/aliases", json={"aliases": ["M", "the Courier"]}
    ).json()

    assert patched["goals"] == "Reach the vault"
    assert patched["personality"] == "Watchful"
    assert aliased["aliases"] == ["M", "the Courier"]


def test_generation_is_persisted_and_listed(client: TestClient) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={
            "instructions": "Mira opens the vault.",
            "model": "fake-model",
            "target_words": 300,
        },
    )

    assert response.status_code == 200, response.text
    record = response.json()
    assert record["status"] == "completed"
    assert record["word_count"] == 120
    assert "output" in record

    listing = client.get(f"/api/projects/{project['id']}/generations").json()
    assert len(listing) == 1
    assert "excerpt" in listing[0]
    assert "output" not in listing[0]


def test_generation_validation_error_is_reported(client: TestClient) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={"instructions": "   ", "model": "fake-model"},
    )

    assert response.status_code == 400
    assert "Describe" in response.json()["detail"]


def test_missing_project_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/projects/4242/tree")

    assert response.status_code == 404
    assert "project" in response.json()["detail"].lower()


def test_appearance_round_trip_and_validation(client: TestClient) -> None:
    defaults = client.get("/api/settings").json()["appearance"]
    assert defaults["theme"] == "system"
    assert defaults["reading_font"] == "garamond"

    saved = client.put(
        "/api/settings/appearance",
        json={
            **defaults,
            "theme": "light",
            "accent": "emerald",
            "reading_font_size": 22,
        },
    )
    assert saved.status_code == 200

    reloaded = client.get("/api/settings").json()["appearance"]
    assert reloaded["theme"] == "light"
    assert reloaded["accent"] == "emerald"
    assert reloaded["reading_font_size"] == 22

    invalid = client.put(
        "/api/settings/appearance", json={**defaults, "theme": "neon"}
    )
    assert invalid.status_code == 422


def test_generation_defaults_round_trip(client: TestClient) -> None:
    saved = client.put(
        "/api/settings/generation",
        json={
            "model": "qwen2.5:1.5b",
            "temperature": 0.4,
            "top_p": 0.8,
            "num_predict": 512,
            "context_window": 4096,
        },
    )
    assert saved.status_code == 200
    assert client.get("/api/settings").json()["generation"]["model"] == "qwen2.5:1.5b"


def test_static_client_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Novellire" in response.text
    assert "/static/app.css" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    css = client.get("/static/app.css")
    script = client.get("/static/js/app.js")

    assert css.status_code == 200
    assert "--reader-bg" in css.text
    assert script.status_code == 200
    assert "renderWorkspace" in script.text


def test_unknown_api_route_is_not_html(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert "Unknown API route" in response.json()["detail"]
