"""Synthetic long-range benchmark: retrieval quality and continuity findings.

The sample under ``samples/benchmark_novel`` is a 27-chapter manuscript with one
detail planted in chapter 2, aliases, a secret, an unresolved mystery, a
location change, and a contradictory pair of relationship records. These tests
seed it through the real services and measure retrieval separately from prose,
as the project specification requires. No model is contacted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
from novellire.llm.base import GenerationResult, ModelInfo
from novellire.storage.database import Database
from novellire.storage.event_repository import EventDraft, EventRepository
from novellire.storage.relationship_repository import RelationshipRepository
from novellire.storage.state_repository import CharacterStateRepository

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "benchmark_novel"
HEADING = re.compile(r"^#\s*(\d+)\.\s*(.+)$")
DOCUMENT_KINDS = (
    "master_bible",
    "character_bible",
    "chapter_map",
    "style_guide",
)


class ScriptedProvider:
    """A provider whose reply is set by the test; it never runs a model."""

    def __init__(self) -> None:
        self.text = "{}"
        self.requests = []

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model")]

    def generate(self, request):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return GenerationResult(text=self.text, model=request.model, duration_ms=1)


def _load_annotations() -> dict:
    return json.loads((SAMPLE / "annotations.json").read_text(encoding="utf-8"))


def _load_chapters() -> list[tuple[int, str, str]]:
    chapters = []
    for path in sorted((SAMPLE / "chapters").glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        match = HEADING.match(lines[0])
        assert match, f"{path.name} has no numbered heading"
        chapters.append((int(match.group(1)), match.group(2), "\n".join(lines[1:]).strip()))
    return chapters


@pytest.fixture()
def benchmark(tmp_path: Path):
    data = _load_annotations()
    provider = ScriptedProvider()
    settings = Settings(
        data_dir=tmp_path / "data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    database = Database(settings.database_path)
    app = create_app(settings=settings, database=database, provider=provider)

    with TestClient(app) as client:
        services = app.state.services
        project = services.projects.create_project(
            name=data["project"]["name"],
            description=data["project"]["description"],
            genre=data["project"]["genre"],
            narrative_style=data["project"]["narrative_style"],
            target_word_count=data["project"]["target_word_count"],
        )
        for kind in DOCUMENT_KINDS:
            services.documents.save_document(
                project.id,
                kind,
                (SAMPLE / "blueprint" / f"{kind}.md").read_text(encoding="utf-8"),
            )

        chapter_ids: dict[int, int] = {}
        for position, title, content in _load_chapters():
            chapter = services.chapters.create_chapter(
                project_id=project.id,
                title=title,
                content=content,
                position=position,
            )
            chapter_ids[position] = chapter.id

        characters: dict[str, int] = {}
        for item in data["characters"]:
            character = services.characters.create_character(
                project_id=project.id,
                name=item["name"],
                aliases=item["aliases"],
                personality=item["personality"],
                secrets=item["secrets"],
            )
            characters[item["name"]] = character.id

        states = CharacterStateRepository(database)
        for item in data["states"]:
            states.create(
                project_id=project.id,
                character_id=characters[item["character"]],
                chapter_id=chapter_ids[item["chapter"]],
                location=item["location"],
                status=item["status"],
                goals=item["goals"],
                knowledge=item["knowledge"],
            )

        relationships = RelationshipRepository(database)
        for item in data["relationships"]:
            relationships.create(
                project_id=project.id,
                character_a_id=characters[item["a"]],
                character_b_id=characters[item["b"]],
                relation_type=item["relation_type"],
                description=item["description"],
                status=item["status"],
                source_event_id=None,
            )

        events = EventRepository(database)
        for item in data["events"]:
            events.replace_for_chapter(
                project.id,
                chapter_ids[item["chapter"]],
                [
                    EventDraft(
                        summary=item["summary"],
                        threads=tuple(item["threads"]),
                    )
                ],
                model="fake-model",
            )

        yield SimpleNamespace(
            client=client,
            services=services,
            provider=provider,
            data=data,
            project=project,
            chapter_ids=chapter_ids,
            characters=characters,
            database=database,
        )


def test_sample_contains_the_planted_narrative_features(benchmark) -> None:
    data = benchmark.data

    assert len(benchmark.chapter_ids) == 27
    assert [item["name"] for item in data["characters"]][:4] == [
        "Ilse Marrow",
        "Tamsin Roke",
        "Brann Ocque",
        "Sera Vane",
    ]
    assert all(item["aliases"] for item in data["characters"])
    assert "cut the lighthouse lens" in data["characters"][0]["secrets"]

    states = data["states"]
    ilse_locations = [
        item["location"] for item in states if item["character"] == "Ilse Marrow"
    ]
    assert ilse_locations == [
        "Cinder Point lighthouse",
        "the flooded archive of Veyra",
    ]
    assert "She believes the lens was lost" in next(
        item["knowledge"] for item in states if item["character"] == "Tamsin Roke"
    )

    mystery = {item["chapter"] for item in data["events"]}
    assert mystery == {6, 26}
    assert all(
        item["threads"] == ["Who cut the lighthouse lens?"]
        for item in data["events"]
    )

    pair = [
        (item["relation_type"], item["status"])
        for item in data["relationships"]
        if {item["a"], item["b"]} == {"Ilse Marrow", "Brann Ocque"}
    ]
    assert pair == [("ally", "approved"), ("rival", "proposed")]

    documents = benchmark.client.get(
        f"/api/projects/{benchmark.project.id}/documents"
    ).json()
    assert [item["kind"] for item in documents] == list(DOCUMENT_KINDS)


def test_retrieval_meets_recall_precision_and_rank_targets(benchmark) -> None:
    rows = []
    for probe in benchmark.data["probes"]:
        context = benchmark.services.context.build(
            benchmark.project.id,
            instructions=probe["instructions"],
            chapter_id=benchmark.chapter_ids[probe["chapter"]],
        )
        retrieved = [chapter.position for chapter in context.memory_chapters]
        expected = set(probe["expected"])
        matched = expected & set(retrieved)
        first = next(
            (index for index, position in enumerate(retrieved, start=1) if position in expected),
            None,
        )
        rows.append(
            {
                "probe": probe["id"],
                "expected": sorted(expected),
                "retrieved": retrieved,
                "recall": len(matched) / len(expected),
                "precision": len(matched) / len(retrieved) if retrieved else 0.0,
                "mrr": 1 / first if first else 0.0,
            }
        )

    assert all(row["recall"] == 1.0 for row in rows), rows
    assert all(row["precision"] == 1.0 for row in rows), rows
    assert all(row["mrr"] == 1.0 for row in rows), rows
    # Chapter 27 must not be handed its own or a later chapter as memory.
    assert all(max(row["retrieved"]) < 27 for row in rows), rows


def test_chapter_two_detail_is_returned_for_chapter_twenty_seven(benchmark) -> None:
    context = benchmark.services.context.build(
        benchmark.project.id,
        instructions="The brass astrolabe.",
        chapter_id=benchmark.chapter_ids[27],
    )

    assert [chapter.position for chapter in context.memory_chapters] == [2]
    chapter = context.memory_chapters[0]
    assert chapter.title == "The Brass Astrolabe"
    assert "brass astrolabe" in chapter.excerpt
    assert "third stair" in chapter.excerpt
    assert "Chapter 2 — The Brass Astrolabe" in context.earlier_chapters
    # The most recent chapters do not satisfy the query; this is not recency.
    assert not {24, 25, 26} & {
        chapter.position for chapter in context.memory_chapters
    }


def test_alias_and_secret_reach_the_generation_context(benchmark) -> None:
    alias_context = benchmark.services.context.build(
        benchmark.project.id,
        instructions="Where is the Gull?",
        chapter_id=benchmark.chapter_ids[27],
    )
    assert "Sera Vane" in alias_context.character_profiles
    assert "also: the Gull" in alias_context.character_profiles

    secret_context = benchmark.services.context.build(
        benchmark.project.id,
        instructions="What does Ilse know about the lens?",
        chapter_id=benchmark.chapter_ids[27],
        # A 16k window leaves room for both current state snapshots; the 4k
        # default budget can only carry the first one.
        context_window=16384,
    )
    assert "Secrets: She cut the lighthouse lens herself" in (
        secret_context.character_profiles
    )
    assert "Knowledge: She knows who cut the lighthouse lens" in (
        secret_context.character_states
    )
    ledger = benchmark.services.ledger.ledger(benchmark.project.id)
    tamsin = next(row for row in ledger["characters"] if row["name"] == "Tamsin Roke")
    knowledge = tamsin["snapshots"][-1]["knowledge"]
    assert "She believes the lens was lost in the storm." == knowledge
    assert "She knows who cut" not in knowledge


def test_unresolved_mystery_stays_open_in_the_ledger(benchmark) -> None:
    ledger = benchmark.services.ledger.ledger(benchmark.project.id)

    thread = next(
        item for item in ledger["threads"] if "lighthouse lens" in item["thread"]
    )
    assert thread["status"] == "open"
    assert thread["note"] == ""
    assert thread["resolved_chapter"] is None
    assert [chapter["position"] for chapter in thread["chapters"]] == [6, 26]
    assert ledger["counts"]["open_threads"] == 1


def test_location_change_is_recorded_with_provenance(benchmark) -> None:
    ledger = benchmark.services.ledger.ledger(benchmark.project.id)

    ilse = next(
        row for row in ledger["characters"] if row["name"] == "Ilse Marrow"
    )
    assert [snapshot["chapter_position"] for snapshot in ilse["snapshots"]] == [1, 12]
    first, second = ilse["snapshots"]
    assert first["location"] == "Cinder Point lighthouse"
    assert second["location"] == "the flooded archive of Veyra"
    assert "location" in second["changed"]
    assert ledger["counts"]["states"] == 4


def test_planted_contradiction_is_reported_by_the_audit(benchmark) -> None:
    audit = benchmark.client.get(
        f"/api/projects/{benchmark.project.id}/contradictions"
    ).json()

    assert audit["counts"]["findings"] == 1
    finding = audit["findings"][0]
    assert finding["kind"] == "conflicting_relationships"
    assert "ally" in finding["summary"] and "rival" in finding["summary"]
    assert len(finding["sources"]) == 2
    assert all("Relationship #" in source for source in finding["sources"])


CONTRADICTION_DRAFT = (
    "Ilse stood in the flooded archive of Veyra and swore she had never left "
    "Cinder Point. The pumps were still running."
)


def test_continuity_keeps_only_the_cited_location_finding(benchmark) -> None:
    chapter_id = benchmark.chapter_ids[27]
    saved = benchmark.client.patch(
        f"/api/chapters/{chapter_id}",
        json={"content": CONTRADICTION_DRAFT},
    )
    assert saved.status_code == 200, saved.text

    references = benchmark.services.continuity.canon_records(
        benchmark.project.id, 27
    )
    target = next(
        reference
        for reference in references
        if "Ilse Marrow" in reference.label
        and "flooded archive" in reference.label
    )
    benchmark.provider.text = json.dumps(
        {
            "findings": [
                {
                    "kind": "location",
                    "severity": "high",
                    "quote": "swore she had never left Cinder Point.",
                    "source": target.id,
                    "explanation": (
                        "The recorded state places Ilse in the flooded archive."
                    ),
                    "suggestion": "Reword the claim or change the setting.",
                },
                {
                    "kind": "location",
                    "severity": "high",
                    "quote": "Ilse flew over the harbor.",
                    "source": target.id,
                },
                {
                    "kind": "location",
                    "severity": "high",
                    "quote": "The pumps were still running.",
                    "source": "C999",
                },
            ]
        }
    )

    response = benchmark.client.post(
        f"/api/chapters/{chapter_id}/continuity", json={"model": "fake-model"}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["canon_count"] >= 6
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["quote"] == "swore she had never left Cinder Point."
    assert finding["source_id"] == target.id
    assert finding["source_kind"] == "state"
    assert finding["source_chapter_position"] == 12
    assert "flooded archive" in finding["source"]

    prompt = benchmark.provider.requests[0].prompt
    assert f"{target.id}: Character state · Ilse Marrow" in prompt
    assert CONTRADICTION_DRAFT in prompt
