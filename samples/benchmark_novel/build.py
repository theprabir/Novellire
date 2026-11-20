"""Build the synthetic retrieval and continuity benchmark sample.

Run from the repository root:

    python samples/benchmark_novel/build.py

The generated Markdown and ``annotations.json`` are committed, so tests read the
sample as an author would import it. This file is the single source of truth for
the dataset; edit it and rerun to regenerate.

The prose is deliberately controlled:

* ``astrolabe``, ``brass``, ``third``, and ``stair`` appear only in chapter 2, so
  chapter 27's retrieval probe has one correct source.
* ``flooded`` and ``archive`` appear only in chapters 12, 13, and 19.
* ``gull`` and ``ledger`` appear only in chapters 9, 12, and 18.
* the lighthouse lens is cut in chapter 6, mentioned again in chapter 26, and
  never resolved.

Filler chapters avoid those terms so recall and precision measure retrieval
rather than coincidental word overlap.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CHAPTERS: list[tuple[str, str]] = [
    (
        "The Eroding Coast",
        "Ilse Marrow came back to Cinder Point with three blank charts and a "
        "borrowed coat. The cliff had lost another two paces since her last "
        "survey, and the lighthouse stood closer to the water than she "
        "remembered. Brann Ocque watched her from the harbor gate without "
        "raising a hand.",
    ),
    (
        "The Brass Astrolabe",
        "Before the storm, Ilse wrapped the brass astrolabe in oilcloth and hid "
        "it beneath the third stair of the Cinder Point lighthouse. The "
        "instrument had belonged to her father, and the harbor inquiry would "
        "ask where it had gone. She told Tamsin only that the survey tools were "
        "safe. Then the wind rose and the lamp went dark.",
    ),
    (
        "A Survey of Salt",
        "Morning left a white crust on every railing. Ilse measured the "
        "high-water line while Tamsin copied numbers into a fresh notebook. "
        "The work was slow and ordinary, which was what Ilse wanted. By noon "
        "the tide had pulled back far enough to expose the old jetty posts.",
    ),
    (
        "The Apprentice",
        "Tamsin Roke could name every channel between the harbor and the outer "
        "shoals. She had learned them from fishermen, not from charts, and she "
        "corrected Ilse twice before lunch. Ilse pretended to be annoyed and "
        "wrote the corrections down. In the afternoon she began teaching the "
        "girl how to read a sounding line.",
    ),
    (
        "The Harbor Gate",
        "Brann kept the gate log locked in the gatehouse, though he never "
        "wrote in it himself. He counted the boats out and the boats in, and "
        "he counted Ilse's return as a debt. They spoke for the first time in "
        "eleven years beside the chain winch, and neither of them mentioned "
        "their mother.",
    ),
    (
        "The Cut Lens",
        "The lamp keeper found the lens split cleanly across its face, as if "
        "someone had scored the glass and waited for the cold. No storm does "
        "that. The harbor committee called it vandalism and offered a reward, "
        "but nobody came forward. Ilse looked at the break for a long time and "
        "said nothing.",
    ),
    (
        "Low Tide",
        "The water withdrew further than the oldest fishermen had seen. Ilse "
        "walked out across the weed and counted the ribs of a wreck she had "
        "charted as buried. Tamsin stayed on the shingle and called out the "
        "depth at each marker. They returned before the turn, wet to the knee "
        "and pleased with themselves.",
    ),
    (
        "The Tidewarden's Offer",
        "Brann proposed that Ilse survey the outer channel for the harbor "
        "office. The fee was generous and the deadline was impossible. He "
        "said the committee needed an answer before the autumn gales, and he "
        "did not say who had recommended her. Ilse accepted, because refusing "
        "would have looked like fear.",
    ),
    (
        "The Gull's Passage",
        "Sera Vane, whom the harbor called the Gull, kept her ledger in a "
        "tarred pouch and her boat in a creek the charts forgot. She offered "
        "Ilse passage to the outer shoals for a price she would not name. "
        "Tamsin recognized the boat and went quiet. They left before dawn, "
        "with no lantern showing.",
    ),
    (
        "The Storm Cellar",
        "The gale drove everyone below the harbor line. In the cellar, Brann "
        "passed out blankets and pretended not to know which families were "
        "missing a father. Ilse sat with the survey books against her chest "
        "and listened to the sea test the doors. By morning the gatehouse roof "
        "was gone.",
    ),
    (
        "The Lamp Room",
        "With the lamp dark, the tower became a plain stone column. Ilse "
        "climbed to the lamp room and found the keeper's tools arranged as "
        "carefully as always. The broken glass had been swept into a corner. "
        "She pocketed one shard, then climbed back down before the keeper "
        "could ask what she wanted.",
    ),
    (
        "The Flooded Archive",
        "The lower archive of Veyra had been flooded for a generation, and the "
        "city had finally voted to drain it. Ilse took the contract to chart "
        "the rooms before the pumps started. She moved her survey office into "
        "the flooded archive that same week, with Tamsin and the ledger of "
        "tides carried up the west stairs. The water stood knee-deep and "
        "perfectly still.",
    ),
    (
        "A Map of Water",
        "They worked from a flat-bottomed punt, marking shelves and doorways "
        "that had not been seen since the flood. The flooded archive kept its "
        "own weather: cold air, slow drips, and a smell of wet paper. Tamsin "
        "found a room of broken instruments and asked whether any of them "
        "could be sold. Ilse said they were evidence, not stock. The vault "
        "kept the rest of its rooms closed.",
    ),
    (
        "The Long Galleries",
        "The eastern galleries ran further than the city plans admitted. Ilse "
        "measured them twice and got two different answers, which meant the "
        "floor was moving. She marked the discrepancy in red and told Tamsin "
        "to write down the time of each reading. Nothing in the vault was "
        "as stable as it looked.",
    ),
    (
        "The Missing Sounding",
        "A page had been cut from the harbor's oldest sounding book. The gap "
        "fell exactly where the outer channel deepened, and the committee "
        "could not say who had held the book last. Brann claimed the volume "
        "had never left the gatehouse. Tamsin remembered seeing it in the "
        "cellar during the gale.",
    ),
    (
        "Sera's Price",
        "Sera wanted the vault's west stair opened before the pumps ran. She "
        "would not say why, and she would not take money. Ilse refused, then "
        "spent the night wondering what Sera expected to find below the "
        "waterline. In the morning Sera was gone and the creek was empty.",
    ),
    (
        "The Keeper's Confession",
        "The lamp keeper admitted he had moved the oil stores without telling "
        "the committee. He had been afraid of being dismissed for hoarding. "
        "Ilse asked him nothing about the glass. He seemed grateful for that, "
        "and then asked her, very quietly, whether she had come home to sell "
        "the tower.",
    ),
    (
        "The Ledger of Tides",
        "Ilse opened the ledger of tides and found three entries in a hand she "
        "knew. The ink was fresh, the dates were wrong, and the depths matched "
        "no survey she had ever taken. She copied the entries into her own "
        "book and locked the ledger away again. Someone had been writing the "
        "coast's future before it happened.",
    ),
    (
        "The Drowned Stacks",
        "The pumps reached the lowest shelf and the flooded archive began to "
        "give up its dead. Ilse catalogued water-stained registers while "
        "Tamsin carried them to the drying frames. One register listed every "
        "ship the harbor had lost, including the Merrow, whose loss the city "
        "still argued about. The last page had been torn out.",
    ),
    (
        "The Harbor Inquiry",
        "The committee met in the custom house with the windows shut. Brann "
        "answered every question about the gate log and none about the "
        "missing sounding. Ilse presented her charts and watched the members "
        "study Brann rather than the coast. The inquiry closed without a "
        "finding, which everyone treated as a verdict.",
    ),
    (
        "The Brother's Debt",
        "Brann came to the records hall at dusk and stood in the water rather than "
        "cross the threshold. He said the family debt had been paid, though "
        "Ilse had never asked him to pay it. She told him the tower was not "
        "for sale. He laughed once, without humor, and left the way he came.",
    ),
    (
        "The Coast Moves",
        "The autumn survey showed the outer channel shallower by a full fathom. "
        "Ilse checked the instrument, the tide table, and her own arithmetic. "
        "The coast was moving faster than any chart could follow, and the "
        "harbor's new depth would not survive the winter. She wrote the "
        "finding plainly, then wrote it again for the committee.",
    ),
    (
        "A Second Survey",
        "Tamsin ran the second survey alone and came back with numbers that "
        "matched Ilse's. The girl was proud and trying not to show it. Ilse "
        "gave her the good sounding line and told her to sign the sheet. For "
        "one afternoon the vault felt like a place where something was "
        "being built.",
    ),
    (
        "The Empty Lighthouse",
        "The keeper left without notice, taking nothing but his coat. Ilse "
        "climbed the tower and found the lamp room swept clean and the door "
        "locked from the inside. She did not force it. From the gallery she "
        "could see the whole harbor, the new shallows, and the road where "
        "Brann's cart waited.",
    ),
    (
        "The Tide Chart",
        "The committee published a tide chart based on Ilse's old soundings. "
        "She wrote to correct it and received no answer. Tamsin wanted to "
        "post the new survey on the custom house door. Ilse said a chart was "
        "not an argument, and that they would need proof the committee could "
        "not dismiss.",
    ),
    (
        "The Lens Again",
        "A fragment of the lighthouse lens turned up in the custom house wreck "
        "register, wrapped in oilcloth and labeled as salvage. The break "
        "matched the shard Ilse had pocketed. Someone had brought the glass "
        "here before the flood and left it among the records, as if filing it "
        "away would settle the question. It did not.",
    ),
    (
        "The Third Stair",
        "The tide receded far enough to walk to Cinder Point without a boat. "
        "Ilse went back to the lighthouse and knelt beneath the third stair. "
        "The oilcloth was still there, and the brass astrolabe inside it had "
        "not rusted. She carried it out into the light while Tamsin watched. "
        "Now the harbor would have to believe the survey, and Ilse would have "
        "to explain how she had known where to look.",
    ),
]

BLUEPRINT = {
    "master_bible": """# Master Story Bible

