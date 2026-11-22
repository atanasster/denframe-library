"""Dependency-free canonical package encoding and streaming content hashes."""

import hashlib
import io
import json
import stat
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


#: Every element archive entry's time: fixed, so the same documents always zip to the same bytes.
ELEMENT_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
#: A pack archive entry's time, which the released packs' digests were computed with.
PACK_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def zip_entry(name: str, date_time: tuple[int, int, int, int, int, int]) -> zipfile.ZipInfo:
    """A deterministic archive entry: stored (not compressed), a regular 0644 file, at a fixed
    time."""
    info = zipfile.ZipInfo(name, date_time=date_time)
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def deterministic_zip(
    entries: Iterable[tuple[str, bytes]],
    *,
    date_time: tuple[int, int, int, int, int, int] = ELEMENT_ZIP_TIME,
) -> bytes:
    """`entries` as an archive whose bytes depend on nothing but the names, the contents and
    their order."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(zip_entry(name, date_time), content)
    return output.getvalue()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def forbidden_text_character(char: str) -> bool:
    code = ord(char)
    return (
        code < 0x20 or 0x7F <= code <= 0x9F or 0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069
    )


def check_text(value: Any) -> None:
    if isinstance(value, str):
        if any(forbidden_text_character(char) for char in value):
            raise ValueError("Package text contains control or bidi formatting characters")
    elif isinstance(value, list):
        for item in value:
            check_text(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            check_text(key)
            check_text(item)


def strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")),
    )
    check_text(value)
    return value


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
