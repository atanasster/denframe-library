"""Reject descriptive media metadata without rewriting signed resource bytes."""

from __future__ import annotations

from .encoding import check_text


def _synchsafe(raw: bytes) -> int:
    if len(raw) != 4 or any(byte & 128 for byte in raw):
        raise ValueError("Invalid MP3 tag size")
    return sum(byte << (7 * (3 - index)) for index, byte in enumerate(raw))


def mp3_audio_start(data: bytes) -> int:
    if not data.startswith(b"ID3"):
        return 0
    if len(data) < 10 or data[3] not in (3, 4) or data[4:6] != b"\x00\x00":
        raise ValueError("Unsupported MP3 tag")
    end = 10 + _synchsafe(data[6:10])
    if end > len(data) or end > 4096:
        raise ValueError("Invalid MP3 tag length")
    position = 10
    seen_encoder = False
    while position < end:
        if not any(data[position:end]):
            break
        header = data[position : position + 10]
        if len(header) != 10 or header[:4] != b"TSSE" or header[8:] != b"\x00\x00" or seen_encoder:
            raise ValueError("MP3 metadata is not allowed except an encoder tag")
        size = _synchsafe(header[4:8]) if data[3] == 4 else int.from_bytes(header[4:8], "big")
        position += 10
        if size < 2 or size > 1024 or position + size > end:
            raise ValueError("Invalid MP3 encoder tag")
        frame = data[position : position + size]
        encodings = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}
        if frame[0] not in encodings or (data[3] == 3 and frame[0] > 1):
            raise ValueError("Unsupported MP3 text encoding")
        text = frame[1:].decode(encodings[frame[0]]).removesuffix("\x00")
        if not text.strip():
            raise ValueError("Empty MP3 encoder tag")
        check_text(text)
        seen_encoder = True
        position += size
    return end


def check_image_metadata(data: bytes, kind: str) -> None:
    """Allow image structure and pixel data; refuse metadata and unknown ancillary chunks."""
    if kind == "PNG":
        position = 8
        allowed = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
        while position < len(data):
            if position + 12 > len(data):
                raise ValueError("Truncated PNG chunk")
            size = int.from_bytes(data[position : position + 4], "big")
            chunk = data[position + 4 : position + 8]
            if chunk not in allowed:
                raise ValueError("Image metadata is not allowed")
            position += size + 12
            if position > len(data):
                raise ValueError("Truncated PNG chunk")
    elif kind == "WEBP":
        position = 12
        while position < len(data):
            if position + 8 > len(data):
                raise ValueError("Truncated WebP chunk")
            chunk = data[position : position + 4]
            size = int.from_bytes(data[position + 4 : position + 8], "little")
            if chunk not in {b"VP8 ", b"VP8L", b"VP8X", b"ALPH"}:
                raise ValueError("Image metadata is not allowed")
            position += 8 + size + size % 2
            if position > len(data):
                raise ValueError("Truncated WebP chunk")
    elif kind == "JPEG":
        _check_jpeg_metadata(data)


def _check_jpeg_metadata(data: bytes) -> None:
    position = 2
    in_scan = False
    while position < len(data):
        if in_scan:
            position = data.find(b"\xff", position)
            if position < 0:
                raise ValueError("Missing JPEG end marker")
        elif data[position] != 0xFF:
            raise ValueError("Invalid JPEG marker")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise ValueError("Truncated JPEG marker")
        marker = data[position]
        position += 1
        if in_scan and (marker == 0 or 0xD0 <= marker <= 0xD7):
            continue
        if marker == 0xD9:
            if position != len(data):
                raise ValueError("JPEG trailing metadata is not allowed")
            return
        if position + 2 > len(data):
            raise ValueError("Truncated JPEG segment")
        size = int.from_bytes(data[position : position + 2], "big")
        if size < 2 or position + size > len(data):
            raise ValueError("Truncated JPEG segment")
        if marker == 0xFE or 0xE1 <= marker <= 0xEF:
            raise ValueError("Image metadata is not allowed")
        if marker == 0xE0:
            segment = data[position + 2 : position + size]
            if len(segment) != 14 or segment[:5] != b"JFIF\x00" or segment[-2:] != b"\0\0":
                raise ValueError("Image metadata is not allowed")
        position += size
        in_scan = marker == 0xDA
    raise ValueError("Missing JPEG end marker")
