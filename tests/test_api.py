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
    assert payload["schema_version"] == 3
    assert payload["version"] == "0.2.3"


def test_meta_exposes_labels_for_the_client(client: TestClient) -> None:
    payload = client.get("/api/meta").json()

    assert {"key": "premise", "label": "Premise"} in payload["bible_categories"]
    assert any(item["key"] == "approved" for item in payload["work_statuses"])
    assert any(item["key"] == "character_arc" for item in payload["character_fields"])
    assert "violet" in payload["appearance_options"]["accents"]
    kinds = [item["kind"] for item in payload["workspace_documents"]]
    assert kinds == [
        "master_bible",
        "character_bible",
        "chapter_map",
        "style_guide",
    ]
    assert "Complete storyline" in payload["workspace_documents"][0]["placeholder"]


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


def test_tree_reports_documents_and_chapter_stats(client: TestClient) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "The Sealed Vault",
            "content": "Mira crossed the empty square.",
            "origin": "imported",
        },
    )

    tree = client.get(f"/api/projects/{project['id']}/tree").json()

    assert tree["stats"] == {"words": 5, "chapters": 1}
    assert tree["chapters"][0]["title"] == "The Sealed Vault"
    assert tree["chapters"][0]["word_count"] == 5
    assert tree["chapters"][0]["origin"] == "imported"

    documents = client.get(f"/api/projects/{project['id']}/documents").json()
    assert [document["kind"] for document in documents] == [
        "master_bible",
        "character_bible",
        "chapter_map",
        "style_guide",
    ]
    assert all(document["content"] == "" for document in documents)


def test_manuscript_returns_ordered_chapters(client: TestClient) -> None:
    project = create_project(client)
    for title, text in (("One", "First chapter."), ("Two", "Second chapter text.")):
        client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": title, "content": text},
        )

    manuscript = client.get(f"/api/projects/{project['id']}/manuscript").json()

    assert [chapter["title"] for chapter in manuscript["chapters"]] == ["One", "Two"]
    assert manuscript["chapters"][0]["content"] == "First chapter."
    assert manuscript["chapters"][1]["word_count"] == 3


def test_documents_save_and_reload(client: TestClient) -> None:
    project = create_project(client)

    saved = client.put(
        f"/api/projects/{project['id']}/documents/master_bible",
        json={"content": "The star is dimming, not dying."},
    )
    assert saved.status_code == 200
    assert saved.json()["derived"] is False

    documents = {
        document["kind"]: document
        for document in client.get(f"/api/projects/{project['id']}/documents").json()
    }
    assert documents["master_bible"]["content"] == "The star is dimming, not dying."
    assert documents["style_guide"]["content"] == ""

    unknown = client.put(
        f"/api/projects/{project['id']}/documents/not_a_document",
        json={"content": "x"},
    )
    assert unknown.status_code == 400


def test_imported_chapter_counts_words_and_rejects_ai_writes(
    client: TestClient,
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "Pasted opening",
            "content": "Already written prose lives here.",
            "origin": "imported",
        },
    ).json()

    assert chapter["origin"] == "imported"
    assert chapter["word_count"] == 5
    assert chapter["status"] == "drafted"

    blocked = client.post(
        f"/api/projects/{project['id']}/generate",
        json={
            "instructions": "Continue this chapter.",
            "model": "fake-model",
            "chapter_id": chapter["id"],
        },
    )
    assert blocked.status_code == 400
    assert "pre-written" in blocked.json()["detail"]


def test_chapter_content_update_recounts_words(client: TestClient) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Draft"},
    ).json()

    updated = client.patch(
        f"/api/chapters/{chapter['id']}",
        json={"content": "Four words in this line."},
    ).json()

    assert updated["word_count"] == 5
    assert updated["origin"] == "written"


def test_style_guide_analysis_reads_the_manuscript(client: TestClient) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Opening", "content": "The ash fell, warm and grey."},
    )

    response = client.post(
        f"/api/projects/{project['id']}/style-guide/analyze",
        json={"model": "fake-model"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["derived"] is True
    assert payload["content"].strip()

    documents = {
        document["kind"]: document
        for document in client.get(f"/api/projects/{project['id']}/documents").json()
    }
    assert documents["style_guide"]["content"] == payload["content"]
    assert documents["style_guide"]["derived"] is True


def test_generation_learns_the_style_guide_first(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Opening", "content": "The ash fell, warm and grey."},
    )

    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={"instructions": "Write the next beat.", "model": "fake-model"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["style_guide_inferred"] is True
    assert len(fake_provider.requests) == 2

    documents = {
        document["kind"]: document
        for document in client.get(f"/api/projects/{project['id']}/documents").json()
    }
    assert documents["style_guide"]["derived"] is True
    assert "style guide" in fake_provider.requests[1].prompt.lower()


def test_generation_prompt_includes_workspace_documents(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    client.put(
        f"/api/projects/{project['id']}/documents/master_bible",
        json={"content": "The city lies beneath a dimming star."},
    )

    client.post(
        f"/api/projects/{project['id']}/generate",
        json={"instructions": "Write the next beat.", "model": "fake-model"},
    )

    prompt = fake_provider.requests[0].prompt
    assert "The city lies beneath a dimming star." in prompt
    assert "Master story bible" in prompt


def test_generation_prompt_includes_relevant_canon(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters",
        json={
            "name": "Mira Voss",
            "aliases": ["the Courier"],
            "personality": "Watchful",
            "secrets": "She broke the seal once.",
        },
    ).json()
    client.post(
        f"/api/projects/{project['id']}/bible",
        json={
            "category": "premise",
            "title": "The sealed gate",
            "content": "The gate is bound with iron.",
        },
    )
    client.post(
        f"/api/projects/{project['id']}/bible",
        json={
            "category": "geography",
            "title": "The Southern Isles",
            "content": "A warm archipelago with no gates.",
        },
    )
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Arrival", "viewpoint_character_id": mira["id"]},
    ).json()

    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={
            "instructions": "Mira reaches the gate.",
            "model": "fake-model",
            "chapter_id": chapter["id"],
        },
    )

    assert response.status_code == 200, response.text
    prompt = fake_provider.requests[-1].prompt
    assert "Relevant story bible entries:" in prompt
    assert "The gate is bound with iron." in prompt
    assert "Southern Isles" not in prompt
    assert "Relevant character profiles:" in prompt
    assert "Mira Voss (also: the Courier)" in prompt
    assert "Secrets: She broke the seal once." in prompt


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