## Premise

The Salt Cartographer follows Ilse Marrow, a coastal surveyor, as she returns
to the harbor of Cinder Point and discovers that the coast is moving faster
than the charts admit.

## Main storyline

Ilse hides her father's brass astrolabe beneath the third stair of the
lighthouse before a storm. The lamp lens is later found cut cleanly, and no
one admits to the act. When the lower archive of Veyra is drained, Ilse takes
the contract to chart it, moves her office into the flooded archive, and finds
records that were never meant to survive the water. Her final survey proves the
outer channel has shifted, and the instrument she hid in chapter two becomes
the proof the harbor cannot dismiss.

## Open question

Who cut the lighthouse lens? The question is raised in chapter six and again
in chapter twenty-six. It is intentionally left unresolved.

## Themes

Proof versus authority, family debt, and the difference between a chart and a
coast.
""",
    "character_bible": """# Character Bible

## Ilse Marrow (also: the Salt Surveyor)

A coastal cartographer in her forties. Careful, stubborn, and unwilling to
explain herself. She knows who cut the lighthouse lens and has told no one.
Her secret is that she scored the glass herself the night the Merrow sank, to
keep the harbor committee from using the lamp as an alibi.

## Tamsin Roke (also: Tam, the Ledger Girl)

Ilse's apprentice. Quick with numbers and eager to be trusted. She believes
the lens was lost in the storm. She does not know Ilse's secret.

