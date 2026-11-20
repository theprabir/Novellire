"""Revision suggestions derived from measured prose, with no model."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import ModelInfo
from novellire.storage.database import Database


class UnusedProvider:
    """The revision plan is deterministic and must not run inference."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("the revision plan must not run inference")


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    return TestClient(
        create_app(
            settings=settings,
            database=Database(settings.database_path),
            provider=UnusedProvider(),
        )
    )


def _project(client: TestClient, chapters: list[str]):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    for index, content in enumerate(chapters, start=1):
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": f"Chapter {index}"},
        ).json()
        updated = client.patch(
            f"/api/chapters/{chapter['id']}", json={"content": content}
        )
        assert updated.status_code == 200, updated.text
    return project


def _word(index: int) -> str:
    """A distinct, purely alphabetic token, so no phrase accidentally repeats."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("a") + remainder) + letters
    return letters


def _long_sentence(words: int) -> str:
    return " ".join(_word(index) for index in range(words - 1)) + " end."


def test_a_long_sentence_is_located_with_a_next_step(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = _project(client, [f"{_long_sentence(40)} She left."])

        response = client.get(f"/api/projects/{project['id']}/revision-plan")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"] == {
            "chapters": 1,
            "chapters_with_items": 1,
            "items": 1,
        }
        row = payload["chapters"][0]
        assert row["position"] == 1
        assert row["title"] == "Chapter 1"
        item = row["items"][0]
        assert item["kind"] == "long_sentence"
        assert item["severity"] == "medium"
        assert item["detail"] == "40 words in one sentence."
        assert item["quote"].startswith("a b c")
        assert item["quote"].endswith("end.")
        assert "Split it" in item["suggestion"]


def test_a_very_long_sentence_is_high_and_short_prose_has_no_items(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project = _project(
            client,
            [f"{_long_sentence(70)} She left.", "Mira slept. Ash fell."],
        )

        payload = client.get(f"/api/projects/{project['id']}/revision-plan").json()

        assert len(payload["chapters"]) == 1
        item = payload["chapters"][0]["items"][0]
        assert item["severity"] == "high"
        assert item["detail"] == "70 words in one sentence."


def test_a_dense_paragraph_is_suggested_for_breaking(tmp_path: Path) -> None:
    sentence = "ash fell on the ground."
    with _client(tmp_path) as client:
        project = _project(
            client,
            [
                " ".join([sentence] * 40),
                " ".join([sentence] * 61),
            ],
        )

        payload = client.get(f"/api/projects/{project['id']}/revision-plan").json()

        first, second = payload["chapters"]
        medium = first["items"][0]
        assert medium["kind"] == "dense_paragraph"
        assert medium["severity"] == "medium"
        assert medium["detail"] == "200 words in one paragraph."
        assert medium["quote"].startswith("ash fell on the ground.")
        assert "Break it" in medium["suggestion"]
        high = second["items"][0]
        assert high["severity"] == "high"
        assert high["detail"] == "305 words in one paragraph."


def test_a_repeated_phrase_is_suggested_in_each_chapter_it_appears(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project = _project(
            client,
            [
                "Mira waited. The gate was sealed with iron.",
                "Ash fell. The gate was sealed with iron.",
                "Nobody came. The gate was sealed with iron.",
                "Mira slept.",
            ],
        )

        payload = client.get(f"/api/projects/{project['id']}/revision-plan").json()

        assert [row["position"] for row in payload["chapters"]] == [1, 2, 3]
        item = payload["chapters"][0]["items"][0]
        assert item["kind"] == "repetition"
        assert item["severity"] == "low"
        assert item["quote"] == "the gate was sealed with iron"
        assert item["detail"] == (
            "“the gate was sealed with iron” appears 3 times across the "
            "manuscript."
        )
        assert payload["counts"]["items"] == 3


def test_suggestions_are_capped_and_carry_ordered_ids(tmp_path: Path) -> None:
    paragraphs = [
        f"{_long_sentence(40)} She left." for _ in range(8)
    ]
    with _client(tmp_path) as client:
        project = _project(client, ["\n\n".join(paragraphs)])

        payload = client.get(f"/api/projects/{project['id']}/revision-plan").json()

        row = payload["chapters"][0]
        assert len(row["items"]) == 6
        assert [item["id"] for item in row["items"]] == [1, 2, 3, 4, 5, 6]
        assert payload["counts"]["items"] == 6


def test_the_revision_plan_handles_an_empty_project_and_a_missing_one(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        project = _project(client, [])
        empty = client.get(f"/api/projects/{project['id']}/revision-plan")
        assert empty.status_code == 200, empty.text
        assert empty.json() == {
            "counts": {"chapters": 0, "chapters_with_items": 0, "items": 0},
            "chapters": [],
        }

        missing = client.get("/api/projects/999/revision-plan")
        assert missing.status_code == 404
