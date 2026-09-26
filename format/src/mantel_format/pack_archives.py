"""Streaming v2 archive validation. Extraction never publishes installed content."""

from __future__ import annotations

import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .encoding import canonical, digest, file_digest
from .media import inspect_asset
from .pack_archive_index import CHUNK_SIZE, open_pack_archive, resource_chunks
from .pack_contracts import PackDefinition, PackManifest


@dataclass(frozen=True)
class ValidatedPack:
    manifest: PackManifest
    definition: PackDefinition
    archive_sha256: str
    archive_bytes: int
    expanded_bytes: int


def validate_archive(path: Path, destination: Path) -> ValidatedPack:
    """Destination must be a fresh private directory owned by the caller's job."""
    with open_pack_archive(path) as (
        archive,
        manifest,
        definition,
        total,
        manifest_raw,
        definition_raw,
    ):
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        (destination / "assets").mkdir()
        for resource in definition.resources:
            target = destination / resource.path
            with target.open("xb") as output:
                for chunk in resource_chunks(archive, resource):
                    output.write(chunk)
            inspect_asset(target, resource)
        (destination / "manifest.json").write_bytes(manifest_raw)
        (destination / "definition.json").write_bytes(definition_raw)
    return ValidatedPack(manifest, definition, file_digest(path), path.stat().st_size, total)


def build_archive(
    target: Path, manifest: PackManifest, definition: PackDefinition, assets: Path
) -> None:
    """Deterministic ZIP_STORED output; caller supplies a new output path."""
    raw = canonical(definition.model_dump(mode="json"))
    if manifest.definition_sha256 != digest(raw):
        raise ValueError("Definition hash mismatch")
    output = target.open("xb")
    try:
        with output, zipfile.ZipFile(output, "w") as archive:
            documents = {
                "manifest.json": canonical(manifest.model_dump(mode="json")),
                "definition.json": raw,
            }
            for name in sorted([*documents, *(resource.path for resource in definition.resources)]):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with archive.open(info, "w") as sink:
                    if name in documents:
                        sink.write(documents[name])
                    else:
                        with (assets / name).open("rb") as source:
                            while chunk := source.read(CHUNK_SIZE):
                                sink.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
