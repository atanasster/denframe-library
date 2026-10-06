"""Versioned local composition metadata; portable packages never contain local bindings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from itertools import combinations
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal

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

from .block_instances import Identifier, InstanceBinding
from .capabilities import (
    BACKGROUND_CANVAS_CAPABILITY,
    BLOCK_STYLE_CAPABILITY,
    LAYOUT_CAPABILITY,
    LIBRARY_PROVENANCE_CAPABILITY,
    OVERLAY_LAYOUT_CAPABILITY,
    PICTURE_FILL_CAPABILITY,
    WALL_LAYOUT_CAPABILITY,
    background_requires_capability,
    block_style_requires_capability,
    overlay_requires_capability,
    wall_requires_capability,
)
from .vocabulary import (
    Accent,
    Align,
    BackgroundKind,
    BlockFace,
    BlockPadding,
    Detail,
    Face,
    Font,
    Heading,
    Importance,
    Layout,
    Margin,
    MatStyle,
    OverlayCorner,
    OverlayScrim,
    Radius,
    Region,
    Spacing,
    TextSize,
    WallDock,
)

if TYPE_CHECKING:
    from .elements import PortableAppearance

PackageId = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*$", max_length=100)
]

# One scene holds at most this many blocks, so at most this many placement hints: one per
# instance. Kept as one name so the placement cap cannot drift from the block cap.
MAX_BLOCKS = 12

# The authored grid is the shared vocabulary between the editor, the resolver, and the
# browser geometry contract.
GRID_COLUMNS = 12
GRID_ROWS = 6
MAX_PLACEMENTS = MAX_BLOCKS
DEFAULT_COL_SPAN = GRID_COLUMNS
DEFAULT_ROW_SPAN = 1
# A portrait screen carries its own arrangement on a transposed grid: the same cell count,
# narrow and tall. Square shares the landscape grid.
PORTRAIT_GRID_COLUMNS = GRID_ROWS
PORTRAIT_GRID_ROWS = GRID_COLUMNS
GridShape = Literal["portrait"]

GridCollision = Literal["block", "push"]


# Bounds on the background rotation interval, mirrored in `frontend/src/composition/appearance.ts`.
MIN_BACKGROUND_CADENCE_SECONDS = 15
MAX_BACKGROUND_CADENCE_SECONDS = 86_400

# Background source identifiers are local collection/album keys, never free text or a URL.
BackgroundSourceId = Annotated[str, StringConstraints(min_length=1, max_length=200)]

TOKEN_PALETTE = dict[str, Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]]
TOKEN_NAMES = frozenset(
    {
        "background",
        "surface",
        "captionSurface",
        "text",
        "mutedText",
        "accent",
        "accentText",
        "border",
        "positive",
        "negative",
    }
)


def _whole_number(value: Any) -> Any:
    """Accept an integral float, because JSON has one number type.

    `4.0` and `4` are the same document to a browser (`Number.isInteger(4)` is true) and to
    the generated JSON Schema, which types these fields as `integer` -- draft 2020-12 defines
    `integer` as an integral *number*. Pydantic's strict int check would reject the float, so
    normalize it here. Strings and booleans are left untouched and still fail that check,
    which keeps this agreeing with the browser's `Number.isInteger`.

    Applied as a `field_validator(mode="before")` rather than an `Annotated[..., BeforeValidator]`
    on purpose: the latter makes Pydantic emit the non-standard `ge`/`le` keywords instead of
    `minimum`/`maximum` for an optional field, and the committed JSON Schema is validated by AJV
    in strict mode.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# Span fields are omitted from serialization when they still hold their default, so a document
# that never authored a span produces exactly the bytes it produced before spans existed. That
# keeps non-grid receiver envelopes parseable by a receiver build that predates this vocabulary
# -- the `grid-placement-v1` token cannot gate it, because a flow or auto document advertises
# neither the grid token nor any reason to expect spans.
SPAN_FIELDS = ("col_span", "row_span", "col_start", "row_start")

