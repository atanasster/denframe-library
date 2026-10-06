"""Curate an art collection from a brief: fetch, check, derive, record (art backgrounds plan).

    python scripts/art/curate.py library/src/packs/calm-landscapes/brief.json

A brief names the collection and, in order, each work by its provider and object id. Every work
is fetched by its provider (which admits it only on that provider's own rights signal, D7), held
to the selection rules (D6), and turned into the receiver derivative and thumbnail (D5) beside
the brief. `curation.json` records what was admitted and what was refused and why, and
`contact-sheet.html` puts every admitted work at screen size with its placard for the review
of subject and variety (D6.5-6), which no machine makes. Museums are asked here, at authoring
time, never by a household's hub (D3); the committed files are what a build packs (D12).
"""

from __future__ import annotations

import argparse
import html
import io
import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from art_derive import STRIP_WORKS, derivative, mean_colour, sha256, strip, thumbnail
from art_rules import Shape, check_work, normalised_creator
from art_source import write_source
from art_works import Provider, Refused
from PIL import Image, ImageOps, UnidentifiedImageError

#: The only licence an art collection's works carry (D6.1).
LICENCE = "CC0-1.0"

#: How many works by one creator a collection may hold before the review is asked to look (D6.6).
WORKS_PER_CREATOR = 2

#: Seconds between two works fetched from one provider: museums ask for single-threaded,
#: unhurried use of their open APIs.
FETCH_PAUSE_SECONDS = 1.0

#: The files a run writes; a re-run removes the last one's first, so nothing stale is packed.
GENERATED = ("assets/*.jpg", "assets/*.webp", "source.json")


@dataclass
class Curation:
    brief: Mapping[str, Any]
    works: list[dict[str, Any]] = field(default_factory=list)
    refused: list[dict[str, Any]] = field(default_factory=list)


def read_brief(path: Path) -> dict[str, Any]:
    brief = json.loads(path.read_text(encoding="utf-8"))
    for key in ("slug", "name", "description", "shape", "works"):
        if key not in brief:
            raise SystemExit(f"{path}: the brief has no {key}")
    if brief["shape"] not in ("landscape", "portrait"):
        raise SystemExit(f"{path}: shape must be landscape or portrait")
    return brief


