"""HTTP API tests against the FastAPI app and a stubbed provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import GenerationDefaults, Settings
from novellire.llm.base import GenerationResult
from novellire.storage.event_repository import EventDraft
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
    assert payload["schema_version"] == 9
    assert payload["version"] == "0.4.0"


def test_meta_exposes_labels_for_the_client(client: TestClient) -> None:
    payload = client.get("/api/meta").json()

    assert {"key": "premise", "label": "Premise"} in payload["bible_categories"]
    assert any(item["key"] == "approved" for item in payload["work_statuses"])
    assert any(item["key"] == "character_arc" for item in payload["character_fields"])
    assert "violet" in payload["appearance_options"]["accents"]
    assert any(item["key"] == "ally" for item in payload["relationship_types"])
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


def test_chapter_move_and_delete_keep_positions_contiguous(
    client: TestClient,
) -> None:
    project = create_project(client)
    ids = [
        client.post(
            f"/api/projects/{project['id']}/chapters", json={"title": title}
        ).json()["id"]
        for title in ("One", "Two", "Three")
    ]

    for _ in range(2):
        moved = client.post(f"/api/chapters/{ids[2]}/move", json={"direction": "up"})
        assert moved.status_code == 200, moved.text

    tree = client.get(f"/api/projects/{project['id']}/tree").json()
    assert [(chapter["title"], chapter["position"]) for chapter in tree["chapters"]] == [
        ("Three", 1),
        ("One", 2),
        ("Two", 3),
    ]

    # Moving past the first position is a no-op, not an error.
    client.post(f"/api/chapters/{ids[2]}/move", json={"direction": "up"})
    tree = client.get(f"/api/projects/{project['id']}/tree").json()
    assert [chapter["title"] for chapter in tree["chapters"]] == ["Three", "One", "Two"]

    # Deleting the first chapter must shift the rest without a unique collision.
    deleted = client.delete(f"/api/chapters/{ids[2]}")
    assert deleted.status_code == 200

    tree = client.get(f"/api/projects/{project['id']}/tree").json()
    assert [(chapter["title"], chapter["position"]) for chapter in tree["chapters"]] == [
        ("One", 1),
        ("Two", 2),
    ]
    manuscript = client.get(f"/api/projects/{project['id']}/manuscript").json()
    assert [chapter["title"] for chapter in manuscript["chapters"]] == ["One", "Two"]

    invalid = client.post(f"/api/chapters/{ids[1]}/move", json={"direction": "sideways"})
    assert invalid.status_code == 422


def test_scene_move_and_delete_keep_positions_contiguous(
    client: TestClient,
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "The Vault"}
    ).json()
    ids = [
        client.post(
            f"/api/chapters/{chapter['id']}/scenes",
            json={"title": title, "content": f"{title} prose."},
        ).json()["id"]
        for title in ("Approach", "Descent", "Vault")
    ]

    for _ in range(2):
        moved = client.post(f"/api/scenes/{ids[2]}/move", json={"direction": "up"})
        assert moved.status_code == 200, moved.text

    tree = client.get(f"/api/projects/{project['id']}/tree").json()
    scenes = tree["chapters"][0]["scenes"]
    assert [(scene["title"], scene["position"]) for scene in scenes] == [
        ("Vault", 1),
        ("Approach", 2),
        ("Descent", 3),
    ]

    # Deleting the first scene must shift the rest without a unique collision.
    client.delete(f"/api/scenes/{ids[2]}")
    tree = client.get(f"/api/projects/{project['id']}/tree").json()
    scenes = tree["chapters"][0]["scenes"]
    assert [(scene["title"], scene["position"]) for scene in scenes] == [
        ("Approach", 1),
        ("Descent", 2),
    ]

    after = client.get(f"/api/chapters/{chapter['id']}/scenes").json()
    assert [scene["title"] for scene in after] == ["Approach", "Descent"]


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


def test_generation_uses_earlier_chapters_and_reports_them(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    earlier = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "The Gate",
            "content": "Mira crossed the ashen archive and read the ledger.",
            "summary": "Mira enters the archive and reads the ledger.",
        },
    ).json()
    client.app.state.services.event_repository.replace_for_chapter(
        project["id"],
        earlier["id"],
        [
            EventDraft(
                summary="Mira hides the sealed key in her coat.",
                characters=("Mira",),
                locations=("archive",),
                objects=("sealed key",),
                threads=("Who sealed the ledger?",),
            )
        ],
        model="fake-model",
    )
    current = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "Return"}
    ).json()

    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={
            "instructions": "Mira returns to the ashen archive.",
            "model": "fake-model",
            "chapter_id": current["id"],
            "target_words": 300,
        },
    )

    assert response.status_code == 200, response.text
    sources = response.json()["context"]["chapters"]
    assert [source["title"] for source in sources] == ["The Gate"]
    assert sources[0]["position"] == 1
    assert "archive" in sources[0]["excerpt"]

    events = response.json()["context"]["events"]
    assert [event["summary"] for event in events] == [
        "Mira hides the sealed key in her coat."
    ]
    assert events[0]["chapter_title"] == "The Gate"
    assert events[0]["threads"] == ["Who sealed the ledger?"]

    prompt = fake_provider.requests[-1].prompt
    assert "Earlier chapters:" in prompt
    assert "Chapter 1 — The Gate" in prompt
    assert "Mira enters the archive and reads the ledger." in prompt
    assert "Chapter 2 — Return" not in prompt
    assert "Earlier events:" in prompt
    assert "Event: Mira hides the sealed key in her coat." in prompt
    assert "Characters: Mira" in prompt


def test_generation_validation_error_is_reported(client: TestClient) -> None:
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/generate",
        json={"instructions": "   ", "model": "fake-model"},
    )

    assert response.status_code == 400
    assert "Describe" in response.json()["detail"]


def test_search_returns_chapter_and_document_hits(client: TestClient) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Mira crossed the ash square."},
    )
    client.put(
        f"/api/projects/{project['id']}/documents/master_bible",
        json={"content": "The star is dimming."},
    )

    chapter_hits = client.get(
        f"/api/projects/{project['id']}/search", params={"q": "ash"}
    ).json()["results"]
    assert len(chapter_hits) == 1
    assert chapter_hits[0]["kind"] == "chapter"
    assert chapter_hits[0]["title"] == "The Gate"
    assert "ash" in chapter_hits[0]["excerpt"].lower()

    document_hits = client.get(
        f"/api/projects/{project['id']}/search", params={"q": "dimming"}
    ).json()["results"]
    assert len(document_hits) == 1
    assert document_hits[0]["kind"] == "master_bible"
    assert document_hits[0]["title"] == "Master Story Bible"


def test_search_rejects_a_blank_query(client: TestClient) -> None:
    project = create_project(client)

    response = client.get(
        f"/api/projects/{project['id']}/search", params={"q": "   "}
    )

    assert response.status_code == 400
    assert "Enter a word" in response.json()["detail"]


def test_summarize_chapter_stores_the_summary(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Mira pressed the key to her palm."},
    ).json()

    response = client.post(
        f"/api/chapters/{chapter['id']}/summarize",
        json={"model": "fake-model"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"] == " ".join(["word"] * 120)
    assert payload["model"] == "fake-model"

    manuscript = client.get(f"/api/projects/{project['id']}/manuscript").json()
    assert manuscript["chapters"][0]["summary"] == payload["summary"]


def test_bulk_summary_streams_progress(client: TestClient, fake_provider) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "One", "content": "Mira pressed the key to her palm."},
    )
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "Two",
            "content": "Mira waited.",
            "summary": "An older summary.",
        },
    )

    with client.stream(
        "POST",
        f"/api/projects/{project['id']}/summaries",
        json={"model": "fake-model"},
    ) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    assert events[0] == {"type": "start", "total": 2, "pending": 1}
    steps = [event for event in events if event["type"] == "step"]
    assert [step["status"] for step in steps] == ["summarised", "skipped"]
    assert steps[0]["processed"] == 1
    assert steps[1]["detail"] == "Already has a summary."
    assert events[-1] == {
        "type": "done",
        "summarised": 1,
        "skipped": 1,
        "empty": 0,
        "failed": 0,
        "total": 2,
    }

    manuscript = client.get(f"/api/projects/{project['id']}/manuscript").json()
    assert manuscript["chapters"][0]["summary"] == " ".join(["word"] * 120)
    assert manuscript["chapters"][1]["summary"] == "An older summary."


def test_event_extraction_stores_and_lists_events(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={
            "title": "The Gate",
            "content": "Mira crossed the ashen archive and met the keeper.",
        },
    ).json()
    fake_provider.result = GenerationResult(
        text=(
            '{"events":[{"summary":"Mira reaches the archive.",'
            '"characters":["Mira"],"locations":["archive"],'
            '"objects":["sealed key"],'
            '"threads":["Who sealed the ledger?"]}]}'
        ),
        model="fake-model",
        duration_ms=64,
    )

    response = client.post(
        f"/api/chapters/{chapter['id']}/events/extract",
        json={"model": "fake-model"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["duration_ms"] == 64
    assert len(payload["events"]) == 1
    assert payload["events"][0]["chapter_title"] == "The Gate"
    assert payload["events"][0]["threads"] == ["Who sealed the ledger?"]

    listing = client.get(f"/api/projects/{project['id']}/events").json()
    assert listing == payload["events"]


def test_events_link_profiles_and_support_edit_and_delete(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "Mira Voss", "aliases": ["the Courier"]},
    ).json()
    orin = client.post(
        f"/api/projects/{project['id']}/characters",
        json={"name": "Orin Vale"},
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "The Courier enters."},
    ).json()
    fake_provider.result = GenerationResult(
        text=(
            '{"events":[{"summary":"The Courier enters the archive.",'
            '"characters":["the Courier"],"locations":["archive"],'
            '"objects":[],"threads":[]}]}'
        ),
        model="fake-model",
        duration_ms=12,
    )

    extracted = client.post(
        f"/api/chapters/{chapter['id']}/events/extract",
        json={"model": "fake-model"},
    ).json()
    event = extracted["events"][0]
    assert event["character_ids"] == [mira["id"]]

    updated = client.patch(
        f"/api/events/{event['id']}",
        json={
            "summary": "Orin takes the ledger instead.",
            "characters": ["Orin"],
            "locations": ["keep"],
            "objects": ["ledger"],
            "threads": [],
        },
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["summary"] == "Orin takes the ledger instead."
    assert updated.json()["character_ids"] == [orin["id"]]

    deleted = client.delete(f"/api/events/{event['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/projects/{project['id']}/events").json() == []


def test_relationships_endpoint_reports_shared_events(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Mira Voss"}
    ).json()
    orin = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Orin Vale"}
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Mira and Orin meet."},
    ).json()
    fake_provider.result = GenerationResult(
        text=(
            '{"events":[{"summary":"Mira and Orin open the gate.",'
            '"characters":["Mira","Orin"],"locations":["gate"],'
            '"objects":[],"threads":[]}]}'
        ),
        model="fake-model",
        duration_ms=5,
    )
    client.post(
        f"/api/chapters/{chapter['id']}/events/extract",
        json={"model": "fake-model"},
    )

    relationships = client.get(
        f"/api/projects/{project['id']}/relationships"
    ).json()

    assert len(relationships) == 1
    pair = relationships[0]
    assert {pair["character_a_name"], pair["character_b_name"]} == {
        "Mira Voss",
        "Orin Vale",
    }
    assert pair["shared_events"] == 1
    assert pair["latest_summary"] == "Mira and Orin open the gate."
    assert pair["latest_chapter_title"] == "The Gate"
    assert pair["status"] == "derived"
    assert {pair["character_a_id"], pair["character_b_id"]} == {
        mira["id"],
        orin["id"],
    }


def test_relationship_records_support_create_approve_and_delete(
    client: TestClient,
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Mira Voss"}
    ).json()
    orin = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Orin Vale"}
    ).json()

    created = client.post(
        f"/api/projects/{project['id']}/relationship-records",
        json={
            "character_a_id": orin["id"],
            "character_b_id": mira["id"],
            "relation_type": "ally",
            "description": "They guard the archive.",
        },
    )

    assert created.status_code == 201, created.text
    record = created.json()
    assert record["character_a_id"] == mira["id"]
    assert record["status"] == "proposed"

    approved = client.patch(
        f"/api/relationship-records/{record['id']}/status",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    edited = client.patch(
        f"/api/relationship-records/{record['id']}",
        json={"relation_type": "family"},
    )
    assert edited.json()["relation_type"] == "family"

    listing = client.get(
        f"/api/projects/{project['id']}/relationship-records"
    ).json()
    assert len(listing) == 1
    assert listing[0]["description"] == "They guard the archive."

    deleted = client.delete(f"/api/relationship-records/{record['id']}")
    assert deleted.status_code == 200
    assert client.get(
        f"/api/projects/{project['id']}/relationship-records"
    ).json() == []


def test_character_state_snapshots_support_create_edit_and_delete(
    client: TestClient,
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Mira Voss"}
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate"},
    ).json()

    created = client.post(
        f"/api/projects/{project['id']}/character-states",
        json={
            "character_id": mira["id"],
            "chapter_id": chapter["id"],
            "location": "The archive",
            "status": "Wounded",
            "goals": "Reach the gate",
            "knowledge": "The gate is warded",
        },
    )

    assert created.status_code == 201, created.text
    state = created.json()
    assert state["is_current"] is True
    assert state["chapter_title"] == "The Gate"

    listing = client.get(
        f"/api/projects/{project['id']}/character-states"
    ).json()
    assert len(listing) == 1
    assert listing[0]["location"] == "The archive"

    updated = client.patch(
        f"/api/character-states/{state['id']}",
        json={
            "location": "The keep",
            "status": "Recovering",
            "goals": "Find the ledger",
            "knowledge": "Orin has the key",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["location"] == "The keep"

    deleted = client.delete(f"/api/character-states/{state['id']}")
    assert deleted.status_code == 200
    assert client.get(
        f"/api/projects/{project['id']}/character-states"
    ).json() == []


def test_chapter_revisions_list_previews_and_restore(
    client: TestClient,
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Original text."},
    ).json()
    client.patch(
        f"/api/chapters/{chapter['id']}", json={"content": "Changed text."}
    )

    listing = client.get(f"/api/chapters/{chapter['id']}/revisions").json()

    assert len(listing) == 1
    assert listing[0]["source"] == "edit"
    assert listing[0]["excerpt"] == "Original text."
    assert "content" not in listing[0]

    detail = client.get(
        f"/api/chapters/{chapter['id']}/revisions/{listing[0]['id']}"
    ).json()
    assert detail["content"] == "Original text."

    other = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "Other", "content": "Other text."},
    ).json()
    foreign = client.get(
        f"/api/chapters/{other['id']}/revisions/{listing[0]['id']}"
    )
    assert foreign.status_code == 404

    restored = client.post(
        f"/api/chapters/{chapter['id']}/revisions/{listing[0]['id']}/restore"
    )

    assert restored.status_code == 200
    assert restored.json()["content"] == "Original text."
    assert len(
        client.get(f"/api/chapters/{chapter['id']}/revisions").json()
    ) == 2


def test_approved_chapter_text_must_be_reopened_first(
    client: TestClient,
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Approved text."},
    ).json()
    approved = client.patch(
        f"/api/chapters/{chapter['id']}", json={"status": "approved"}
    )
    assert approved.status_code == 200

    blocked = client.patch(
        f"/api/chapters/{chapter['id']}", json={"content": "Changed text."}
    )
    assert blocked.status_code == 400
    assert "Reopen" in blocked.json()["detail"]

    reopened = client.patch(
        f"/api/chapters/{chapter['id']}",
        json={"status": "drafted", "content": "Changed text."},
    )
    assert reopened.status_code == 200
    assert reopened.json()["content"] == "Changed text."
    assert reopened.json()["status"] == "drafted"


def test_approved_chapter_must_be_reopened_before_restore(
    client: TestClient,
) -> None:
    project = create_project(client)
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Original text."},
    ).json()
    client.patch(
        f"/api/chapters/{chapter['id']}", json={"content": "Changed text."}
    )
    revision = client.get(
        f"/api/chapters/{chapter['id']}/revisions"
    ).json()[0]
    client.patch(
        f"/api/chapters/{chapter['id']}", json={"status": "approved"}
    )

    blocked = client.post(
        f"/api/chapters/{chapter['id']}/revisions/{revision['id']}/restore"
    )
    assert blocked.status_code == 400
    assert "Reopen" in blocked.json()["detail"]

    client.patch(f"/api/chapters/{chapter['id']}", json={"status": "drafted"})
    restored = client.post(
        f"/api/chapters/{chapter['id']}/revisions/{revision['id']}/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["content"] == "Original text."


def test_chapter_with_state_snapshots_cannot_be_deleted(
    client: TestClient,
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Mira Voss"}
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate"},
    ).json()
    state = client.post(
        f"/api/projects/{project['id']}/character-states",
        json={
            "character_id": mira["id"],
            "chapter_id": chapter["id"],
            "location": "The archive",
        },
    ).json()

    blocked = client.delete(f"/api/chapters/{chapter['id']}")

    assert blocked.status_code == 400
    assert "character state snapshots" in blocked.json()["detail"]
    chapters = client.get(f"/api/projects/{project['id']}/chapters").json()
    assert [item["id"] for item in chapters] == [chapter["id"]]

    assert client.delete(f"/api/character-states/{state['id']}").status_code == 200
    assert client.delete(f"/api/chapters/{chapter['id']}").status_code == 200


def test_adding_an_alias_relinks_existing_events(
    client: TestClient, fake_provider
) -> None:
    project = create_project(client)
    mira = client.post(
        f"/api/projects/{project['id']}/characters", json={"name": "Mira Voss"}
    ).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "The Courier enters."},
    ).json()
    fake_provider.result = GenerationResult(
        text=(
            '{"events":[{"summary":"The Courier enters.",'
            '"characters":["the Courier"],"locations":[],'
            '"objects":[],"threads":[]}]}'
        ),
        model="fake-model",
        duration_ms=5,
    )
    events = client.post(
        f"/api/chapters/{chapter['id']}/events/extract",
        json={"model": "fake-model"},
    ).json()["events"]
    assert events[0]["character_ids"] == []

    client.put(
        f"/api/characters/{mira['id']}/aliases",
        json={"aliases": ["the Courier"]},
    )

    listing = client.get(f"/api/projects/{project['id']}/events").json()
    assert listing[0]["character_ids"] == [mira["id"]]


def test_backup_download_and_restore(client: TestClient) -> None:
    create_project(client, name="Original")
    download = client.get("/api/backup")

    assert download.status_code == 200
    assert download.content.startswith(b"SQLite format 3\x00")
    assert "novellire-backup-" in download.headers["content-disposition"]

    create_project(client, name="Later")
    restored = client.post(
        "/api/backup/restore",
        content=download.content,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["projects"] == 1
    assert restored.json()["safety_backup"].startswith("pre-restore-")
    names = [
        project["name"]
        for project in client.get("/api/projects").json()["projects"]
    ]
    assert names == ["Original"]


def test_restore_rejects_a_non_backup_file(client: TestClient) -> None:
    create_project(client, name="Original")

    response = client.post(
        "/api/backup/restore",
        content=b"not a database",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 400
    assert "not a Novellire" in response.json()["detail"]
    names = [
        project["name"]
        for project in client.get("/api/projects").json()["projects"]
    ]
    assert names == ["Original"]


def test_export_returns_a_manuscript_file(client: TestClient) -> None:
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/chapters",
        json={"title": "The Gate", "content": "Mira opened the gate."},
    )
    client.put(
        f"/api/projects/{project['id']}/documents/master_bible",
        json={"content": "The gate is sealed with iron."},
    )

    response = client.get(
        f"/api/projects/{project['id']}/export?format=markdown&include_documents=true"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "ashfall-with-documents.md"
    assert "## Chapter 1 — The Gate" in payload["content"]
    assert "Mira opened the gate." in payload["content"]
    assert "The gate is sealed with iron." in payload["content"]
    assert payload["word_count"] == 4


def test_export_requires_chapter_text(client: TestClient) -> None:
    project = create_project(client)

    response = client.get(f"/api/projects/{project['id']}/export")

    assert response.status_code == 400
    assert "at least one chapter" in response.json()["detail"]


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
