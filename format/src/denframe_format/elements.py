"""Bounded, data-only portable definitions. No household data crosses this boundary."""

from __future__ import annotations

import io
import zipfile
import zlib
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_validator,
    model_serializer,
    model_validator,
)

from .archive_validation import ArchiveLimits, validated_archive
from .block_instances import Symbol
from .block_overrides import (
    BLOCK_OVERRIDES_CAPABILITY,
    LOCAL_OVERRIDE_FIELDS,
    OVERRIDES_KEY,
    strict_overrides,
)
from .capabilities import (
    BACKGROUND_CANVAS_CAPABILITY,
    BLOCK_STYLE_CAPABILITY,
    LAYOUT_ARRANGEMENT_CAPABILITY,
    LAYOUT_CAPABILITY,
    LAYOUT_SETUP_CAPABILITY,
    OVERLAY_LAYOUT_CAPABILITY,
    PICTURE_FILL_CAPABILITY,
    background_requires_capability,
    overlay_requires_capability,
    picture_capabilities,
)
from .composition import (
    BACKGROUND_FIELDS,
    CANVAS_FIELDS,
    MAX_BACKGROUND_CADENCE_SECONDS,
    MIN_BACKGROUND_CADENCE_SECONDS,
    OVERLAY_FIELDS,
    TOKEN_NAMES,
    TOKEN_PALETTE,
    Appearance,
    BlockStyle,
    DefinitionRef,
    Importance,
    PackageId,
    Placement,
    Region,
    _omit_fields_at_default,
    _whole_number,
    requires_block_style,
)
from .content_ladder import (
    CONTENT_LADDER_CAPABILITY,
    CONTENT_LADDER_V2_CAPABILITY,
    ContentLadderDeclaration,
    ladder_uses_v2_names,
    wire_ladder,
)
from .encoding import canonical as canonical
from .encoding import digest as digest
from .encoding import strict_json as strict_json
from .layout_arrangement import LayoutArrangement, LayoutPurpose
from .localized_text import LOCALIZED_TEXT_CAPABILITY, Localized
from .pack_contracts import CardBlockSettings
from .themes import validate_palette
from .vocabulary import (
    BackgroundKind,
    Face,
    Font,
    Layout,
    Margin,
    MatStyle,
    OverlayCorner,
    OverlayScrim,
    Radius,
    Spacing,
)

MAX_ARCHIVE = 256 * 1024
MAX_EXPANDED = 128 * 1024
SafeText = Annotated[str, StringConstraints(min_length=1, max_length=100)]
SlotId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
KINDS = {
    "clock",
    "weather",
    "calendar",
    "news",
    "market",
    "tasks",
    "notes",
    "home",
    "meal",
    "transport",
    "package",
    "guest",
    "image",
    "media",
    "custom",
    "card",
}
# Presets carry exact references; multimedia bytes stay in their original artifacts.
PORTABLE_KINDS = KINDS
SETTINGS = {
    "clock": {
        "hour_format": {"12", "24"},
        "show_seconds": {True, False},
        "meridiem": {"auto", "show", "hide"},
    },
    "calendar": {"view": {"day", "week"}},
    # A picture's own framing (fill steps 4 and 11) is design: where it reaches and how it fits.
    "image": {
        "edges": {"bleed", "inside"},
        "fit": {"fit", "fill", "smart"},
        "mat_style": {"modern", "museum", "full_bleed", "shadow_box"},
    },
    "media": {"edges": {"bleed", "inside"}, "fit": {"fit", "fill", "smart"}},
}
#: The one structured portable setting: a custom preset's declared content ladder
#: (`app.display.content_ladder`), validated by its own model rather than the value allowlist above.
RESPONSIVE_SETTING = "responsive"


def declared_ladder(kind: str, settings: dict) -> ContentLadderDeclaration | None:
    """The content ladder a portable custom block declares, validated; `None` without one."""
    if kind != "custom" or RESPONSIVE_SETTING not in settings:
        return None
    return ContentLadderDeclaration.model_validate(settings[RESPONSIVE_SETTING])