def curate(
    brief: Mapping[str, Any],
    out: Path,
    providers: Mapping[str, Provider],
    *,
    today: Callable[[], date] = date.today,
    sleep: Callable[[float], None] = time.sleep,
) -> Curation:
    """Fetch, check and derive every work in `brief` into `out`; return what happened."""
    shape: Shape = brief["shape"]
    curation = Curation(brief)
    # Only the strip's works are kept: a whole collection of full-size sources would not fit.
    strip_images: list[Image.Image] = []
    for pattern in GENERATED:
        for stale in out.glob(pattern):
            stale.unlink()
    (out / "assets").mkdir(parents=True, exist_ok=True)
    asked: set[str] = set()
    listed: set[tuple[str, str]] = set()
    for entry in brief["works"]:
        provider_name, object_id = str(entry["provider"]), str(entry["object_id"])
        refusal = {"provider": provider_name, "object_id": object_id}
        if (provider_name, object_id) in listed:
            curation.refused.append({**refusal, "reasons": ["listed twice in the brief"]})
            continue
        listed.add((provider_name, object_id))
        provider = providers.get(provider_name)
        if provider is None:
            curation.refused.append({**refusal, "reasons": [f"no provider {provider_name}"]})
            continue
        if provider_name in asked:
            sleep(FETCH_PAUSE_SECONDS)
        asked.add(provider_name)
        try:
            work = provider.fetch(object_id)
        except Refused as exc:
            curation.refused.append({**refusal, "reasons": [str(exc)]})
            continue
        if work.rights.get("license") != LICENCE:
            curation.refused.append({**refusal, "reasons": ["not CC0"]})
            continue
        try:
            with Image.open(io.BytesIO(work.image)) as opened:
                # Upright before any rule: a rotated JPEG is held to the shape it shows as.
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            curation.refused.append({**refusal, "reasons": ["the image does not decode"]})
            continue
        placard = {
            **work.placard,
            "creator": normalised_creator(work.placard.get("creator")),
        }
        verdict = check_work(image, placard, shape)
        if not verdict.admitted:
            curation.refused.append({**refusal, "reasons": list(verdict.reasons)})
            continue
        picture = derivative(image, shape)
        digest = sha256(picture)
        (out / "assets" / f"{digest}.jpg").write_bytes(picture)
        small = thumbnail(image)
        small_digest = sha256(small)
        (out / "assets" / f"{small_digest}.webp").write_bytes(small)
        with Image.open(io.BytesIO(picture)) as fitted:
            width, height = fitted.size
        curation.works.append(
            {
                "provider": provider_name,
                "object_id": object_id,
                "file": f"assets/{digest}.jpg",
                "sha256": digest,
                "length": len(picture),
                "width": width,
                "height": height,
                "orientation": "portrait" if height > width else "landscape",
                "mean_colour": mean_colour(picture),
                "thumbnail": f"assets/{small_digest}.webp",
                "alt_text": entry.get("alt_text"),
                "placard": placard,
                "rights": dict(work.rights),
            }
        )
        if len(strip_images) < STRIP_WORKS:
            strip_images.append(image)
    strip_file = None
    if strip_images:
        strip_bytes = strip(strip_images)
        strip_file = f"assets/{sha256(strip_bytes)}.webp"
        (out / strip_file).write_bytes(strip_bytes)
    record = {
        "schema_version": 1,
        "slug": brief["slug"],
        "name": brief["name"],
        "description": brief["description"],
        "shape": shape,
        "curated_on": today().isoformat(),
        "strip": strip_file,
        "works": curation.works,
        "refused": curation.refused,
        "review_notes": review_notes(curation.works),
    }
    (out / "curation.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "contact-sheet.html").write_text(contact_sheet(record), encoding="utf-8")
    if curation.works and "id" in brief and "version" in brief:
        write_source(record, brief, out)
    return curation


def review_notes(works: list[dict[str, Any]]) -> list[str]:
    """What the review is asked to look at: more than two works by one creator (D6.6)."""
    creators = Counter(str(work["placard"].get("creator")) for work in works)
    return [
        f"{creator} has {count} works (at most {WORKS_PER_CREATOR} per collection)"
        for creator, count in sorted(creators.items())
        if count > WORKS_PER_CREATOR
    ]


def contact_sheet(record: Mapping[str, Any]) -> str:
    """Every admitted work at screen size with its placard, and every refusal with its reasons."""

    def text(value: object) -> str:
        return html.escape("" if value is None else str(value))

    works = "\n".join(
        f"""<figure><img src="{text(work["file"])}" alt="" loading="lazy">
<figcaption><b>{text(work["placard"].get("title"))}</b><br>{text(work["placard"].get("creator"))}
· {text(work["placard"].get("date"))}<br>{text(work["placard"].get("institution"))} ·
{text(work["width"])}x{text(work["height"])} · {text(work["mean_colour"])}</figcaption></figure>"""
        for work in record["works"]
    )
    refused = "\n".join(
        f"<li>{text(item['provider'])} {text(item['object_id'])}: "
        f"{text('; '.join(item['reasons']))}</li>"
        for item in record["refused"]
    )
    notes = "\n".join(f"<li>{text(note)}</li>" for note in record["review_notes"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{text(record["name"])} · contact sheet</title>
<style>body{{font:16px system-ui;margin:24px;background:#222;color:#eee}}
figure{{margin:0 0 32px}}img{{max-width:100%;max-height:90vh;display:block;background:#000}}
figcaption{{margin-top:8px}}</style></head><body>
<h1>{text(record["name"])}</h1><p>{text(record["description"])}</p>
<p>{len(record["works"])} admitted, {len(record["refused"])} refused ·
curated {text(record["curated_on"])}</p>
<h2>Review notes</h2><ul>{notes or "<li>None</li>"}</ul>
<p>Look at each work for subject (no violence, death, nudity, devotional scenes or distress) and
at the set for variety of colour (D6.5-6).</p>
{works}
<h2>Refused</h2><ul>{refused or "<li>None</li>"}</ul>
</body></html>
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("brief", type=Path)
    options = parser.parse_args(argv)
    from art_providers import PROVIDERS

    brief = read_brief(options.brief)
    curation = curate(brief, options.brief.parent, PROVIDERS)
    sys.stderr.write(
        f"{brief['slug']}: {len(curation.works)} admitted, {len(curation.refused)} refused\n"
    )


if __name__ == "__main__":
    main()
