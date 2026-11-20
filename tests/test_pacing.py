"""Pacing and repetition review: measured locally, with no model."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import ModelInfo
from novellire.storage.database import Database

PROSE = (
    "Mira opened the gate. The rain fell in long grey lines, and ash covered "
    "the square. \u201cWe should go,\u201d Orin said.\n\nNobody answered him."
)


class UnusedProvider:
    """Pacing and repetition are deterministic and must not run inference."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("pacing review must not run inference")


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
    rows = []
    for index, content in enumerate(chapters, start=1):
        chapter = client.post(
            f"/api/projects/{project['id']}/chapters",
            json={"title": f"Chapter {index}"},
        ).json()
        updated = client.patch(
            f"/api/chapters/{chapter['id']}", json={"content": content}
        )
        assert updated.status_code == 200, updated.text
        rows.append(chapter)
    return project, rows


def test_pacing_measures_paragraph_rhythm_without_a_model(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project, _ = _project(client, [PROSE])

        response = client.get(f"/api/projects/{project['id']}/pacing")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"] == {
            "chapters": 1,
            "words": 24,
            "phrases": 0,
            "truncated": False,
        }
        pacing = payload["pacing"]
        assert pacing["paragraphs"] == 2
        assert pacing["sentences"] == 4
        assert pacing["average_paragraph_words"] == 12.0
        assert pacing["longest_paragraph_words"] == 21
        assert pacing["average_sentence_words"] == 6.0
        assert pacing["dialogue_paragraphs"] == 1
        assert pacing["dialogue_share"] == 50
        chapter = payload["chapters"][0]
        assert chapter["position"] == 1
        assert chapter["title"] == "Chapter 1"
        assert chapter["average_paragraph_words"] == 12.0
        assert chapter["longest_paragraph_words"] == 21
        assert payload["repetitions"] == []


def test_repetition_merges_a_phrase_repeated_across_chapters(
    tmp_path: Path,
) -> None:
    lines = [
        "Mira waited by the gate. The gate was sealed with iron.",
        "Ash fell on the square. The gate was sealed with iron.",
        "Nobody came at dawn. The gate was sealed with iron.",
    ]
    with _client(tmp_path) as client:
        project, _ = _project(client, lines)

        payload = client.get(f"/api/projects/{project['id']}/pacing").json()

        assert payload["counts"]["truncated"] is False
        phrases = [row["phrase"] for row in payload["repetitions"]]
        assert "the gate was sealed with iron" in phrases
        assert phrases.count("the gate was sealed") == 0
        finding = payload["repetitions"][phrases.index(
            "the gate was sealed with iron"
        )]
        assert finding["id"] == 1
        assert finding["count"] == 3
        assert [row["chapter_position"] for row in finding["occurrences"]] == [
            1,
            2,
            3,
        ]
        assert finding["occurrences"][0]["chapter_title"] == "Chapter 1"
        assert "The gate was sealed with iron." in finding["occurrences"][0][
            "excerpt"
        ]


def test_repetition_ignores_a_phrase_seen_twice_and_stopword_windows(
    tmp_path: Path,
) -> None:
    lines = [
        "It was in a. The gate was sealed with iron. Mira waited.",
        "It was in a. The gate was sealed with iron. Orin slept.",
        "It was in a. Someone knocked at noon. Ash fell.",
    ]
    with _client(tmp_path) as client:
        project, _ = _project(client, lines)

        payload = client.get(f"/api/projects/{project['id']}/pacing").json()

        phrases = [row["phrase"] for row in payload["repetitions"]]
        assert "it was in a" not in phrases
        assert "the gate was sealed" not in phrases
        assert payload["repetitions"] == []


def test_repetition_caps_findings_and_occurrences(tmp_path: Path) -> None:
    words = [
        "amber",
        "basalt",
        "cinder",
        "dusk",
        "ember",
        "frost",
        "granite",
        "harbor",
        "iron",
        "juniper",
        "kindling",
        "lantern",
        "marble",
        "nickel",
        "onyx",
    ]
    sentences = [f"{word} lorem ipsum dolor." for word in words] * 3
    with _client(tmp_path) as client:
        project, _ = _project(client, [" ".join(sentences)])

        payload = client.get(f"/api/projects/{project['id']}/pacing").json()

        repetitions = payload["repetitions"]
        assert len(repetitions) == 12
        assert all(row["count"] == 3 for row in repetitions)
        assert all(len(row["occurrences"]) == 3 for row in repetitions)
        assert payload["counts"]["phrases"] == 12


def test_pacing_rejects_an_unknown_project(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/projects/999/pacing")

    assert response.status_code == 404