## Brann Ocque (also: the Tidewarden)

Harbor master and Ilse's estranged brother. He keeps the gate ledger and the
family debt. He knows Ilse is his sister; the harbor does not.

## Sera Vane (also: the Gull)

A smuggler who keeps her ledger in a tarred pouch and knows the channels the
charts forgot. She wants the archive's west stair opened and will not say why.

## Keeper Noll (also: the Lampwright)

The lighthouse keeper. He moved the oil stores and is ashamed of it. He knows
more about the broken glass than he will admit.
""",
    "chapter_map": "\n".join(
        f"- Chapter {index}: {title}"
        for index, (title, _) in enumerate(CHAPTERS, start=1)
    ),
    "style_guide": """# Style Guide

## Narrative perspective

Close third person, past tense, limited to Ilse's point of view except where a
chapter explicitly follows Tamsin.

## Sentence structure

Prefer short declarative sentences and concrete coastal detail. Allow one long
sentence per page at most.

## Dialogue

Dialogue is sparse and indirect. Characters rarely state their feelings; they
answer a different question than the one asked.

## What to avoid

Do not resolve the lighthouse lens question. Do not name the culprit. Keep the
Merrow's loss contested, and do not let the model promote a suspicion to canon.
""",
}

ANNOTATIONS = {
    "project": {
        "name": "The Salt Cartographer",
        "description": "A surveyor returns to a harbor whose coast is moving.",
        "genre": "Literary fantasy",
        "narrative_style": "Close third person, past tense",
        "target_word_count": 80_000,
    },
    "characters": [
        {
            "name": "Ilse Marrow",
            "aliases": ["the Salt Surveyor"],
            "role": "Protagonist",
            "personality": "Careful, stubborn, private.",
            "secrets": (
                "She cut the lighthouse lens herself and has told no one."
            ),
        },
        {
            "name": "Tamsin Roke",
            "aliases": ["Tam", "the Ledger Girl"],
            "role": "Apprentice",
            "personality": "Quick, proud, eager to be trusted.",
            "secrets": "She believes the lens was lost in the storm.",
        },
        {
            "name": "Brann Ocque",
            "aliases": ["the Tidewarden"],
            "role": "Harbor master",
            "personality": "Guarded and proud.",
            "secrets": "He is Ilse's brother, and the harbor does not know.",
        },
        {
            "name": "Sera Vane",
            "aliases": ["the Gull"],
            "role": "Smuggler",
            "personality": "Patient, transactional, amused.",
            "secrets": "She wants the archive's west stair opened.",
        },
        {
            "name": "Keeper Noll",
            "aliases": ["the Lampwright"],
            "role": "Lighthouse keeper",
            "personality": "Apologetic and watchful.",
            "secrets": "He moved the oil stores and fears dismissal.",
        },
    ],
    "states": [
        {
            "character": "Ilse Marrow",
            "chapter": 1,
            "location": "Cinder Point lighthouse",
            "status": "weary but working",
            "goals": "Survey the eroding coast before the inquiry.",
            "knowledge": (
                "She knows who cut the lighthouse lens and has told no one."
            ),
        },
        {
            "character": "Ilse Marrow",
            "chapter": 12,
            "location": "the flooded archive of Veyra",
            "status": "determined",
            "goals": "Chart the archive before the pumps reach the lowest shelf.",
            "knowledge": (
                "She knows who cut the lighthouse lens and has told no one; "
                "the brass astrolabe is hidden beneath the third stair."
            ),
        },
        {
            "character": "Tamsin Roke",
            "chapter": 12,
            "location": "the flooded archive of Veyra",
            "status": "curious",
            "goals": "Learn to sign her own survey.",
            "knowledge": "She believes the lens was lost in the storm.",
        },
        {
            "character": "Brann Ocque",
            "chapter": 1,
            "location": "the harbor gate",
            "status": "watchful",
            "goals": "Keep the gate ledger and the family debt quiet.",
            "knowledge": "He knows Ilse is his sister.",
        },
    ],
    "relationships": [
        {
            "a": "Ilse Marrow",
            "b": "Brann Ocque",
            "relation_type": "ally",
            "description": "Estranged siblings keeping a truce for the harbor.",
            "status": "approved",
        },
        {
            "a": "Ilse Marrow",
            "b": "Brann Ocque",
            "relation_type": "rival",
            "description": "A dispute over the lighthouse lease.",
            "status": "proposed",
        },
    ],
    "events": [
        {
            "chapter": 6,
            "summary": (
                "The lighthouse lens is found cut cleanly across its face."
            ),
            "threads": ["Who cut the lighthouse lens?"],
        },
        {
            "chapter": 26,
            "summary": (
                "A fragment of the lighthouse lens is found in the archive's "
                "wreck register."
            ),
            "threads": ["Who cut the lighthouse lens?"],
        },
    ],
    "probes": [
        {
            "id": "astrolabe",
            "chapter": 27,
            "instructions": "The brass astrolabe.",
            "expected": [2],
        },
        {
            "id": "flooded_archive",
            "chapter": 27,
            "instructions": "The flooded archive.",
            "expected": [12, 13, 19],
        },
        {
            "id": "gull_ledger",
            "chapter": 27,
            "instructions": "Gull ledger.",
            "expected": [9, 12, 18],
        },
    ],
}


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")


def main() -> None:
    chapters_dir = ROOT / "chapters"
    blueprint_dir = ROOT / "blueprint"
    chapters_dir.mkdir(exist_ok=True)
    blueprint_dir.mkdir(exist_ok=True)

    for index, (title, prose) in enumerate(CHAPTERS, start=1):
        path = chapters_dir / f"{index:02d}-{_slug(title)}.md"
        path.write_text(
            f"# {index}. {title}\n\n{prose.strip()}\n", encoding="utf-8"
        )

    for kind, content in BLUEPRINT.items():
        (blueprint_dir / f"{kind}.md").write_text(
            content.strip() + "\n", encoding="utf-8"
        )

    (ROOT / "annotations.json").write_text(
        json.dumps(ANNOTATIONS, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(CHAPTERS)} chapters and {len(BLUEPRINT)} documents to {ROOT}")


if __name__ == "__main__":
    main()
