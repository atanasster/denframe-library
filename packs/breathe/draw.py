"""Breathe: one activity of six slow breathing cycles that ends after the sixth, four counts in, four held, four
out, four held, paced by the card's own timing (prompt 4 s, recall 4 s, reveal 4 s, dwell 4 s).
Two drawn pictures -- full rings to breathe in by, a small ring to breathe out by -- and no sound,
no quiz and nothing that animates. Rewrites this folder's assets and source.json; see
../drawing.py."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from drawing import REPOSITORY, SIZE, face, svg, write_pack  # noqa: E402

PLATE = "#eef3f1"
RING = "#3f7f74"
SOFT = "#bcd9d2"
DOT = "#26292e"


def rings(full: bool) -> str:
    """Concentric rings: all five drawn when the lungs are full, the smallest alone when empty.
    Four dots round the outside stand for the four counts of each step."""
    c = SIZE / 2
    radii = [60, 110, 160, 210, 260]
    parts = []
    if full:
        parts.append(f'<circle cx="{c}" cy="{c}" r="{radii[-1]}" fill="{SOFT}"/>')
        for radius in radii:
            parts.append(
                f'<circle cx="{c}" cy="{c}" r="{radius}" fill="none" stroke="{RING}" '
                f'stroke-width="14"/>'
            )
    else:
        for radius in radii[1:]:
            parts.append(
                f'<circle cx="{c}" cy="{c}" r="{radius}" fill="none" stroke="{SOFT}" '
                f'stroke-width="6" stroke-dasharray="4 22" stroke-linecap="round"/>'
            )
        parts.append(
            f'<circle cx="{c}" cy="{c}" r="{radii[0]}" fill="{SOFT}" stroke="{RING}" '
            f'stroke-width="14"/>'
        )
    for x, y in ((c, c - 330), (c + 330, c), (c, c + 330), (c - 330, c)):
        parts.append(f'<circle cx="{x}" cy="{y}" r="16" fill="{DOT}"/>')
    return svg("".join(parts), PLATE)


PICTURES = {"in": rings(True), "out": rings(False)}
ALT = {
    "in": "Five wide rings, one inside another, filling the picture, with four dots around them.",
    "out": "One small ring in the middle, with faint dotted rings around it and four dots.",
}
CREDIT = {
    "creator": "Denframe",
    "license": "CC0-1.0",
    "attribution": "Original ring drawing, made in code with AI assistance.",
    "source": f"{REPOSITORY}/breathe",
    "modified": False,
}
CYCLES = [
    (
        "Sit comfortably. If you feel dizzy, stop and breathe normally. Breathe in slowly for four… "
        "then hold for four.",
        "Breathe out slowly for four… then hold for four.",
    ),
    ("Breathe in for four… hold for four.", "Breathe out for four… hold for four."),
    ("Breathe in for four… hold for four.", "Breathe out for four… hold for four."),
    ("Breathe in for four… hold for four.", "Breathe out for four… hold for four."),
    ("Breathe in for four… hold for four.", "Breathe out for four… hold for four."),
    (
        "Last one. Breathe in for four… hold for four.",
        "Breathe out for four… hold for four. Then breathe normally.",
    ),
]


SOURCES = [
    {
        "supports": "The 4-4-4-4 pattern (box breathing: in, hold, out, hold, four counts each) "
        "as a described technique only; the pack makes no health claim.",
        "url": "https://health.clevelandclinic.org/box-breathing-benefits",
    },
]


def main() -> None:
    items = [
        {
            "id": f"cycle-{index}",
            "content_revision": 1,
            "translations": {
                "en": {
                    "prompt": face(breathe_in, "in", ALT["in"]),
                    "reveal": face(breathe_out, "out", ALT["out"]),
                }
            },
            "audio_cues": [],
        }
        for index, (breathe_in, breathe_out) in enumerate(CYCLES, start=1)
    ]
    write_pack(
        HERE,
        header={
            "id": "denframe/breathe",
            "version": "1.0.0",
            "publisher": "Denframe",
            "definition": {
                "schema_version": 2,
                "kind": "pack",
                "name": "Breathe",
                "description": (
                    "Six slow breaths at an even pace: in for four, hold for four, out for four, "
                    "hold for four, then it ends. Drawn rings, no sound. Not medical advice; stop "
                    "if you feel dizzy."
                ),
                "locales": ["en"],
            },
        },
        pictures=PICTURES,
        credit={key: CREDIT for key in PICTURES},
        items=items,
        activities=[
            {
                "id": "breathe",
                "name": "Breathe",
                "kind": "reveal-sequence-v1",
                "item_ids": [item["id"] for item in items],
                "locale": "en",
                "loop": False,
                "timing": {
                    "prompt_seconds": 4,
                    "recall_seconds": 4,
                    "reveal_seconds": 4,
                    "dwell_seconds": 4,
                },
            },
        ],
        provenance={
            "pack": "denframe/breathe",
            "drawn": "2026-09-27",
            "authorship": "Text and drawing code drafted for Denframe with AI assistance (Claude); "
            "a person reviews every pack before it is approved (plan D26).",
            "narration": "None. eSpeak NG, the only voice the plan allows (D26), was not "
            "installed where the pack was drawn; the cards are text-first and silent.",
            "sources": SOURCES,
        },
    )


if __name__ == "__main__":
    main()
