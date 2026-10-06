"""Portable source documents and lossless media extraction for local authors."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .elements import Definition, Manifest, PortableBlock, SourceSlot, build_element, build_package
from .encoding import canonical, digest, strict_json
from .pack_archives import build_archive, validate_archive
from .pack_contracts import (
    MAX_PACK_DOCUMENTS,
    MAX_PACK_EXPANDED,
    PACK_KIND_CAPABILITIES,
    AnyPackDefinition,
    GalleryDefinition,
    PackDefinition,
    PackManifest,
    parse_pack_definition,
)
from .themes import BUILTIN_THEMES
from .validation import inspect_archive


def read_source(path: Path) -> tuple[dict, Definition | AnyPackDefinition, bytes]:
    """Build a bounded author document, preserving optional explicit manifest metadata."""
    with path.open("rb") as source:
        raw = source.read(MAX_PACK_DOCUMENTS + 1)
    if len(raw) > MAX_PACK_DOCUMENTS:
        raise ValueError("Author document exceeds size limit")
    item = strict_json(raw)
    if not isinstance(item, dict) or set(item) - {
        "id",
        "version",
        "definition",
        "slug",
        "publisher",
        "manifest",
    }:
        raise ValueError("Unknown author document field")
    if not {"id", "version", "definition"} <= set(item) or not isinstance(item["definition"], dict):
        raise ValueError("Author document needs id, version and definition")
    if "manifest" in item and not isinstance(item["manifest"], dict):
        raise ValueError("Manifest must be an object")
    definition: Definition | AnyPackDefinition
    manifest: Manifest | PackManifest
    if item["definition"].get("kind") in PACK_KIND_CAPABILITIES:
        definition = parse_pack_definition(item["definition"])
        values = {
            "publisher": item.get("publisher", "Local author"),
            "required_capabilities": list(PACK_KIND_CAPABILITIES[definition.kind]),
            **item.get("manifest", {}),
        }
        manifest = PackManifest.model_validate(source_manifest(item, definition, values))
        check_resources(path.parent, definition)
        with tempfile.TemporaryDirectory(prefix="denframe-author-") as temporary:
            target = Path(temporary) / "pack.denframepack"
            build_archive(target, manifest, definition, path.parent)
            require_valid(target)
            archive = target.read_bytes()
        return item, definition, archive
    definition = Definition.model_validate(item["definition"])
    if "manifest" in item:
        manifest = Manifest.model_validate(source_manifest(item, definition, item["manifest"]))
        archive = build_element(manifest, definition)
    else:
        if "publisher" in item:
            raise ValueError("A design publisher belongs in its manifest")
        archive = build_package(item["id"], item["version"], definition)
    with tempfile.TemporaryDirectory(prefix="denframe-author-") as temporary:
        target = Path(temporary) / "design.denframepack"
        target.write_bytes(archive)
        require_valid(target)
    return item, definition, archive


def source_manifest(item: dict, definition: Definition | AnyPackDefinition, values: dict) -> dict:
    if any(key in values and values[key] != item[key] for key in ("id", "version")):
        raise ValueError("Source and manifest identities differ")
    return {
        **values,
        "id": item["id"],
        "version": item["version"],
        "definition_sha256": digest(canonical(definition.model_dump(mode="json"))),
    }


def check_resources(root: Path, definition: AnyPackDefinition) -> None:
    total = 0
    for resource in definition.resources:
        path = root / resource.path
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Resource must be a file inside the source directory")
        if path.stat().st_size != resource.length:
            raise ValueError("Resource length differs from its inventory")
        total += resource.length
    if total > MAX_PACK_EXPANDED:
        raise ValueError("Source resources exceed expanded size limit")


def require_valid(path: Path) -> None:
    result = inspect_archive(path)
    if not result.valid:
        raise ValueError(result.error or "Invalid archive")


def write_new(path: Path, data: bytes) -> None:
    """Exclusive output: an author command never replaces another source or release."""
    output = path.open("xb")
    try:
        with output:
            output.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def unpack(path: Path, destination: Path) -> Path:
    result = inspect_archive(path)
    if not result.valid or result.manifest is None or result.definition is None:
        raise ValueError(result.error or "Invalid archive")
    item = {
        "id": result.manifest.id,
        "version": result.manifest.version,
        "manifest": result.manifest.model_dump(mode="json"),
        "definition": result.definition.model_dump(mode="json"),
    }
    with tempfile.TemporaryDirectory(prefix="denframe-unpack-") as temporary:
        staging = Path(temporary) / "source"
        if isinstance(result.definition, PackDefinition | GalleryDefinition):
            validate_archive(path, staging)
            (staging / "manifest.json").unlink()
            (staging / "definition.json").unlink()
        else:
            staging.mkdir()
        (staging / "source.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        destination.mkdir(mode=0o700)
        try:
            shutil.copytree(staging, destination, dirs_exist_ok=True)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination / "source.json"


def new_source(kind: str, identity: str, name: str, look: str, blocks: str, publisher: str) -> dict:
    definition: Definition | PackDefinition
    if kind == "pack":
        definition = PackDefinition.model_validate(
            {
                "name": name,
                "description": "Engineering draft; content review pending.",
                "locales": ["en"],
                "items": [
                    {
                        "id": "example",
                        "content_revision": 1,
                        "translations": {
                            "en": {
                                "prompt": {"text": "What comes next?"},
                                "reveal": {"text": "Your original answer."},
                            }
                        },
                    }
                ],
                "activities": [
                    {"id": "learn", "name": "Learn", "locale": "en", "item_ids": ["example"]}
                ],
            }
        )
        values: dict[str, Any] = {"publisher": publisher}
        PackManifest(
            id=identity,
            version="1.0.0",
            publisher=publisher,
            definition_sha256=digest(canonical(definition.model_dump(mode="json"))),
        )
    else:
        theme = next(t for t in BUILTIN_THEMES if t["look"] == look)
        kinds = [] if kind == "theme" else blocks.split(",")
        instances = [
            PortableBlock(
                id=f"{value}-{index + 1}",
                kind=value,
                source_slot=f"source-{index + 1}" if value != "clock" else None,
            )
            for index, value in enumerate(kinds)
        ]
        definition = Definition.model_validate(
            {
                "kind": kind,
                "name": name,
                "look": look,
                "appearance": {**theme["appearance"], "tokens": theme["tokens"]},
                "blocks": instances,
                "source_slots": [
                    SourceSlot(id=b.source_slot, kind=b.kind) for b in instances if b.source_slot
                ],
            }
        )
        build_package(identity, "1.0.0", definition)
        values = {"manifest": {"publisher": publisher, "license": "MIT"}}
    item = {
        "id": identity,
        "version": "1.0.0",
        **values,
        "definition": definition.model_dump(mode="json"),
    }
    strict_json(canonical(item))
    if isinstance(definition, Definition):
        Manifest.model_validate(source_manifest(item, definition, values["manifest"]))
    return item
