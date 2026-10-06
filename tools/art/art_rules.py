"""The selection rules an art collection's works are held to (art backgrounds plan, D5/D6).

A wall screen shows a picture all day, behind text, in a family room. These are the rules a
machine can check; subject and variety (D6.5-6) are a person's, on the contact sheet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageStat

Shape = Literal["landscape", "portrait"]

#: The box a receiver derivative is fitted into, by the collection's shape (D5).
BOXES: dict[Shape, tuple[int, int]] = {"landscape": (1920, 1080), "portrait": (1080, 1920)}

#: Width over height a work may have, by the collection's shape (D6.3). Outside it the work is
#: refused, never cropped.
ASPECT_BANDS: dict[Shape, tuple[float, float]] = {
    "landscape": (1.25, 2.1),
    "portrait": (0.5, 0.8),
}

#: Mean luminance a work's picture must sit between (D6.4): a scrim keeps text readable over
#: anything, but not cheaply over a near-black or a near-white picture.
LUMINANCE_BAND = (0.12, 0.85)

#: The share of a picture that may be blown out (above `CLIPPED_HIGH`) or crushed (below
#: `CLIPPED_LOW`) before it is refused (D6.4).
CLIPPED_SHARE = 0.25
CLIPPED_LOW = 0.02
CLIPPED_HIGH = 0.98

#: The placard fields a work must carry (D6.7).
PLACARD_FIELDS = ("title", "creator", "date")


@dataclass(frozen=True)
class Verdict:
    """A work's check: the reasons it is refused, empty when it is admitted."""

    reasons: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return not self.reasons


def fitted_size(width: int, height: int, shape: Shape) -> tuple[int, int]:
    """The size a picture of `width` x `height` takes when fitted to its shape's box: larger
    than the source where the source is smaller, which `check_work` refuses (D6.2)."""
    box_width, box_height = BOXES[shape]
    scale = min(box_width / width, box_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def tone(image: Image.Image) -> tuple[float, float]:
    """The picture's mean luminance and the share of it clipped to black or white, 0-1."""
    grey = image.convert("L")
    mean = ImageStat.Stat(grey).mean[0] / 255
    histogram = grey.histogram()
    total = sum(histogram) or 1
    low = sum(histogram[: int(CLIPPED_LOW * 255) + 1])
    high = sum(histogram[math.ceil(CLIPPED_HIGH * 255) :])
    return mean, (low + high) / total


def normalised_creator(value: str | None) -> str | None:
    """A creator on one line: museums put a nationality and dates on lines of their own."""
    if value is None:
        return None
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[0] if len(lines) == 1 else f"{lines[0]} ({', '.join(lines[1:])})"


def check_work(image: Image.Image, placard: dict[str, str | None], shape: Shape) -> Verdict:
    """Hold one work to the rules a machine can check (D6.2-4, D6.7)."""
    reasons: list[str] = []
    width, height = image.size
    fitted = fitted_size(width, height, shape)
    box_width, box_height = BOXES[shape]
    # D6.2: the source covers what it is fitted to, so the derivative is only ever downsampled.
    needed_scale = min(box_width / width, box_height / height)
    if needed_scale > 1:
        reasons.append(f"source {width}x{height} would be upscaled to {fitted[0]}x{fitted[1]}")
    low, high = ASPECT_BANDS[shape]
    aspect = width / height
    if not low <= aspect <= high:
        reasons.append(f"aspect {aspect:.2f} is outside the {shape} band {low}-{high}")
    mean, clipped = tone(image)
    if not LUMINANCE_BAND[0] <= mean <= LUMINANCE_BAND[1]:
        low_mean, high_mean = LUMINANCE_BAND
        reasons.append(f"mean luminance {mean:.2f} is outside {low_mean}-{high_mean}")
    if clipped > CLIPPED_SHARE:
        reasons.append(f"{clipped:.0%} of the picture is blown out or crushed")
    for field in PLACARD_FIELDS:
        if not (placard.get(field) or "").strip():
            reasons.append(f"placard has no {field}")
    return Verdict(tuple(reasons))
