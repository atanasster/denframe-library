"""The files a curated work becomes (art backgrounds plan, D5).

A receiver derivative fitted to its shape's box, a small thumbnail, and per collection a strip of
its first works. Each is encoded the same way every time from the same source, so a curation
re-run reproduces the bytes its record names.
"""

from __future__ import annotations

import hashlib
import io

from art_rules import Shape, fitted_size
from PIL import Image, ImageCms, ImageOps

#: JPEG quality for a receiver derivative (D5): about 250-400 KB for a painting at 1920 px.
DERIVATIVE_QUALITY = 82

#: A thumbnail's longest side, and the most it may weigh (LIBRARY_ASSETS_PLAN D32).
THUMBNAIL_SIDE = 480
THUMBNAIL_BUDGET = 60 * 1024

#: The collection strip: three works side by side, each this tall.
STRIP_HEIGHT = 160
STRIP_WORKS = 3


def srgb(image: Image.Image) -> Image.Image:
    """The picture in sRGB, upright, in RGB mode, with no metadata carried over."""
    image = ImageOps.exif_transpose(image)
    profile = image.info.get("icc_profile")
    if profile:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            image = ImageCms.profileToProfile(
                image, source, ImageCms.createProfile("sRGB"), outputMode="RGB"
            )
        except (OSError, ImageCms.PyCMSError):
            image = image.convert("RGB")
    rgb = image.convert("RGB")
    # A fresh image holds only pixels: no EXIF, ICC, comments or thumbnails survive.
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    return clean


def derivative(image: Image.Image, shape: Shape) -> bytes:
    """The receiver derivative: fitted to the shape's box, progressive JPEG, sRGB, bare."""
    picture = srgb(image)
    size = fitted_size(*picture.size, shape)
    if size != picture.size:
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    picture.save(output, "JPEG", quality=DERIVATIVE_QUALITY, progressive=True, optimize=True)
    return output.getvalue()


def thumbnail(image: Image.Image) -> bytes:
    """A WebP thumbnail under its budget, stepping the quality down until it fits."""
    picture = srgb(image)
    picture.thumbnail((THUMBNAIL_SIDE, THUMBNAIL_SIDE), Image.Resampling.LANCZOS)
    return webp_within_budget(picture, "thumbnail")


def strip(images: list[Image.Image]) -> bytes:
    """A collection's first works side by side, for a picker or a Library card."""
    if not images:
        raise ValueError("a strip needs at least one work")
    scaled = []
    for image in images[:STRIP_WORKS]:
        picture = srgb(image)
        width = max(1, round(picture.width * STRIP_HEIGHT / picture.height))
        scaled.append(picture.resize((width, STRIP_HEIGHT), Image.Resampling.LANCZOS))
    gap = 4
    canvas = Image.new(
        "RGB",
        (sum(item.width for item in scaled) + gap * (len(scaled) - 1), STRIP_HEIGHT),
        (255, 255, 255),
    )
    left = 0
    for item in scaled:
        canvas.paste(item, (left, 0))
        left += item.width + gap
    return webp_within_budget(canvas, "strip")


def webp_within_budget(picture: Image.Image, what: str) -> bytes:
    """`picture` as WebP under `THUMBNAIL_BUDGET`, stepping the quality down until it fits."""
    for quality in (80, 70, 60, 50, 40):
        output = io.BytesIO()
        picture.save(output, "WEBP", quality=quality, method=6)
        if output.tell() <= THUMBNAIL_BUDGET:
            return output.getvalue()
    raise ValueError(f"{what} does not fit its budget")


def mean_colour(data: bytes) -> str:
    """The derivative's average colour, as `#rrggbb`: a backdrop while it loads."""
    with Image.open(io.BytesIO(data)) as image:
        tiny = image.convert("RGB").resize((1, 1), Image.Resampling.BOX)
        red, green, blue = tiny.getpixel((0, 0))
    return f"#{red:02x}{green:02x}{blue:02x}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
