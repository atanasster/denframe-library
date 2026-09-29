"""Bounded asset inspection. Called only in a disposable validation process."""

from __future__ import annotations

import warnings
from pathlib import Path

from PIL import Image

from .media_limits import MAX_DECODED_PIXELS
from .media_metadata import check_image_metadata, mp3_audio_start
from .pack_contracts import MAX_PACK_AUDIO_SECONDS, PackResource


def mp3_duration(data: bytes) -> float:
    """Inspect complete MPEG Layer III frames, rejecting free bitrate and trailing data."""
    position = mp3_audio_start(data)
    duration = 0.0
    frames = 0
    while position < len(data):
        if position + 4 > len(data):
            raise ValueError("Truncated MP3 frame")
        header = int.from_bytes(data[position : position + 4], "big")
        version = (header >> 19) & 3
        bitrate_index = (header >> 12) & 15
        sample_index = (header >> 10) & 3
        if (
            header >> 21 != 0x7FF
            or version == 1
            or ((header >> 17) & 3) != 1
            or bitrate_index in (0, 15)
            or sample_index == 3
        ):
            raise ValueError("Unsupported MP3 frame")
        rates = (
            (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
            if version == 3
            else (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
        )
        sample_rate = (44100, 48000, 32000)[sample_index] // {3: 1, 2: 2, 0: 4}[version]
        frame_size = (144 if version == 3 else 72) * rates[bitrate_index] * 1000 // sample_rate
        frame_size += (header >> 9) & 1
        position += frame_size
        if position > len(data):
            raise ValueError("Truncated MP3 frame")
        duration += (1152 if version == 3 else 576) / sample_rate
        frames += 1
        if duration > MAX_PACK_AUDIO_SECONDS + 0.1:
            raise ValueError("MP3 duration exceeds limit")
    if frames < 2:
        raise ValueError("MP3 requires complete audio frames")
    return duration


def inspect_asset(path: Path, resource: PackResource) -> None:
    if resource.media_type == "audio/mpeg":
        duration = mp3_duration(path.read_bytes())
        # Encoder delay/padding accounts for at most a few frame durations.
        if resource.duration_seconds is None or abs(duration - resource.duration_seconds) > 0.1:
            raise ValueError("MP3 duration does not match inventory")
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
                if (
                    image.format != expected[resource.media_type]
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Unsupported image format or animation")
                width, height = image.size
                if (
                    min(width, height) < 1
                    or max(width, height) > 20_000
                    or width * height > MAX_DECODED_PIXELS
                ):
                    raise ValueError("Image decoded dimensions exceed limit")
                check_image_metadata(path.read_bytes(), expected[resource.media_type])
                image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image decoded dimensions exceed limit") from exc
