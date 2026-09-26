"""Local provenance operations shared by composition authors and the host."""

from collections.abc import Mapping
from uuid import uuid4

from .capabilities import LIBRARY_PROVENANCE_CAPABILITY
from .composition import CompositionDocument, DefinitionRef, LibraryApplication, composition_refs


def normalize_provenance(document: CompositionDocument, block_ids: set[str], look: str) -> None:
    """Remove absent instance contributions and detach a look changed by its owner."""
    document.block_origins = {
        key: ref for key, ref in document.block_origins.items() if key in block_ids
    }
    for application in document.library_applications.values():
        application.blocks = {
            authored: [
                local
                for local in copies
                if document.block_origins.get(local) == application.definition
            ]
            for authored, copies in application.blocks.items()
        }
        application.blocks = {
            authored: copies for authored, copies in application.blocks.items() if copies
        }
        if application.look != look:
            application.look = None


def enable_provenance(document: CompositionDocument) -> None:
    """Preserve untraceable pre-existing locks before recording the first exact application."""
    if LIBRARY_PROVENANCE_CAPABILITY not in document.required_capabilities:
        document.legacy_dependencies = composition_refs(document)
        document.required_capabilities.append(LIBRARY_PROVENANCE_CAPABILITY)


def record_application(
    document: CompositionDocument, ref: DefinitionRef, blocks: Mapping[str, str], look: str | None
) -> str:
    """Record one use, retaining unknown legacy locks until their absence can be proven."""
    enable_provenance(document)
    replaced = set(blocks.values())
    for previous in document.library_applications.values():
        previous.blocks = {
            authored: remaining
            for authored, copies in previous.blocks.items()
            if (remaining := [local for local in copies if local not in replaced])
        }
    if look is not None:
        for application in document.library_applications.values():
            application.look = None
    identifier = str(uuid4())
    application = LibraryApplication.model_validate(
        {
            "definition": ref,
            "blocks": {authored: [local] for authored, local in blocks.items()},
            "look": look,
        }
    )
    document.library_applications[identifier] = application
    document.block_origins.update({local: ref for local in blocks.values()})
    return identifier