# Background settings omitted from serialization while they hold their default; see
# `Appearance.omit_default_background_settings`.
BACKGROUND_FIELDS = (
    "background_source_id",
    "background_mat",
    "background_motion",
    "background_cadence_seconds",
)
# Grid authoring settings omitted the same way, for the same byte-identity reason.
GRID_FIELDS = ("grid_collision",)
# The canvas settings: their defaults are exactly what every dashboard rendered before they existed,
# so an unauthored one stays byte-identical.
CANVAS_FIELDS = ("margin", "face", "radius")
# The overlay family's two settings (legibility step 14), omitted at their defaults for the
# same byte-identity reason: a document that never authored an overlay is unchanged on the
# wire, and an older receiver's strict parser never sees a field it would refuse.
OVERLAY_FIELDS = ("overlay_corner", "overlay_scrim")
# The calendar wall's dock edge (family calendar step 12), on the overlay settings' terms.
WALL_FIELDS = ("wall_dock",)


def _omit_fields_at_default(
    model: type[BaseModel], data: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, Any]:
    """Remove `fields` from a dumped model while each still equals its declared default.

    Note for callers: this is unconditional by design, so `include=` and `exclude_unset=True`
    cannot observe an explicitly authored default. That is the price of keeping a document that
    never configured these settings byte-identical to one written before the fields existed --
    which is what keeps already-deployed receivers parsing and the published catalog
    republishable. `DesignInspector` echoes normalized defaults on every edit, so a
    `model_fields_set` guard would emit the keys on the wire and reintroduce the same break.
    """
    for field in fields:
        info = model.model_fields.get(field)
        # A narrowed record legitimately omits a field; there is nothing to strip for it.
        if info is None:
            continue
        if data.get(field) == info.default:
            data.pop(field, None)
    return data


class DefinitionRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: PackageId
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$", max_length=30)]
    digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class LibraryApplication(BaseModel):
    """One application of a release; copied instances retain their authored instance id."""

    model_config = ConfigDict(extra="forbid")
    definition: DefinitionRef
    blocks: dict[Identifier, Annotated[list[Identifier], Field(min_length=1, max_length=12)]] = (
        Field(default_factory=dict, max_length=12)
    )
    look: Literal["painting", "modern", "glass", "ink", "linen", "botanical"] | None = None

    @model_validator(mode="after")
    def unique_instances(self) -> LibraryApplication:
        instances = [identifier for copies in self.blocks.values() for identifier in copies]
        if len(instances) > 12 or len(instances) != len(set(instances)):
            raise ValueError("Application instances must be unique and bounded to 12")
        return self


def composition_refs(document: CompositionDocument) -> list[DefinitionRef]:
    """Exact locks for usage and admission; precise documents retain origin as history only."""
    references = [
        *document.dependencies,
        *document.legacy_dependencies,
        *document.block_origins.values(),
    ]
    references.extend(
        application.definition
        for application in document.library_applications.values()
        if application.blocks or application.look is not None
    )
    if document.origin and LIBRARY_PROVENANCE_CAPABILITY not in document.required_capabilities:
        references.append(document.origin)
    return list(dict.fromkeys(references))


