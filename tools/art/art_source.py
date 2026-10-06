"""A curated collection as a gallery pack source (art backgrounds plan, D2, D12).

`curation.json` records what was curated; `source.json` is what the library builds: a `gallery`
definition (the format's `GalleryDefinition`) whose resources are the curated files under
`assets/`, each named by its own SHA-256. The format validates it here, so a curation that
would not build fails where it was made.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from denframe_format.pack_contracts import GalleryDefinition

#: What a work's placard or credit field may hold, by the format's text grammar.
SHORT, DISPLAY, CREDIT = 100, 240, 500


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _resource(out: Path, path: str, media_type: str, work: Mapping[str, Any] | None) -> dict:
    data = (out / path).read_bytes()
    placard = work["placard"] if work else {}
    return {
        "path": path,
        "sha256": Path(path).stem,
        "length": len(data),
        "media_type": media_type,
        "duration_seconds": None,
        "credit": {
            "creator": _clip(placard.get("creator") or "Denframe", SHORT),
            "license": "CC0-1.0",
            "attribution": _clip(
                f"{placard.get('title')} · {placard.get('creator')} · "
                f"{placard.get('institution')} · CC0"
                if work
                else "The collection's first works, side by side.",
                CREDIT,
            ),
            "source": _clip(placard.get("canonical_url", ""), CREDIT),
            # A receiver derivative is resized and re-encoded from the museum's file.
            "modified": True,
        },
    }


def source_definition(record: Mapping[str, Any], out: Path) -> dict:
    """The gallery definition for a curation record, validated by the format."""
    resources = []
    works = []
    for work in record["works"]:
        placard = work["placard"]
        title, creator = (
            _clip(placard.get("title"), DISPLAY),
            _clip(placard.get("creator"), DISPLAY),
        )
        resources.append(_resource(out, work["file"], "image/jpeg", work))
        resources.append(_resource(out, work["thumbnail"], "image/webp", work))
        evidence = {
            key: value
            for key, value in work["rights"]["evidence"].items()
            if key
            in (
                "provider_field",
                "provider_value",
                "image_url",
                "observed_at",
                "image_field",
                "uuid",
            )
        }
        works.append(
            {
                "id": f"{work['provider']}-{work['object_id']}".lower()[:40],
                "image": work["file"],
                "thumbnail": work["thumbnail"],
                "alt_text": _clip(work.get("alt_text") or f"{title}, by {creator}", DISPLAY),
                "width": work["width"],
                "height": work["height"],
                "orientation": work["orientation"],
                "focal_x": 0.5,
                "focal_y": 0.5,
                "mean_colour": work["mean_colour"],
                "placard": {
                    "title": title,
                    "creator": creator,
                    "date": _clip(placard.get("date"), SHORT),
                    "medium": _clip(placard.get("medium"), DISPLAY) or None,
                    "dimensions": _clip(placard.get("dimensions"), DISPLAY) or None,
                    "institution": _clip(placard.get("institution"), SHORT),
                    "canonical_url": placard["canonical_url"],
                },
                "rights": {
                    "license": "CC0-1.0",
                    "uri": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "evidence": {"image_field": None, "uuid": None, **evidence},
                },
            }
        )
    resources.append(_resource(out, record["strip"], "image/webp", None))
    definition = GalleryDefinition.model_validate(
        {
            "schema_version": 2,
            "kind": "gallery",
            "name": record["name"],
            "description": record["description"],
            "shape": record["shape"],
            "strip": record["strip"],
            "resources": resources,
            "works": works,
        }
    )
    return definition.model_dump(mode="json")


def write_source(record: Mapping[str, Any], brief: Mapping[str, Any], out: Path) -> None:
    """`source.json` beside the curation: the pack id, version and publisher come from the brief."""
    document = {
        "id": brief["id"],
        "version": brief["version"],
        "publisher": brief.get("publisher", "Denframe"),
        "definition": source_definition(record, out),
    }
    (out / "source.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
