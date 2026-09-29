"""Layered format inspection; publisher trust is supplied by the consuming application."""

from __future__ import annotations

import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .archive_validation import ArchiveLimits, validated_archive
from .elements import (
    MAX_ARCHIVE,
    MAX_EXPANDED,
    Definition,
    Manifest,
    read_package,
    required_capabilities,
)
from .encoding import digest, strict_json
from .pack_archive_index import open_pack_archive
from .pack_archives import validate_archive
from .pack_contracts import (
    MAX_PACK_ARCHIVE,
    MAX_PACK_COMPRESSION_RATIO,
    MAX_PACK_DOCUMENTS,
    MAX_PACK_EXPANDED,
    MAX_PACK_FILES,
    PackDefinition,
    PackManifest,
)
from .themes import palette_verdict_for

Verdict = Literal["pass", "fail", "warning", "not applicable", "not checked"]
LAYERS = ("archive", "json", "schema", "capabilities", "contrast", "media", "trust")
PACK_LIMITS = ArchiveLimits(
    MAX_PACK_ARCHIVE, MAX_PACK_EXPANDED, MAX_PACK_FILES, MAX_PACK_COMPRESSION_RATIO
)


@dataclass
class Inspection:
    layers: dict[str, Verdict] = field(default_factory=lambda: dict.fromkeys(LAYERS, "not checked"))
    manifest: Manifest | PackManifest | None = None
    definition: Definition | PackDefinition | None = None
    error: str | None = None

    @property
    def valid(self) -> bool:
        return "fail" not in self.layers.values() and self.definition is not None

    def summary(self) -> dict:
        return {
            "valid": self.valid,
            "layers": self.layers,
            "error": self.error,
            "manifest": self.manifest.model_dump(mode="json") if self.manifest else None,
            "definition": self.definition.model_dump(mode="json") if self.definition else None,
        }


def inspect_archive(path: Path, *, version: int | None = None) -> Inspection:
    """Validate private media in a temporary directory, never installing or granting trust."""
    result = Inspection()
    layer = "archive"
    try:
        if version is None:
            with validated_archive(path, PACK_LIMITS) as index:
                if "manifest.json" not in index.names:
                    raise ValueError("Missing manifest.json")
                manifest_raw = index.read("manifest.json", MAX_PACK_DOCUMENTS)
            result.layers["archive"] = "pass"
            layer = "json"
            manifest = strict_json(manifest_raw)
            layer = "schema"
            if not isinstance(manifest, dict):
                raise ValueError("Manifest must be an object")
            version = manifest.get("schema_version", 1)
        if version not in (1, 2):
            raise ValueError("Unsupported archive schema version")
        layer = "archive"
        limits = ArchiveLimits(MAX_ARCHIVE, MAX_EXPANDED, 2) if version == 1 else PACK_LIMITS
        document_limit = MAX_EXPANDED if version == 1 else MAX_PACK_DOCUMENTS
        with validated_archive(path, limits) as index:
            if version == 1 and set(index.names) != {"manifest.json", "definition.json"}:
                raise ValueError("Unexpected documents")
            if not {"manifest.json", "definition.json"} <= set(index.names):
                raise ValueError("Missing documents")
            result.layers[layer] = "pass"
            layer = "json"
            manifest_raw = index.read("manifest.json", document_limit)
            manifest = strict_json(manifest_raw)
            raw = index.read("definition.json", document_limit - len(manifest_raw))
            definition = strict_json(raw)
        result.layers[layer] = "pass"
        layer = "schema"
        if version == 1:
            parsed_manifest = Manifest.model_validate(manifest)
            parsed = Definition.model_validate(definition)
            if digest(raw) != parsed_manifest.definition_sha256:
                raise ValueError("Definition hash mismatch")
            result.manifest, result.definition = parsed_manifest, parsed
        else:
            with open_pack_archive(path) as (_, pack_manifest, pack, *_):
                result.manifest, result.definition = pack_manifest, pack
        result.layers[layer] = "pass"
        layer = "capabilities"
        extra = set()
        if version == 1:
            parsed_manifest, parsed = read_package(path.read_bytes())
            extra = set(parsed_manifest.required_capabilities) - set(required_capabilities(parsed))
        result.layers[layer] = "warning" if extra else "pass"
        layer = "contrast"
        if isinstance(result.definition, Definition) and palette_verdict_for(
            result.definition.look, result.definition.appearance.tokens
        ):
            raise ValueError("Theme colours must meet minimum contrast, including picture scrims")
        result.layers[layer] = "pass"
        layer = "media"
        if version == 2:
            with tempfile.TemporaryDirectory(prefix="denframe-validate-") as temporary:
                validate_archive(path, Path(temporary) / "unpacked")
        result.layers[layer] = "pass" if version == 2 else "not applicable"
    except (ValueError, UnicodeError, zipfile.BadZipFile, OSError, RuntimeError, zlib.error) as exc:
        result.layers[layer] = "fail"
        result.error = str(exc)
    return result
