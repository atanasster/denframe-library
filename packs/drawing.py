"""Shared drawing and assembly for the activity packs whose illustrations are drawn in code
(plan D26): each pack's `draw.py` describes its pictures as SVG and its cards as data, and this
module turns them into the pack's source.

- SVG is rasterised with `rsvg-convert` (librsvg), then re-encoded by Pillow as an 8-bit
  palette PNG with no ancillary chunks: no text, time, colour-profile or EXIF metadata.
- Nothing uses a font: numerals are drawn as strokes (`numeral`), so a picture does not depend
  on the fonts of the machine that draws it.
- The PNG bytes are committed; the build copies them and never redraws. Running a pack's
  `draw.py` again with the same librsvg, cairo (which librsvg rasterises through, and whose
  antialiasing decides the pixels), Pillow and zlib reproduces them byte for byte (the pack's
  `provenance.json` records the versions used).

Run from the repository root: `python3 packs/<slug>/draw.py` (needs `rsvg-convert` and
Pillow). It rewrites `packs/<slug>/assets/` and `packs/<slug>/source.json`.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path

from PIL import Image

SIZE = 800
REPOSITORY = "https://github.com/atanasster/denframe-library/tree/main/packs"

# Stroke numerals in a 10 x 16 box (origin top left), drawn with round caps and joins.
_DIGITS = {
    "0": "M5,0 C1.5,0 0.5,4 0.5,8 C0.5,12 1.5,16 5,16 C8.5,16 9.5,12 9.5,8 C9.5,4 8.5,0 5,0 Z",
    "1": "M2,3.5 L6,0 L6,16",
    "2": "M1,4 C1,1 3,0 5,0 C7.5,0 9,1.7 9,4 C9,8 1,11 1,16 L9.5,16",
    "3": "M1,2 C2.5,0.3 4,0 5,0 C7.5,0 9,1.5 9,3.8 C9,6.3 7,7.6 4.2,7.6 C7.6,7.6 9.5,9.4 9.5,12 "
    "C9.5,14.6 7.5,16 5,16 C3.2,16 1.6,15.3 0.6,14",
    "4": "M7,16 L7,0 L0.5,11 L9.5,11",
    "5": "M9,0 L2,0 L1.2,7 C2.5,6 3.7,5.7 5,5.7 C7.8,5.7 9.5,7.7 9.5,10.8 C9.5,14 7.6,16 4.8,16 "
    "C3.1,16 1.6,15.3 0.6,14",
    "6": "M8.4,1.2 C7.5,0.4 6.4,0 5.4,0 C2.3,0 0.6,3.6 0.6,9 C0.6,13.6 2.3,16 5,16 "
    "C7.8,16 9.4,14 9.4,11 C9.4,8.2 7.6,6.3 5.1,6.3 C3,6.3 1.3,7.6 0.7,9.6",
    "7": "M0.5,0 L9.5,0 L4,16",
    "8": "M5,7.6 C2.6,7.6 1.2,6.2 1.2,3.8 C1.2,1.5 2.8,0 5,0 C7.2,0 8.8,1.5 8.8,3.8 "
    "C8.8,6.2 7.4,7.6 5,7.6 C2.2,7.6 0.5,9.3 0.5,11.8 C0.5,14.4 2.4,16 5,16 C7.6,16 9.5,14.4 "
    "9.5,11.8 C9.5,9.3 7.8,7.6 5,7.6 Z",
    "9": "M1.6,14.8 C2.5,15.6 3.6,16 4.6,16 C7.7,16 9.4,12.4 9.4,7 C9.4,2.4 7.7,0 5,0 "
    "C2.2,0 0.6,2 0.6,5 C0.6,7.8 2.4,9.7 4.9,9.7 C7,9.7 8.7,8.4 9.3,6.4",
}


def numeral(text: str, cx: float, cy: float, height: float, colour: str, weight: float) -> str:
    """`text` (digits) centred on (cx, cy), `height` tall, as stroked paths."""
    scale = height / 16
    advance = 12 * scale
    width = advance * (len(text) - 1) + 10 * scale
    left = cx - width / 2
    paths = []
    for index, digit in enumerate(text):
        x = left + index * advance
        paths.append(
            f'<path d="{_DIGITS[digit]}" transform="translate({x:.2f},{cy - height / 2:.2f}) '
            f'scale({scale:.4f})" fill="none" stroke="{colour}" '
            f'stroke-width="{weight / scale:.3f}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return "".join(paths)


def svg(body: str, background: str, size: int = SIZE) -> str:
    """A square picture on its own plate, so it reads on a light or a dark look alike."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}"><rect width="{size}" height="{size}" '
        f'fill="{background}"/>{body}</svg>'
    )


