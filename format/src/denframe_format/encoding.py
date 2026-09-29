"""Dependency-free canonical package encoding and streaming content hashes."""

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


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
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()
