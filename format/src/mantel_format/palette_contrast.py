"""The one contrast gate a dashboard palette clears (fill step 15).

`contracts/composition/palette-contrast.json` specifies it -- the pairs, the scrim's
compositing and rounding, and the conformance vectors -- and the browser's `paletteVerdict`
reads that file directly. This module mirrors it in code, because the runtime does not ship the
contracts directory; `tests/test_palette_contrast.py` pins the mirror to the file and runs
every vector.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

REQUIRED = 4.5
TEXT_FACES = ("background", "surface", "captionSurface", "scrim")
PAIRS: tuple[tuple[str, str], ...] = (
    *(("text", face) for face in TEXT_FACES),
    *(("mutedText", face) for face in TEXT_FACES),
    ("positive", "surface"),
    ("negative", "surface"),
    ("accent", "surface"),
    ("accentText", "accent"),
)
#: The pairs a stored palette was first held to, before the scrim joined the gate: the model
#: validator reads these, so a palette stored under them still loads.
STORED_PAIRS = tuple(pair for pair in PAIRS if pair[1] != "scrim")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class PaletteVerdict:
    """The first pair a palette fails: which text on which face, the ratio it reaches (rounded
    down to two places, so it never reads as passing) and the ratio it needs."""

    text: str
    face: str
    ratio: float
    required: float = REQUIRED

    def detail(self) -> dict[str, object]:
        return {"pair": [self.text, self.face], "ratio": self.ratio, "required": self.required}


class PaletteContrastError(ValueError):
    """A palette refused by the gate, carrying the pair it fails.

    Raised inside model validation, so a request whose body is refused while FastAPI parses it
    still reaches the client as the structured `palette-contrast` reason
    (`routes.http_errors`), never as the validator's internals."""

    def __init__(self, verdict: PaletteVerdict) -> None:
        super().__init__("Theme colours must meet minimum contrast on their surfaces")
        self.verdict = verdict


def _channel(byte: int) -> float:
    value = byte / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    red, green, blue = (_channel(int(color[index : index + 2], 16)) for index in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground: str, background: str) -> float:
    darker, lighter = sorted((luminance(foreground), luminance(background)))
    return (lighter + 0.05) / (darker + 0.05)


def _inverse_channel(linear: float) -> float:
    clamped = max(0.0, min(1.0, linear))
    normalized = clamped * 12.92 if clamped <= 0.0031308 else 1.055 * clamped ** (1 / 2.4) - 0.055
    return normalized * 255


def scrim_hex(tokens: dict[str, str]) -> str:
    """The worst-case backdrop text reads over a picture: the scrim, at the alpha that brings a
    white (or black) pixel to the caption surface's luminance, composited over that pixel."""
    light_text = luminance(tokens["text"]) > luminance(tokens["background"])
    gray = _inverse_channel(luminance(tokens["captionSurface"]))
    alpha = math.ceil((1 - gray / 255 if light_text else gray / 255) * 100) / 100
    scrim, pixel = (0, 255) if light_text else (255, 0)
    byte = max(0, min(255, math.floor(scrim * alpha + pixel * (1 - alpha) + 0.5)))
    return f"#{byte:02x}{byte:02x}{byte:02x}"


def palette_verdict(
    tokens: dict[str, str], *, pairs: tuple[tuple[str, str], ...] = PAIRS
) -> PaletteVerdict | None:
    """The first pair a complete palette fails, in the specification's order; `None` when every
    pair clears. A colour that is not `#rrggbb` is no palette at all and raises."""
    for role, value in tokens.items():
        if not _HEX.fullmatch(value):
            raise ValueError(f"Invalid colour for {role}")
    faces = {**tokens, "scrim": scrim_hex(tokens)}
    for text, face in pairs:
        ratio = contrast(tokens[text], faces[face])
        if ratio < REQUIRED:
            return PaletteVerdict(text, face, math.floor(ratio * 100) / 100)
    return None