def portable_ladder(value: object) -> object:
    """A declaration in its portable, canonical shape: validated and normalised, then spelled
    the v1 way unless any row uses a v2 role name, in which case every role is written v2
    and the package requires `content-ladder-v2` -- one package, one vocabulary. A v1
    package's bytes never change spelling under it, and a v1 consumer reads what it always
    read."""
    normalised = ContentLadderDeclaration.model_validate(value).model_dump(
        mode="json", exclude_none=True
    )
    return normalised if ladder_uses_v2_names(value) else wire_ladder(normalised)


def ladder_capability(value: object) -> str:
    """The token a declaration requires: v2 when spelled with a v2 role name, else v1."""
    if ladder_uses_v2_names(value):
        return CONTENT_LADDER_V2_CAPABILITY
    return CONTENT_LADDER_CAPABILITY


# Public preset identifiers are renderer/source vocabulary, never household identifiers.
PUBLIC_SOURCE_PRESETS = {
    "image": frozenset({"bundled-open-art", "the-met-open-access-highlights"}),
    "news": frozenset({"nasa-jpl-space"}),
}


class SuggestedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: SafeText
    preset_id: SlotId | None = None

    @model_validator(mode="after")
    def public_source(self) -> Self:
        if self.kind not in PORTABLE_KINDS - {"clock", "card"}:
            raise ValueError("Unknown suggested source kind")
        if self.preset_id is not None and self.preset_id not in PUBLIC_SOURCE_PRESETS.get(
            self.kind, frozenset()
        ):
            raise ValueError("Suggested sources must name a public preset")
        return self


class SetupPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_slot: SlotId
    field: Literal["city", "units", "watchlist"]
    required: bool = False


class SourceSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: SlotId
    kind: SafeText
    required: bool = True
    suggested_source: SuggestedSource | None = None

    @model_serializer(mode="wrap")
    def omit_suggestion(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.suggested_source is None:
            data.pop("suggested_source")
        return data

    @model_validator(mode="after")
    def known_kind(self) -> Self:
        if self.suggested_source is not None and self.suggested_source.kind != self.kind:
            raise ValueError("Suggested source kind must match its slot")
        if self.kind not in PORTABLE_KINDS - {"clock", "card"}:
            raise ValueError("Unknown source capability")
        return self


class PortablePlacement(BaseModel):
    """Region and importance hints, also used when no explicit arrangement is carried.

    Grid coordinates live in the layout's optional arrangement. Keeping these hints unchanged
    preserves the bytes of releases published before layout-arrangement-v1.
    """

    model_config = ConfigDict(extra="forbid")
    region: Region = "auto"
    importance: Importance = "normal"

    @classmethod
    def from_placement(cls, placement: Placement | PortablePlacement) -> PortablePlacement:
        """Narrow a local placement, or an already-narrow one, to the portable vocabulary.

        Accepts either record because the read path re-validates a stored portable block while
        the write path narrows a dashboard's local placement.
        """
        return cls(region=placement.region, importance=placement.importance)

    def to_local(self) -> Placement:
        """Widen the narrow hint into the local record, filling span defaults.

        The inverse of `from_placement`. Pydantic will not coerce one model instance into the
        other, so the conversion is explicit in both directions.
        """
        return Placement(region=self.region, importance=self.importance)


class PortableAppearance(BaseModel):
    """The paint a shared definition may carry: everything except a local media key.

    `Appearance.background_source_id` names a *household* gallery collection or personal album.
    A downloadable definition must not carry one — the module docstring of
    `app/composition.py` states that portable packages never contain local bindings, and the
    same rule already narrows `PortablePlacement`. Importing a package applies its appearance
    to the importer's dashboard, so a foreign key here would point the importer at a source its
    household does not own.

    This is its own model rather than a narrowed subclass so the field does not appear in the
    committed public schema at all: an author reading `portable-definition.schema.json` must not
    be told the field is available. `Definition` embeds this record, and published package bytes
    are immutable, so the field list here is a release-compatibility surface — do not widen it
    without deciding to re-version the published catalog.
    """

    model_config = ConfigDict(extra="forbid")
    layout: Layout = "flow"
    background: BackgroundKind = "theme"
    font: Font = "theme"
    spacing: Spacing = "standard"
    tokens: TOKEN_PALETTE = Field(default_factory=dict, max_length=10)
    background_mat: MatStyle = "museum"
    background_motion: bool = Field(default=False, strict=True)
    background_cadence_seconds: int = Field(
        default=45,
        ge=MIN_BACKGROUND_CADENCE_SECONDS,
        le=MAX_BACKGROUND_CADENCE_SECONDS,
        strict=True,
    )
    # The canvas is design, like `region`/`importance`: a theme ships its margin, face and
    # corners. Omitted at their defaults (below) so every published package keeps its bytes.
    margin: Margin = "standard"
    face: Face = "look"
    radius: Radius = "look"
    # The ambient overlay's two settings are design too, on exactly the canvas's terms: a
    # recipe that composes over its own artwork ships the corner it was arranged for.
    # Omitted at their defaults, so every package published before they existed keeps its bytes.
    overlay_corner: OverlayCorner = "bottom-left"
    overlay_scrim: OverlayScrim = "standard"

    @field_validator("background_cadence_seconds", mode="before")
    @classmethod
    def whole_cadence(cls, value: Any) -> Any:
        return _whole_number(value)

    @model_validator(mode="after")
    def token_names(self) -> PortableAppearance:
        if not set(self.tokens) <= TOKEN_NAMES:
            raise ValueError("Unsupported theme token")
        return self

    @model_serializer(mode="wrap")
    def omit_unauthored_background_settings(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return _omit_fields_at_default(
            PortableAppearance, handler(self), BACKGROUND_FIELDS + CANVAS_FIELDS + OVERLAY_FIELDS
        )

    @classmethod
    def from_appearance(cls, appearance: Appearance) -> PortableAppearance:
        """Narrow a dashboard's local paint to what a definition may carry."""
        # `grid_collision` is a Studio authoring preference, not paint; a definition ships an
        # arrangement's look, never how its author's editor resolves a drag.
        return cls.model_validate(
            appearance.model_dump(exclude={"background_source_id", "grid_collision"})
        )


class PortableBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: SlotId
    kind: SafeText
    enabled: bool = True
    settings: dict = Field(default_factory=dict, max_length=4)
    source_slot: SlotId | None = None
    symbols: list[Symbol] | None = Field(default=None, max_length=6)
    placement: PortablePlacement = Field(default_factory=PortablePlacement)
    # The block's own style is design, like its placement hint; omitted at its defaults so
    # every package published before styles existed keeps its bytes.
    style: BlockStyle = Field(default_factory=BlockStyle)

    @model_serializer(mode="wrap")
    def omit_default_style(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.style.is_default():
            data.pop("style", None)
        return data

    @model_validator(mode="after")
    def safe_configuration(self) -> Self:
        if self.symbols is not None and (
            self.kind != "market" or len(set(self.symbols)) != len(self.symbols)
        ):
            raise ValueError("Symbol queries require a market instance and unique symbols")
        if self.kind not in PORTABLE_KINDS:
            raise ValueError("Unknown compiled block kind")
        if self.kind == "card":
            self.settings = CardBlockSettings.model_validate(self.settings).model_dump(mode="json")
            if self.source_slot is not None:
                raise ValueError("Cards use content references, not source slots")
            return self
        for key, value in self.settings.items():
            if key == OVERRIDES_KEY:
                # A dashboard's own choices, as design: validated whole, and never this
                # household's people (`LOCAL_OVERRIDE_FIELDS`).
                if isinstance(value, dict) and LOCAL_OVERRIDE_FIELDS & set(value):
                    raise ValueError("A package cannot carry a dashboard's people")
                self.settings[key] = strict_overrides(self.kind, value, where="in this package")
                continue
            if key == RESPONSIVE_SETTING and self.kind == "custom":
                # Normalised so the package carries the declaration's canonical shape, in
                # the role spelling it was authored with.
                self.settings[key] = portable_ladder(value)
                continue
            allowed = SETTINGS.get(self.kind, {}).get(key)
            if allowed is None or not isinstance(value, (str, bool)) or value not in allowed:
                raise ValueError("Unsupported portable setting")
        if self.settings.get(OVERRIDES_KEY) == {}:
            # An empty object chooses nothing: not a setting, and no reason for a token.
            del self.settings[OVERRIDES_KEY]
        if self.kind != "clock" and self.source_slot is None:
            raise ValueError("A portable content block requires a source slot")
        return self


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    kind: Literal["theme", "block", "content"]
    name: SafeText
    look: Literal["painting", "modern", "glass", "ink", "linen", "botanical"] = "modern"
    appearance: PortableAppearance = Field(default_factory=PortableAppearance)
    blocks: list[PortableBlock] = Field(default_factory=list, max_length=12)
    source_slots: list[SourceSlot] = Field(default_factory=list, max_length=12)
    purpose: LayoutPurpose | None = None
    arrangement: LayoutArrangement | None = None
    setup: list[SetupPrompt] = Field(default_factory=list, max_length=24)
    # D33: the name (and the catalog's mood and description) in other languages. Omitted when
    # absent, so every definition published before it keeps its bytes.
    localized: Localized | None = None

    @model_serializer(mode="wrap")
    def omit_optional_layout(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if not self.setup:
            data.pop("setup")
        for key in ("purpose", "arrangement", "localized"):
            if data[key] is None:
                data.pop(key)
        return data

    @field_validator("appearance", mode="before")
    @classmethod
    def narrow_appearance(cls, value: Any) -> Any:
        """Accept a local `Appearance` by narrowing it, so a caller cannot smuggle a local key.

        Building a definition from a dashboard's own appearance is the normal export shape, so
        this keeps that call working while guaranteeing the portable record only ever receives
        the fields it declares.
        """
        return PortableAppearance.from_appearance(value) if isinstance(value, Appearance) else value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        validate_palette(self.look, self.appearance.tokens)
        if self.kind != "content" and (self.purpose is not None or self.arrangement is not None):
            raise ValueError("Only layouts declare purpose or arrangement")
        if self.arrangement is not None:
            if self.appearance.layout != "grid":
                raise ValueError("An arrangement requires grid layout")
            ids = {block.id for block in self.blocks}
            if set(self.arrangement.landscape) != ids or not set(self.arrangement.portrait) <= ids:
                raise ValueError("Arrangement cells must name the layout's blocks")
        if len({b.id for b in self.blocks}) != len(self.blocks) or len(
            {s.id for s in self.source_slots}
        ) != len(self.source_slots):
            raise ValueError("Duplicate instance or slot ID")
        slots = {s.id: s.kind for s in self.source_slots}
        if self.setup and self.kind != "content":
            raise ValueError("Only layouts declare setup prompts")
        if len({(prompt.source_slot, prompt.field) for prompt in self.setup}) != len(self.setup):
            raise ValueError("Duplicate setup prompt")
        for prompt in self.setup:
            kind = "market" if prompt.field == "watchlist" else "weather"
            if slots.get(prompt.source_slot) != kind:
                raise ValueError("Setup prompts must match a declared source slot")
        if any(b.source_slot and slots.get(b.source_slot) != b.kind for b in self.blocks):
            raise ValueError("Source slots must match block capabilities")
        if set(slots) != {b.source_slot for b in self.blocks if b.source_slot}:
            raise ValueError("Unreferenced source slot")
        if self.kind == "theme" and (self.blocks or self.source_slots):
            raise ValueError("Themes contain appearance only")
        if self.kind == "block" and len(self.blocks) != 1:
            raise ValueError("Block presets contain one instance")
        if self.kind == "content" and not self.blocks:
            raise ValueError("Content collections cannot be empty")
        return self


#: The licences a design package may declare, which the signing tools also spell.
PackageLicense = Literal["MIT", "CC0-1.0", "CC-BY-4.0"]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["denframepack"] = "denframepack"
    schema_version: Literal[1] = 1
    id: PackageId
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$", max_length=30)]
    license: PackageLicense
    publisher: SafeText = "Local author"
    attribution: str = Field(default="", max_length=500)
    entrypoint: Literal["definition.json"] = "definition.json"
    definition_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    dependencies: list[DefinitionRef] = Field(default_factory=list, max_length=32)
    required_capabilities: list[SafeText] = Field(
        default_factory=lambda: ["composition-v2"], max_length=16
    )

    @model_validator(mode="after")
    def unique_locks(self) -> Self:
        if self.license == "CC-BY-4.0" and not self.attribution.strip():
            raise ValueError("Attribution is required for CC-BY packages")
        if len({ref.id for ref in self.dependencies}) != len(self.dependencies):
            raise ValueError("Duplicate dependency IDs")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("Duplicate capabilities")
        return self


def read_package(data: bytes) -> tuple[Manifest, Definition]:
    limits = ArchiveLimits(
        MAX_ARCHIVE,
        MAX_EXPANDED,
        2,
        archive_error="Package exceeds compressed size limit",
        expanded_error="Package exceeds expanded size limit",
    )
    try:
        with validated_archive(data, limits) as index:
            if len(index.entries) != 2 or set(index.names) != {"manifest.json", "definition.json"}:
                raise ValueError("Package must contain only manifest.json and definition.json")
            manifest_raw = index.read("manifest.json", MAX_EXPANDED)
            manifest = Manifest.model_validate(strict_json(manifest_raw))
            raw = index.read(manifest.entrypoint, MAX_EXPANDED - len(manifest_raw))
            if digest(raw) != manifest.definition_sha256:
                raise ValueError("Definition hash mismatch")
            definition = Definition.model_validate(strict_json(raw))
            if (
                definition.purpose is not None or definition.arrangement is not None
            ) and LAYOUT_ARRANGEMENT_CAPABILITY not in manifest.required_capabilities:
                raise ValueError(
                    "Layout purpose or arrangement requires "
                    f"{LAYOUT_ARRANGEMENT_CAPABILITY} capability"
                )
            if (
                definition.localized is not None
                and LOCALIZED_TEXT_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(f"Localized words require {LOCALIZED_TEXT_CAPABILITY} capability")
            if (
                _requires_setup(definition)
                and LAYOUT_SETUP_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(f"Source suggestions or setup require {LAYOUT_SETUP_CAPABILITY}")
            required = LAYOUT_CAPABILITY.get(definition.appearance.layout)
            if required is not None and required not in manifest.required_capabilities:
                raise ValueError(
                    f"{definition.appearance.layout.title()} layout requires {required} capability"
                )
            if (
                background_requires_capability(
                    definition.appearance.background,
                    background_source_id=None,
                    background_mat=definition.appearance.background_mat,
                    background_motion=definition.appearance.background_motion,
                    background_cadence_seconds=definition.appearance.background_cadence_seconds,
                )
                and BACKGROUND_CANVAS_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(
                    f"An authored {definition.appearance.background} background requires "
                    f"{BACKGROUND_CANVAS_CAPABILITY} capability"
                )
            if (
                overlay_requires_capability(
                    definition.appearance.layout,
                    overlay_corner=definition.appearance.overlay_corner,
                    overlay_scrim=definition.appearance.overlay_scrim,
                )
                and OVERLAY_LAYOUT_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(
                    f"An authored overlay requires {OVERLAY_LAYOUT_CAPABILITY} capability"
                )
            if (
                _definition_requires_block_style(definition)
                and BLOCK_STYLE_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(
                    "An authored canvas or block style requires "
                    f"{BLOCK_STYLE_CAPABILITY} capability"
                )
            if (
                _definition_requires_picture_fill(definition)
                and PICTURE_FILL_CAPABILITY not in manifest.required_capabilities
            ):
                raise ValueError(
                    "A picture that fills, or an explicit soft radius, requires "
                    f"{PICTURE_FILL_CAPABILITY} capability"
                )
            for block in definition.blocks:
                if declared_ladder(block.kind, block.settings) is not None:
                    needed = ladder_capability(block.settings[RESPONSIVE_SETTING])
                    if needed not in manifest.required_capabilities:
                        raise ValueError(f"A declared content ladder requires {needed} capability")
                if (
                    _block_carries_overrides(block)
                    and BLOCK_OVERRIDES_CAPABILITY not in manifest.required_capabilities
                ):
                    raise ValueError(
                        f"A block's own settings require {BLOCK_OVERRIDES_CAPABILITY} capability"
                    )
                if block.kind == "card":
                    ref = CardBlockSettings.model_validate(block.settings).content_ref
                    expected = DefinitionRef(
                        id=ref.id, version=ref.version, digest=ref.definition_sha256
                    )
                    if expected not in manifest.dependencies or not {
                        "card-v1",
                        "pack-window-v1",
                    } <= set(manifest.required_capabilities):
                        raise ValueError("Card presets require exact dependencies and capabilities")
            return manifest, definition
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, RecursionError, zlib.error) as exc:
        raise ValueError("Invalid package archive") from exc


def _requires_setup(definition: Definition) -> bool:
    return bool(
        definition.setup
        or any(slot.suggested_source for slot in definition.source_slots)
        or any("mat_style" in block.settings for block in definition.blocks)
    )


def required_capabilities(definition: Definition) -> list[str]:
    """Capabilities required by the portable definition itself."""
    return [
        "composition-v2",
        *([LAYOUT_SETUP_CAPABILITY] if _requires_setup(definition) else []),
        *(
            [LAYOUT_ARRANGEMENT_CAPABILITY]
            if definition.purpose is not None or definition.arrangement is not None
            else []
        ),
        *(
            [LAYOUT_CAPABILITY[definition.appearance.layout]]
            if definition.appearance.layout in LAYOUT_CAPABILITY
            else []
        ),
        *(
            [BACKGROUND_CANVAS_CAPABILITY]
            if background_requires_capability(
                definition.appearance.background,
                background_source_id=None,
                background_mat=definition.appearance.background_mat,
                background_motion=definition.appearance.background_motion,
                background_cadence_seconds=definition.appearance.background_cadence_seconds,
            )
            else []
        ),
        # The overlay's settings need the token even under another family. The layout
        # entry above already carries it for `layout == "overlay"`, and this list is not
        # deduplicated (`Manifest` requires unique tokens), so that case is excluded here.
        *(
            [OVERLAY_LAYOUT_CAPABILITY]
            if definition.appearance.layout != "overlay"
            and overlay_requires_capability(
                definition.appearance.layout,
                overlay_corner=definition.appearance.overlay_corner,
                overlay_scrim=definition.appearance.overlay_scrim,
            )
            else []
        ),
        *([BLOCK_STYLE_CAPABILITY] if _definition_requires_block_style(definition) else []),
        *([PICTURE_FILL_CAPABILITY] if _definition_requires_picture_fill(definition) else []),
        *(
            ["card-v1", "pack-window-v1"]
            if any(block.kind == "card" for block in definition.blocks)
            else []
        ),
        # The token each declaration needs -- v2 where a role is spelled the v2 way -- once.
        *sorted(
            {
                ladder_capability(block.settings[RESPONSIVE_SETTING])
                for block in definition.blocks
                if declared_ladder(block.kind, block.settings) is not None
            }
        ),
        *(
            [BLOCK_OVERRIDES_CAPABILITY]
            if any(_block_carries_overrides(block) for block in definition.blocks)
            else []
        ),
        *([LOCALIZED_TEXT_CAPABILITY] if definition.localized is not None else []),
    ]


def build_package(
    package_id: str,
    version: str,
    definition: Definition,
    license_id: PackageLicense = "MIT",
) -> bytes:
    raw = canonical(definition.model_dump(mode="json"))
    references = {}
    for block in definition.blocks:
        if block.kind == "card":
            ref = CardBlockSettings.model_validate(block.settings).content_ref
            dependency = DefinitionRef(id=ref.id, version=ref.version, digest=ref.definition_sha256)
            if ref.id in references and references[ref.id] != dependency:
                raise ValueError("Conflicting pack versions in reusable design")
            references[ref.id] = dependency
    manifest = Manifest(
        id=package_id,
        version=version,
        license=license_id,
        definition_sha256=digest(raw),
        dependencies=list(references.values()),
        required_capabilities=required_capabilities(definition),
    )
    return build_element(manifest, definition)


def build_element(manifest: Manifest, definition: Definition) -> bytes:
    """Encode an explicit manifest without discarding attribution, publisher or exact locks."""
    raw = canonical(definition.model_dump(mode="json"))
    if manifest.definition_sha256 != digest(raw):
        raise ValueError("Definition hash mismatch")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in [
            ("manifest.json", canonical(manifest.model_dump(mode="json"))),
            ("definition.json", raw),
        ]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def _block_carries_overrides(block: PortableBlock) -> bool:
    """Whether a portable block makes a choice of its own (and so needs the host's token)."""
    return bool(block.settings.get(OVERRIDES_KEY))


def _definition_requires_block_style(definition: Definition) -> bool:
    return requires_block_style(definition.appearance, (block.style for block in definition.blocks))


def _definition_requires_picture_fill(definition: Definition) -> bool:
    # Every portable block counts: a package carries no enabled state of its own.
    return bool(picture_capabilities(definition.appearance.radius, definition.blocks))