class Placement(BaseModel):
    """One block's placement.

    `region` and `importance` are the legacy v2 vocabulary and keep their meaning for the
    flow/columns/auto families: importance controls survival under pressure, never reading
    order. The span fields are additive and only consulted by the authored grid family;
    every other layout ignores them, which is why adding them cannot change an existing
    document's rendering.

    On the grid, `col_start`/`row_start`/`col_span`/`row_span` are the block's cell rectangle
    -- authoritative coordinates on a `GRID_COLUMNS` x `GRID_ROWS` grid whose cells scale
    with the canvas, never packing hints. A grid document names both starts on every placement it
    carries and no two rectangles overlap; `CompositionDocument.consistent` enforces that, since it
    is a property of the map.
    """

    model_config = ConfigDict(extra="forbid")
    region: Region = "auto"
    importance: Importance = "normal"
    # `strict=True` mirrors the browser parser's `Number.isInteger` check: it refuses `"4"`,
    # which Pydantic would otherwise coerce, so a malformed document cannot be accepted here
    # and rejected in the browser. `whole_number` normalizes an integral float first, because
    # JSON has a single number type and the browser sees `4.0` and `4` identically.
    col_span: int = Field(default=DEFAULT_COL_SPAN, ge=1, le=GRID_COLUMNS, strict=True)
    row_span: int = Field(default=DEFAULT_ROW_SPAN, ge=1, le=GRID_ROWS, strict=True)
    col_start: int | None = Field(default=None, ge=1, le=GRID_COLUMNS, strict=True)
    row_start: int | None = Field(default=None, ge=1, le=GRID_ROWS, strict=True)

    # The grid this placement's bounds are checked against; `PortraitPlacement` transposes it.
    _columns: ClassVar[int] = GRID_COLUMNS
    _rows: ClassVar[int] = GRID_ROWS

    @field_validator(*SPAN_FIELDS, mode="before")
    @classmethod
    def whole_number(cls, value: Any) -> Any:
        return _whole_number(value)

    @model_validator(mode="after")
    def span_fits_the_grid(self) -> Placement:
        if self.col_start is not None and self.col_start + self.col_span - 1 > self._columns:
            raise ValueError("Column span must fit within the grid")
        if self.row_start is not None and self.row_start + self.row_span - 1 > self._rows:
            raise ValueError("Row span must fit within the grid")
        return self

    @model_serializer(mode="wrap")
    def omit_unauthored_spans(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Drop span keys that still hold their default; see `SPAN_FIELDS`."""
        return _omit_fields_at_default(type(self), handler(self), SPAN_FIELDS)

    def has_cell(self) -> bool:
        return self.col_start is not None and self.row_start is not None

    def cell(self) -> Cell | None:
        """The rectangle a positioned placement names; `None` while unpositioned."""
        if self.col_start is None or self.row_start is None:
            return None
        return (self.col_start, self.row_start, self.col_span, self.row_span)

    def overlaps(self, other: Placement) -> bool:
        """Whether two positioned rectangles share a cell; unpositioned ones never do."""
        mine, theirs = self.cell(), other.cell()
        return mine is not None and theirs is not None and _rect_overlaps(mine, theirs)


class PortraitPlacement(Placement):
    """A placement on the portrait grid: `PORTRAIT_GRID_COLUMNS` x `PORTRAIT_GRID_ROWS`.

    The same fields and rules as `Placement` with the bounds transposed. The default span is
    still full width, which on this grid is `PORTRAIT_GRID_COLUMNS` tracks.
    """

    col_span: int = Field(
        default=PORTRAIT_GRID_COLUMNS, ge=1, le=PORTRAIT_GRID_COLUMNS, strict=True
    )
    row_span: int = Field(default=DEFAULT_ROW_SPAN, ge=1, le=PORTRAIT_GRID_ROWS, strict=True)
    col_start: int | None = Field(default=None, ge=1, le=PORTRAIT_GRID_COLUMNS, strict=True)
    row_start: int | None = Field(default=None, ge=1, le=PORTRAIT_GRID_ROWS, strict=True)

    _columns: ClassVar[int] = PORTRAIT_GRID_COLUMNS
    _rows: ClassVar[int] = PORTRAIT_GRID_ROWS


def validate_grid_placement_map(placements: Mapping[str, Placement], shape: str) -> None:
    """The map-level grid rules: every placement positioned, no two overlapping."""
    for block_id, placement in placements.items():
        if not placement.has_cell():
            raise ValueError(
                f"Grid layout needs col_start and row_start on the {shape} placement "
                f"for {block_id!r}"
            )
    for (block_id, placement), (other_id, other) in combinations(placements.items(), 2):
        if placement.overlaps(other):
            raise ValueError(f"Grid placements overlap in {shape}: {block_id!r} and {other_id!r}")


class Appearance(BaseModel):
    """One scene's paint and layout settings.

    `background` names the canvas treatment. `theme`, `solid`, `aurora`, `canopy`, and `dunes`
    are the original non-photographic treatments; `weather` is a condition-keyed gradient over
    that same system, so it needs no asset, decode, or lease. `artwork` and `album` name a
    photographic source, whose identifier lives in `background_source_id` and is authorized as
    a media lease rather than embedded here.

    Exactly one background is configured per scene: this record is scene-level paint, not an
    instance. It therefore takes no slot in the twelve-block limit, adds no
    `CompositionDocument.bindings` entry, and cannot expand a provider subscription.
    """

    model_config = ConfigDict(extra="forbid")
    layout: Layout = "flow"
    background: BackgroundKind = "theme"
    font: Font = "theme"
    spacing: Spacing = "standard"
    tokens: TOKEN_PALETTE = Field(default_factory=dict, max_length=10)
    # `strict=True` on the flag and the interval mirrors the browser parser, which checks
    # `typeof === "boolean"` and `Number.isInteger`. Lax Pydantic would coerce `"yes"` and
    # `"45"`, so those two documents would be accepted by the API and refused in the browser.
    background_source_id: BackgroundSourceId | None = None
    background_mat: MatStyle = "museum"
    background_motion: bool = Field(default=False, strict=True)
    background_cadence_seconds: int = Field(
        default=45,
        ge=MIN_BACKGROUND_CADENCE_SECONDS,
        le=MAX_BACKGROUND_CADENCE_SECONDS,
        strict=True,
    )
    # How Studio's grid editor resolves a drag into an occupied cell: `block` clamps the
    # gesture to the last free cell, `push` moves the neighbour aside. Authoring-time only --
    # the renderer never reads it, since a saved grid document has no collisions to resolve.
    grid_collision: GridCollision = "push"
    # The canvas: the dashboard's own edge margin (on top of the screen's safe area), the
    # block face every block inherits, and the faces' corner radius. `standard`/`look`/`look`
    # are the pre-existing fixed values, so a document that never authored them draws the same
    # (the radius default was spelled `soft` until fill step 4 and meant the look's own).
    margin: Margin = "standard"
    face: Face = "look"
    radius: Radius = "look"
    # The ambient overlay's appearance (legibility step 14, plan §3.5): which corner of the
    # safe area holds the text stack, and how strongly the scrim under it darkens the media.
    # Where the corner actually lands and how large it is are measured geometry
    # (`overlayLayoutFor`), never these values. Inert under any other layout, and kept rather
    # than cleared when the family changes, so switching away and back does not lose the
    # household's choice -- `grid_collision` is carried on the same terms.
    overlay_corner: OverlayCorner = "bottom-left"
    overlay_scrim: OverlayScrim = "standard"
    # The calendar wall's dock edge (family calendar step 12, plan §5): along the top, or down
    # the leading side of a landscape canvas. The dock's size is measured (`wallLayoutFor`);
    # this only names the edge. Inert under any other layout and kept across a family change,
    # on the overlay settings' terms.
    wall_dock: WallDock = "top"

    @field_validator("background_cadence_seconds", mode="before")
    @classmethod
    def whole_cadence(cls, value: Any) -> Any:
        return _whole_number(value)

    @model_validator(mode="after")
    def token_names(self) -> Appearance:
        if not set(self.tokens) <= TOKEN_NAMES:
            raise ValueError("Unsupported theme token")
        # A source id is meaningless without a photographic background, and accepting the
        # pairing would let a mismatched document resolve a source the screen never draws.
        # The converse is allowed: `artwork` with no source yet is a valid draft state.
        if self.background_source_id is not None and self.background not in {"artwork", "album"}:
            raise ValueError("A background source requires an artwork or album background")
        return self

    @model_serializer(mode="wrap")
    def omit_default_background_settings(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        """Drop background settings that still hold their default.

        `library_packages.Definition` embeds this record, so a new field here changes the bytes
        of every published package. Serializing an unauthored setting as absent keeps a document
        that never configured a photographic background byte-identical to what it produced
        before these fields existed -- which is what keeps the published catalog republishable
        (`scripts/build-library.py::validate_release` refuses changed bytes for a live version)
        and keeps older receivers able to parse a non-grid envelope.
        """
        return _omit_fields_at_default(
            Appearance,
            handler(self),
            BACKGROUND_FIELDS + GRID_FIELDS + CANVAS_FIELDS + OVERLAY_FIELDS + WALL_FIELDS,
        )


class BlockStyle(BaseModel):
    """One block's own design, kept beside its placement in `CompositionDocument.styles` rather
    than in the block's `settings`: settings are content and are merged with a provider's match
    settings at resolve time, and a style must never be something a payload can restate.

    Every field's default means "whatever the dashboard does", so a style at its defaults is
    no style: `is_default` says so and the document's serializer drops it, keeping an
    unstyled document byte-identical to one written before styles existed.
    """

    model_config = ConfigDict(extra="forbid")
    padding: BlockPadding = "inherit"
    face: BlockFace = "inherit"
    text_size: TextSize = "inherit"
    detail: Detail = "auto"
    heading: Heading = "inherit"
    align: Align = "start"
    accent: Accent = "inherit"

    def is_default(self) -> bool:
        return self == BlockStyle()

    @model_serializer(mode="wrap")
    def omit_default_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return _omit_fields_at_default(BlockStyle, handler(self), BLOCK_STYLE_FIELDS)


BLOCK_STYLE_FIELDS = tuple(BlockStyle.model_fields)


def requires_block_style(
    appearance: Appearance | PortableAppearance, styles: Iterable[BlockStyle]
) -> bool:
    """`block_style_requires_capability` for a model: an `Appearance`/`PortableAppearance`
    (both carry the three canvas fields) and the block styles it carries."""
    return block_style_requires_capability(
        margin=appearance.margin,
        face=appearance.face,
        radius=appearance.radius,
        styled_blocks=sum(1 for style in styles if not style.is_default()),
    )


def omit_default_styles(data: dict[str, Any]) -> dict[str, Any]:
    """The one omission rule for `styles`, shared by the stored document and the resolved
    scene: an all-default entry is dropped, and the map is absent on the wire while empty."""
    styles = data.get("styles")
    if isinstance(styles, dict):
        styles = {block_id: style for block_id, style in styles.items() if style}
        data["styles"] = styles
    if not styles:
        data.pop("styles", None)
    return data


def omit_empty_shape_placements(data: dict[str, Any]) -> dict[str, Any]:
    """The one omission rule for `shape_placements`, shared by the stored document and the
    resolved scene: absent on the wire while empty."""
    shapes = data.get("shape_placements")
    if isinstance(shapes, dict):
        # A shape whose map emptied (its last block removed) is no override at all: Studio
        # reads any map present as "customised", so it must not linger.
        shapes = {shape: placements for shape, placements in shapes.items() if placements}
        data["shape_placements"] = shapes
    if not shapes:
        data.pop("shape_placements", None)
    return data


#: Whether a composition is still being arranged or is what the screens render.
CompositionState = Literal["draft", "active"]


class CompositionDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )
    appearance: Appearance = Field(default_factory=Appearance)
    placements: dict[str, Placement] = Field(default_factory=dict, max_length=MAX_PLACEMENTS)
    # Per-shape overrides of the landscape `placements` on the authored grid. Absent shapes
    # are derived from landscape at render time; landscape and square never carry an override. Inert
    # outside `layout: "grid"`, so a dashboard that leaves the grid and returns keeps its portrait
    # arrangement.
    shape_placements: dict[
        GridShape, Annotated[dict[str, PortraitPlacement], Field(max_length=MAX_PLACEMENTS)]
    ] = Field(default_factory=dict)
    # Each block's own style, keyed like `placements`; an all-default entry is dropped on
    # write and the map is absent while empty (`omit_default_styles`).
    styles: dict[str, BlockStyle] = Field(default_factory=dict, max_length=MAX_PLACEMENTS)
    schema_version: Literal[2] = 2
    state: CompositionState = "draft"
    layout_policy: Literal["flow"] = "flow"
    origin: DefinitionRef | None = None
    dependencies: list[DefinitionRef] = Field(default_factory=list, max_length=32)
    legacy_dependencies: list[DefinitionRef] = Field(default_factory=list, max_length=32)
    block_origins: dict[Identifier, DefinitionRef] = Field(default_factory=dict, max_length=12)
    library_applications: dict[Identifier, LibraryApplication] = Field(
        default_factory=dict, max_length=32
    )
    bindings: dict[str, InstanceBinding] = Field(default_factory=dict, max_length=12)
    required_capabilities: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = (
        Field(default_factory=list, max_length=16)
    )

    @model_validator(mode="after")
    def consistent(self) -> CompositionDocument:
        if (
            self.block_origins or self.library_applications or self.legacy_dependencies
        ) and LIBRARY_PROVENANCE_CAPABILITY not in self.required_capabilities:
            raise ValueError(
                f"Library provenance requires {LIBRARY_PROVENANCE_CAPABILITY} capability"
            )
        mapped: dict[str, DefinitionRef] = {}
        looks = 0
        for application in self.library_applications.values():
            looks += application.look is not None
            for copies in application.blocks.values():
                for identifier in copies:
                    if identifier in mapped:
                        raise ValueError("An instance belongs to only one library application")
                    mapped[identifier] = application.definition
        if looks > 1:
            raise ValueError("Only one library application owns the current look")
        if mapped != self.block_origins:
            raise ValueError("Block origins must match the application instance maps")
        if len({ref.id for ref in self.legacy_dependencies}) != len(self.legacy_dependencies):
            raise ValueError("Legacy dependency IDs must be unique")
        ids = [item.id for item in self.dependencies]
        if len(ids) != len(set(ids)):
            raise ValueError("Dependency IDs must be unique")
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("Capabilities must be unique")
        # Derived from what is sent, never stored (fill step 4, D7): a document naming it would
        # keep refusing older screens after the picture that needed it was gone.
        if PICTURE_FILL_CAPABILITY in self.required_capabilities:
            self.required_capabilities = [
                capability
                for capability in self.required_capabilities
                if capability != PICTURE_FILL_CAPABILITY
            ]
        token = LAYOUT_CAPABILITY.get(self.appearance.layout)
        if token is not None and token not in self.required_capabilities:
            raise ValueError(f"{self.appearance.layout.title()} layout requires {token} capability")
        if self.appearance.layout == "grid":
            validate_grid_placement_map(self.placements, "landscape")
            for shape, placements in self.shape_placements.items():
                validate_grid_placement_map(placements, shape)
        if (
            background_requires_capability(
                self.appearance.background,
                background_source_id=self.appearance.background_source_id,
                background_mat=self.appearance.background_mat,
                background_motion=self.appearance.background_motion,
                background_cadence_seconds=self.appearance.background_cadence_seconds,
            )
            and BACKGROUND_CANVAS_CAPABILITY not in self.required_capabilities
        ):
            raise ValueError(
                f"An authored {self.appearance.background} background requires "
                f"{BACKGROUND_CANVAS_CAPABILITY} capability"
            )
        if (
            overlay_requires_capability(
                self.appearance.layout,
                overlay_corner=self.appearance.overlay_corner,
                overlay_scrim=self.appearance.overlay_scrim,
            )
            and OVERLAY_LAYOUT_CAPABILITY not in self.required_capabilities
        ):
            raise ValueError(f"An authored overlay requires {OVERLAY_LAYOUT_CAPABILITY} capability")
        if (
            wall_requires_capability(self.appearance.layout, wall_dock=self.appearance.wall_dock)
            and WALL_LAYOUT_CAPABILITY not in self.required_capabilities
        ):
            raise ValueError(f"A calendar wall requires {WALL_LAYOUT_CAPABILITY} capability")
        if (
            requires_block_style(self.appearance, self.styles.values())
            and BLOCK_STYLE_CAPABILITY not in self.required_capabilities
        ):
            raise ValueError(
                f"An authored canvas or block style requires {BLOCK_STYLE_CAPABILITY} capability"
            )
        return self

    @model_serializer(mode="wrap")
    def omit_empty_shape_placements(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Drop `shape_placements` while empty and `styles` at their defaults, so a document
        without either serializes exactly as it did before they existed
        (see `_omit_fields_at_default`)."""
        data = omit_default_styles(omit_empty_shape_placements(handler(self)))
        for field in ("block_origins", "library_applications", "legacy_dependencies"):
            if not data.get(field):
                data.pop(field, None)
        return data


Cell = tuple[int, int, int, int]
"""`(col_start, row_start, col_span, row_span)`, 1-indexed."""


def _rect_overlaps(a: Cell, b: Cell) -> bool:
    """Whether two 1-indexed cell rectangles share a cell; the one overlap rule for the
    model validator and the migration alike."""
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def pin_grid_coordinates(
    composition: dict[str, Any] | None, blocks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Give a stored grid document the coordinates its placements imply, idempotently.

    Before coordinates became authoritative a grid document carried spans and, at
    most, a `col_start` hint; the renderer packed blocks onto shelves in document order and
    the editor showed exactly that pack against authored row floors. This replays that pack
    (spans only, no content measurement -- the editor's own `authoredHeightOnly` picture) so
    every placement gets the cell its block was last seen in. A placement the shelf pack
    cannot fit lands in the first free cell instead, shrunk to one cell if it must, or -- when
    cells already named fill the grid -- is dropped, which a grid document allows.

    "Done" is a property of the placements present, never of the blocks: every placement
    names a cell, no two overlap, and there are no more than `MAX_PLACEMENTS`. Such a document
    comes back unchanged (as does one that is not a grid), so reading a migrated row never
    invents a placement its household did not save. A placement already naming a cell keeps
    it unless it collides with one kept earlier (a pre-coordinate document could carry two
    hints on one shelf; the second is re-flowed like a placement that never had a cell), and a
    placement for a block no longer on the dashboard is dropped. Coordinates are read
    strictly -- a non-integer never becomes one here that validation would then refuse.
    Operates on the raw JSON object so a row can be repaired before validation.
    `contracts/composition/grid-pin-cases.json` pins its answers (once shared with a browser
    twin, retired in grid step 11: the server pins before anything reaches the browser).
    """
    if not isinstance(composition, dict):
        return composition
    appearance = composition.get("appearance")
    if not isinstance(appearance, dict) or appearance.get("layout") != "grid":
        return composition
    raw = composition.get("placements") or {}
    if not isinstance(raw, dict):
        return composition
    known = {block["id"] for block in blocks if isinstance(block, dict) and "id" in block}
    placements: dict[str, dict[str, Any]] = {
        block_id: placement
        for block_id, placement in raw.items()
        if block_id in known and isinstance(placement, dict)
    }
    if placements == raw and _grid_map_is_settled(placements):
        return composition
    order = [
        block["id"] for block in blocks if isinstance(block, dict) and block.get("id") in placements
    ]
    occupied: set[tuple[int, int]] = set()
    cells: dict[str, Cell] = {}
    # Already-positioned placements keep their cell, unless it collides with one kept before.
    for block_id in order:
        placement = placements[block_id]
        if not _has_cell(placement):
            continue
        cell = _cell_of(placement)
        if cell is None or _cells_covered(cell) & occupied:
            continue
        cells[block_id] = cell
        occupied |= _cells_covered(cell)
    # Shelf-flow the rest in document order, as the old packer and editor did: a column hint
    # is honoured only against a shelf already begun, never for the first block or after a
    # wrap, exactly as `authoredGridFor` did.
    shelf_top, shelf_height, cursor, started = 1, 0, 0, False
    for block_id in order:
        if block_id in cells:
            continue
        placement = placements[block_id]
        col_span = max(
            1, min(GRID_COLUMNS, _strict_int(placement.get("col_span"), DEFAULT_COL_SPAN))
        )
        row_span = max(1, min(GRID_ROWS, _strict_int(placement.get("row_span"), DEFAULT_ROW_SPAN)))
        pinned = _strict_int(placement.get("col_start"), 0)
        col = cursor
        if started and pinned and pinned - 1 >= cursor and pinned - 1 + col_span <= GRID_COLUMNS:
            col = pinned - 1
        if col + col_span > GRID_COLUMNS:
            shelf_top += shelf_height
            shelf_height, cursor, col = 0, 0, 0
        candidate: Cell = (col + 1, shelf_top, col_span, row_span)
        if shelf_top + row_span - 1 <= GRID_ROWS and not (_cells_covered(candidate) & occupied):
            cells[block_id] = candidate
            occupied |= _cells_covered(candidate)
            cursor = col + col_span
            shelf_height = max(shelf_height, row_span)
            started = True
            continue
        free = _first_free_cell(occupied, col_span, row_span)
        if free is None:
            continue
        cells[block_id] = free
        occupied |= _cells_covered(free)
    pinned_placements = {
        block_id: {
            **placements[block_id],
            "col_start": cell[0],
            "row_start": cell[1],
            "col_span": cell[2],
            "row_span": cell[3],
        }
        for block_id, cell in cells.items()
    }
    return {**composition, "placements": pinned_placements}


def _grid_map_is_settled(placements: dict[str, dict[str, Any]]) -> bool:
    """Every placement names a valid cell, none overlap, and the map is within the cap."""
    if len(placements) > MAX_PLACEMENTS:
        return False
    cells: list[Cell] = []
    for placement in placements.values():
        cell = _cell_of(placement) if _has_cell(placement) else None
        if cell is None:
            return False
        cells.append(cell)
    return not any(_rect_overlaps(a, b) for a, b in combinations(cells, 2))


def _strict_int(value: Any, default: int) -> int:
    """An integral JSON number, else `default` -- `Placement`'s strict fields refuse `"4"`
    and `True`, so the migration must not coerce them into a coordinate."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default


def _has_cell(placement: dict[str, Any] | None) -> bool:
    return (
        bool(placement)
        and placement.get("col_start") is not None
        and placement.get("row_start") is not None
    )


def _cell_of(placement: dict[str, Any]) -> Cell | None:
    """The rectangle a positioned placement names, or `None` when a coordinate is not a
    whole number or the rectangle leaves the grid."""
    col_start = _strict_int(placement.get("col_start"), 0)
    row_start = _strict_int(placement.get("row_start"), 0)
    col_span = _strict_int(placement.get("col_span"), DEFAULT_COL_SPAN)
    row_span = _strict_int(placement.get("row_span"), DEFAULT_ROW_SPAN)
    if col_start < 1 or row_start < 1 or col_span < 1 or row_span < 1:
        return None
    if col_start + col_span - 1 > GRID_COLUMNS or row_start + row_span - 1 > GRID_ROWS:
        return None
    return (col_start, row_start, col_span, row_span)


def _cells_covered(cell: Cell) -> set[tuple[int, int]]:
    col_start, row_start, col_span, row_span = cell
    return {
        (col, row)
        for col in range(col_start, col_start + col_span)
        for row in range(row_start, row_start + row_span)
    }


def _first_free_cell(occupied: set[tuple[int, int]], col_span: int, row_span: int) -> Cell | None:
    """The first cell (row-major) where a `col_span` x `row_span` rectangle fits, shrinking the
    rectangle -- height first, then width -- down to 1 x 1 until one does; `None` when cells
    already named fill the whole grid."""
    for height in range(row_span, 0, -1):
        for width in range(col_span, 0, -1):
            for row in range(1, GRID_ROWS - height + 2):
                for col in range(1, GRID_COLUMNS - width + 2):
                    candidate = (col, row, width, height)
                    if not (_cells_covered(candidate) & occupied):
                        return candidate
    return None
