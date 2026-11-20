"""Style analysis: deterministic prose measurements and cited deviations."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.core.style import guide_rules
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database

PROSE = (
    "Mira opened the gate. The rain fell in long grey lines, and ash covered "
    "the square. \u201cWe should go,\u201d Orin said.\n\nNobody answered him."
)
GUIDE = (
    "Sentence structure\n\nShort declarative sentences. Avoid semicolons.\n\n"
    "Vocabulary\n\nConcrete nouns."
)


class UnusedProvider:
    """The deterministic profile must never run inference."""

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        raise AssertionError("style profiling must not run inference")


class StyleProvider:
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


def _project(client: TestClient, *, content: str = PROSE, guide: str = ""):
    project = client.post("/api/projects", json={"name": "Ashfall"}).json()
    chapter = client.post(
        f"/api/projects/{project['id']}/chapters", json={"title": "The Gate"}
    ).json()
    if content:
        updated = client.patch(
            f"/api/chapters/{chapter['id']}", json={"content": content}
        )
        assert updated.status_code == 200, updated.text
    if guide:
        saved = client.put(
            f"/api/projects/{project['id']}/documents/style_guide",
            json={"content": guide},
        )
        assert saved.status_code == 200, saved.text
    return project, chapter


def test_profile_measures_prose_without_a_model(tmp_path: Path) -> None:
    with _client(tmp_path, UnusedProvider()) as client:
        project, _ = _project(client)

        response = client.get(f"/api/projects/{project['id']}/style")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"] == {
            "chapters": 1,
            "words": 24,
            "sentences": 4,
            "paragraphs": 2,
            "dialogue_paragraphs": 1,
            "long_sentences": 0,
            "rules": 0,
        }
        assert payload["average_sentence_words"] == 6.0
        assert payload["dialogue_share"] == 50
        assert payload["guide"] == {"present": False, "derived": False, "rules": []}
        chapter = payload["chapters"][0]
        assert chapter["position"] == 1
        assert chapter["title"] == "The Gate"
        assert chapter["words"] == 24
        assert chapter["sentences"] == 4
        assert chapter["longest_sentence_words"] == 12
        assert chapter["longest_sentence"].startswith("The rain fell")

        missing = client.get("/api/projects/999/style")
        assert missing.status_code == 404


def test_guide_rules_number_paragraphs_and_label_headings() -> None:
    rules = guide_rules(GUIDE)

    assert [rule.id for rule in rules] == ["S1", "S2"]
    assert rules[0].label.startswith("Sentence structure")
    assert "Short declarative sentences" in rules[0].guidance
    assert rules[1].label.startswith("Vocabulary")
    assert "Concrete nouns" in rules[1].guidance


def test_a_rule_with_no_heading_still_becomes_a_citable_rule() -> None:
    rules = guide_rules("Avoid adverbs. Prefer concrete verbs.")

    assert len(rules) == 1
    assert rules[0].id == "S1"
    assert rules[0].guidance == "Avoid adverbs. Prefer concrete verbs."


def test_style_check_keeps_only_deviations_that_cite_a_rule(
    tmp_path: Path,
) -> None:
    quote = "The rain fell in long grey lines, and ash covered the square."
    provider = StyleProvider(
        json.dumps(
            {
                "deviations": [
                    {
                        "aspect": "sentence",
                        "severity": "high",
                        "quote": quote,
                        "rule": "s1",
                        "explanation": "The guide asks for short declarative sentences.",
                        "suggestion": "Split it into two sentences.",
                    },
                    {
                        "aspect": "sentence",
                        "severity": "high",
                        "quote": quote,
                        "rule": "S1",
                        "explanation": "The same finding again.",
                    },
                    {
                        "aspect": "sentence",
                        "severity": "high",
                        "quote": "Mira opened the gate.",
                        "rule": "S9",
                        "explanation": "An invented rule.",
                    },
                    {
                        "aspect": "sentence",
                        "severity": "high",
                        "quote": "She laughed.",
                        "rule": "S1",
                        "explanation": "Text that is not in the chapter.",
                    },
                    {
                        "aspect": "dialogue",
                        "severity": "low",
                        "quote": "\u201cWe should go,\u201d Orin said.",
                        "rule": "S2",
                        "explanation": "   ",
                    },
                ]
            }
        )
    )
    with _client(tmp_path, provider) as client:
        project, chapter = _project(client, guide=GUIDE)

        response = client.post(
            f"/api/chapters/{chapter['id']}/style-check",
            json={"model": "fake-model"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["rule_count"] == 2
        deviations = payload["deviations"]
        assert len(deviations) == 2

        first = deviations[0]
        assert first["rule_id"] == "S1"
        assert first["rule"].startswith("Sentence structure")
        assert first["quote"] == quote
        assert first["aspect"] == "sentence"
        assert first["severity"] == "high"
        assert "short declarative" in first["explanation"]
        assert first["suggestion"] == "Split it into two sentences."

        second = deviations[1]
        assert second["rule_id"] == "S2"
        assert second["explanation"] == "Departs from the cited style rule."

        prompt = provider.requests[0].prompt
        assert "S1: Sentence structure: Short declarative sentences." in prompt
        assert "S2: Vocabulary: Concrete nouns." in prompt
        assert "Mira opened the gate." in prompt
        assert "Return the JSON style report." in prompt

        manuscript = client.get(
            f"/api/projects/{project['id']}/manuscript"
        ).json()
        stored = next(
            row for row in manuscript["chapters"] if row["id"] == chapter["id"]
        )
        assert stored["content"] == PROSE
        documents = client.get(
            f"/api/projects/{project['id']}/documents"
        ).json()
        guide = {row["kind"]: row for row in documents}["style_guide"]
        assert guide["content"] == GUIDE


def test_style_check_refuses_without_a_guide_chapter_or_model(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, StyleProvider("{}")) as client:
        project, chapter = _project(client)

        no_guide = client.post(
            f"/api/chapters/{chapter['id']}/style-check",
            json={"model": "fake-model"},
        )
        assert no_guide.status_code == 400
        assert "Style Guide" in no_guide.json()["detail"]

        empty = client.patch(
            f"/api/chapters/{chapter['id']}", json={"content": "   "}
        )
        assert empty.status_code == 200, empty.text
        no_text = client.post(
            f"/api/chapters/{chapter['id']}/style-check",
            json={"model": "fake-model"},
        )
        assert no_text.status_code == 400
        assert "before checking its style" in no_text.json()["detail"]

        missing = client.post(
            "/api/chapters/999/style-check", json={"model": "fake-model"}
        )
        assert missing.status_code == 400
        assert "no longer exists" in missing.json()["detail"]

        no_model = client.post(
            f"/api/chapters/{chapter['id']}/style-check", json={"model": ""}
        )
        assert no_model.status_code == 400


def test_style_check_reports_bad_json(tmp_path: Path) -> None:
    provider = StyleProvider("No deviations.")
    with _client(tmp_path, provider) as client:
        _, chapter = _project(client, guide=GUIDE)

        malformed = client.post(
            f"/api/chapters/{chapter['id']}/style-check",
            json={"model": "fake-model"},
        )
        assert malformed.status_code == 502
        assert "style JSON" in malformed.json()["detail"]
        assert len(provider.requests) == 1
        assert "Short declarative sentences" in provider.requests[0].prompt
