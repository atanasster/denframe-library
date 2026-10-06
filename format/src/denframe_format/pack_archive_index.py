"""Dependency-free bounded ZIP index and streaming resource verification."""

from __future__ import annotations

import hashlib
import zipfile
import zlib
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from .archive_validation import ArchiveLimits, validated_archive
from .encoding import canonical, digest, strict_json
from .pack_contracts import (
    MAX_PACK_ARCHIVE,
    MAX_PACK_COMPRESSION_RATIO,
    MAX_PACK_DOCUMENTS,
    MAX_PACK_EXPANDED,
    MAX_PACK_FILES,
    PACK_KIND_CAPABILITIES,
    AnyPackDefinition,
    PackManifest,
    PackResource,
    parse_pack_definition,
)

CHUNK_SIZE = 64 * 1024


@contextmanager
def _open_pack_archive(
    path: Path,
) -> Iterator[tuple[ZipFile, PackManifest, AnyPackDefinition, int, bytes, bytes]]:
    limits = ArchiveLimits(
        MAX_PACK_ARCHIVE, MAX_PACK_EXPANDED, MAX_PACK_FILES, MAX_PACK_COMPRESSION_RATIO
    )
    with validated_archive(path, limits) as index:
        archive, names, total = index.archive, index.names, index.expanded_bytes
        if not {"manifest.json", "definition.json"}.issubset(names):
            raise ValueError("Missing pack documents")
        manifest_raw = index.read("manifest.json", MAX_PACK_DOCUMENTS)
        definition_raw = index.read("definition.json", MAX_PACK_DOCUMENTS - len(manifest_raw))
        manifest = PackManifest.model_validate(strict_json(manifest_raw))
        definition = parse_pack_definition(strict_json(definition_raw))
        if set(manifest.required_capabilities) != set(PACK_KIND_CAPABILITIES[definition.kind]):
            raise ValueError("Manifest capabilities do not match the definition's kind")
        if definition_raw != canonical(definition.model_dump(mode="json")):
            raise ValueError("Definition must use canonical encoding with explicit defaults")
        if digest(definition_raw) != manifest.definition_sha256:
            raise ValueError("Definition hash mismatch")
        expected = {"manifest.json", "definition.json"} | {r.path for r in definition.resources}
        if set(names) != expected:
            raise ValueError("Resource inventory does not match archive")
        yield archive, manifest, definition, total, manifest_raw, definition_raw


@contextmanager
def open_pack_archive(
    path: Path,
) -> Iterator[tuple[ZipFile, PackManifest, AnyPackDefinition, int, bytes, bytes]]:
    try:
        with _open_pack_archive(path) as value:
            yield value
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, RecursionError, zlib.error) as exc:
        raise ValueError("Invalid pack archive") from exc


def resource_chunks(
    archive: zipfile.ZipFile, resource: PackResource
) -> Generator[bytes, Any, None]:
    entry = archive.getinfo(resource.path)
    if entry.file_size != resource.length:
        raise ValueError("Resource length mismatch")
    hashed = hashlib.sha256()
    written = 0
    with archive.open(entry) as source:
        while chunk := source.read(CHUNK_SIZE):
            written += len(chunk)
            if written > resource.length:
                raise ValueError("Resource exceeds inventory length")
            hashed.update(chunk)
            yield chunk
    if written != resource.length or hashed.hexdigest() != resource.sha256:
        raise ValueError("Resource hash mismatch")