def render(document: str, size: int = SIZE) -> bytes:
    """SVG -> PNG bytes: librsvg, then an 8-bit palette PNG with no metadata chunks."""
    raster = subprocess.run(
        ["rsvg-convert", "--format=png", f"--width={size}", f"--height={size}"],
        input=document.encode(),
        capture_output=True,
        check=True,
    ).stdout
    with Image.open(io.BytesIO(raster)) as image:
        rgb = image.convert("RGB")
    palette = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    output = io.BytesIO()
    palette.save(output, format="PNG", optimize=True)
    return output.getvalue()


def tool_versions() -> dict[str, str]:
    """The drawing toolchain, for provenance: librsvg and the cairo it draws with (from
    `rsvg-convert --version`'s "libraries used"), Pillow and the zlib it compresses with."""
    import PIL
    from PIL import features

    lines = subprocess.run(
        ["rsvg-convert", "--version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    libraries = dict(line.split() for line in lines[1:] if len(line.split()) == 2)
    return {
        "rsvg-convert": lines[0].removeprefix("rsvg-convert version ").strip(),
        "cairo": libraries.get("cairo", "unknown"),
        "Pillow": PIL.__version__,
        "zlib": features.version("zlib") or "unknown",
    }


def write_pack(
    folder: Path,
    *,
    header: dict,
    pictures: dict[str, str],
    credit: dict[str, dict],
    items: list[dict],
    activities: list[dict],
    provenance: dict,
) -> dict[str, str]:
    """Draw `pictures` (key -> SVG) into `folder/assets` and write `folder/source.json`.

    Each item's faces name a picture by key (`"image": "<key>"`); the source gets the drawn
    file's path. `credit` maps each key to its resource credit. `provenance` (sources, notes)
    goes into `folder/provenance.json` with the toolchain and every drawn file, which stays
    beside the source and out of the archive. Returns key -> asset path.
    """
    # Draw everything first: a failed drawing leaves the folder as it was.
    drawn = {key: render(document) for key, document in pictures.items()}
    assets = folder / "assets"
    assets.mkdir(exist_ok=True)
    for stale in assets.glob("*.png"):
        stale.unlink()
    paths, resources = {}, []
    for key, data in drawn.items():
        digest = hashlib.sha256(data).hexdigest()
        path = f"assets/{digest}.png"
        if path in paths.values():
            raise ValueError(f"Two pictures draw the same bytes: {key}")
        (folder / path).write_bytes(data)
        paths[key] = path
        resources.append(
            {
                "path": path,
                "sha256": digest,
                "length": len(data),
                "media_type": "image/png",
                "duration_seconds": None,
                "credit": credit[key],
            }
        )
    used = set()
    for item in items:
        for translation in item["translations"].values():
            for face in translation.values():
                if face.get("image") is not None:
                    used.add(face["image"])
                    face["image"] = paths[face["image"]]
    if used != set(pictures):
        raise ValueError(
            f"Pictures without a card, or cards without a picture: {used ^ set(pictures)}"
        )
    definition = {
        **header["definition"],
        "resources": resources,
        "items": items,
        "activities": activities,
    }
    document = {**header, "definition": definition}
    (folder / "source.json").write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    shown_by = {
        key: sorted(
            {
                item["id"]
                for item in items
                for translation in item["translations"].values()
                for face in translation.values()
                if face.get("image") == path
            }
        )
        for key, path in paths.items()
    }
    # A person's recorded verdict on a picture holds while the picture is the same bytes (its
    # path is its content hash); a changed or new picture waits for review again.
    kept = {}
    if (folder / "provenance.json").exists():
        for asset in json.loads((folder / "provenance.json").read_text())["assets"]:
            kept[asset["path"]] = {
                key: asset[key] for key in ("visual_review", "visual_review_note") if key in asset
            }
    record = {
        **provenance,
        "method": "SVG drawn by draw.py, rasterised by rsvg-convert, re-encoded by Pillow as an "
        "8-bit palette PNG with no metadata chunks. Original work: no image-generation model, "
        "stock or third-party artwork.",
        "toolchain": tool_versions(),
        "assets": [
            {
                "picture": key,
                "path": paths[key],
                "bytes": (folder / paths[key]).stat().st_size,
                "media_type": "image/png",
                "width": SIZE,
                "height": SIZE,
                "license": credit[key]["license"],
                "items": shown_by[key],
                "visual_review": "pending",
                **kept.get(paths[key], {}),
            }
            for key in pictures
        ],
    }
    (folder / "provenance.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return paths


def face(text: str, image: str | None = None, alt: str | None = None) -> dict:
    return {"text": text, "image": image, "alt_text": alt}
