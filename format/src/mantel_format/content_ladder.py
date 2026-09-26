"""The portable half of the content ladder (`docs/reference/DASHBOARD_RENDERING.md` §3.4).

A block shows a different *form* at each of its variants -- `full`, `compact`, `line` and
`glance` -- and the renderer measures each form's rows honestly before choosing the richest
that fits a cell. Compiled kinds build their ladders in the browser
(`frontend/src/display/layout/contentLadder.ts`); an installed preset
(a `custom` block with a `list` / `hero` / `bars` / `matrix` presentation) gets its
presentation's default ladder for free, and may
declare its own forms with this model -- which item fields each form shows, and in what order.

The declaration is data, never code: a form names *fields of the preset's items*, and a host
refuses a malformed form at import time (`PortableBlock.settings.responsive`,
`app.library.library_packages`), not on the wall. The items themselves come from the preset's source
at render time, so a declared row an item cannot fill has no copy there: the renderer refuses
that form and falls to the next variant (`frontend/src/display/render/blocks/
customLadders.ts`). A package that declares one requires `CONTENT_LADDER_CAPABILITY` in its
manifest, so an older host reports "needs a newer Mantel" rather than failing silently; a
package without one installs exactly as before.

Roles (legibility step 5): the reading roles are `vital`, `essential` and `incidental`
(`display_vocabulary.ReadingRole`); `content-ladder-v1` spelled the first and the last `hero` and
`secondary`. Both spellings are accepted and normalised in memory; the two vocabularies map one
to one, so a declaration is serialised losslessly in v1 names for every consumer that may be
older -- the wire to a receiver (`wire_ladder`) and an exported package -- and a package is
written with `content-ladder-v2` only when it was authored with the v2 names.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from .vocabulary import ReadingRole

CONTENT_LADDER_CAPABILITY: Final[str] = "content-ladder-v1"
#: The same declaration with the v2 role names (`vital`, `incidental`) written out. Published
#: beside v1: a host that knows either installs a package requiring it, and every consumer that
#: may be older is handed the lossless v1 spelling instead.
CONTENT_LADDER_V2_CAPABILITY: Final[str] = "content-ladder-v2"

#: v1 role spellings and the v2 name each normalises to.
LEGACY_ROLE_NAMES: Final[dict[str, str]] = {"hero": "vital", "secondary": "incidental"}
#: v2 role names and the v1 spelling each is written as for an older consumer: the inverse.
V1_ROLE_NAMES: Final[dict[str, str]] = {v2: v1 for v1, v2 in LEGACY_ROLE_NAMES.items()}
#: Role spellings only v2 knows; a declaration using one was authored against v2.
V2_ONLY_ROLE_NAMES: Final[frozenset[str]] = frozenset(V1_ROLE_NAMES)

ContentVariant = Literal["full", "compact", "line", "glance"]
CONTENT_VARIANTS: Final[tuple[ContentVariant, ...]] = ("full", "compact", "line", "glance")

#: The item fields a custom presentation's items carry (`CustomItem` in `frontend/src/
#: display/render/blocks/CustomBlock.parser.ts`: text, metric, range, status_row, link), and so
#: the only ones a form may show, each read as the item prints it (`customItemField` in
#: `customLadders.ts`):
#:   value  -- a text item's text, a metric's value, a range's reading (`20 / 100 %`, unit
#:             included, so `join: ["unit"]` on a range repeats it), a status row's status label;
#:   label  -- every item's but a text item's and an image's;
#:   unit   -- a metric's or a range's;
#:   status -- a status row's label (the same text as its `value`);
#:   detail -- a status row's detail.
#: `alt` and `url` are an image's, never printed as text. `backend/tests/test_content_ladder.py`
#: pins the mirror.
CUSTOM_ITEM_FIELDS: Final[tuple[str, ...]] = ("value", "label", "unit", "status", "detail")

ItemField = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,23}$")]


class ContentRowDeclaration(BaseModel):
    """One row of a declared form: an item field, optionally joined with another (`value ·
    unit`), from the first `items` entries. `lines` bounds the row; the host measures it."""

    model_config = ConfigDict(extra="forbid")
    field: ItemField
    #: Fields joined after `field` with " · " when they have a value; each is dropped, right
    #: to left, as a copy candidate when the joined row does not fit.
    join: list[ItemField] = Field(default_factory=list, max_length=3)
    lines: int = Field(default=1, ge=1, le=4)
    #: The current vocabulary; the v1 spellings `hero` and `secondary` are accepted as input
    #: (`accept_v1_spelling`) and the published schema lists all five.
    role: ReadingRole = Field(
        default="essential",
        json_schema_extra={"enum": ["vital", "essential", "incidental", "hero", "secondary"]},
    )

    @field_validator("role", mode="before")
    @classmethod
    def accept_v1_spelling(cls, value: object) -> object:
        return LEGACY_ROLE_NAMES.get(value, value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def known_fields(self) -> ContentRowDeclaration:
        for name in (self.field, *self.join):
            if name not in CUSTOM_ITEM_FIELDS:
                raise ValueError(f"Unknown item field {name!r}")
        if self.field in self.join or len(set(self.join)) != len(self.join):
            raise ValueError("A row joins each field at most once, never with itself")
        if self.role == "vital" and self.lines != 1:
            raise ValueError("A vital row is one line")
        return self


class ContentFormDeclaration(BaseModel):
    """A form: its rows, printed top to bottom for the first `items` entry (or, with `items`
    above one, one set of rows per item up to that many)."""

    model_config = ConfigDict(extra="forbid")
    rows: list[ContentRowDeclaration] = Field(min_length=1, max_length=6)
    items: int = Field(default=1, ge=1, le=6)
    show_title: bool = Field(
        default=False,
        description="Print the preset's title as a caption below the rows, where it fits.",
    )

    @model_validator(mode="after")
    def unique_fields(self) -> ContentFormDeclaration:
        fields = [row.field for row in self.rows]
        if len(set(fields)) != len(fields):
            raise ValueError("A form names each item field at most once")
        return self


class ContentLadderDeclaration(BaseModel):
    """A preset's own forms, by variant. A variant not declared keeps the presentation's
    default form; `glance` is the one worth declaring most (what the block shows in a cell
    with room for a single row)."""

    model_config = ConfigDict(extra="forbid")
    glance: ContentFormDeclaration | None = None
    line: ContentFormDeclaration | None = None
    compact: ContentFormDeclaration | None = None
    full: ContentFormDeclaration | None = None

    @model_validator(mode="after")
    def declares_something(self) -> ContentLadderDeclaration:
        if not self.declared():
            raise ValueError("A content ladder must declare at least one form")
        return self

    def declared(self) -> dict[str, ContentFormDeclaration]:
        return {v: form for v in CONTENT_VARIANTS if (form := getattr(self, v)) is not None}


def ladder_uses_v2_names(raw: object) -> bool:
    """Whether a raw declaration (as authored, before normalisation) spells any role with a v2
    name -- what makes a package require `content-ladder-v2` rather than v1."""
    if not isinstance(raw, dict):
        return False
    for form in raw.values():
        if not isinstance(form, dict):
            continue
        rows = form.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("role") in V2_ONLY_ROLE_NAMES:
                return True
    return False


def wire_ladder(declaration: JsonValue) -> JsonValue:
    """A stored declaration (already normalised to v2 names) written with the v1 role spellings,
    losslessly, for a consumer that may be older: the receiver, an exported package. Anything
    that is not a declaration-shaped mapping is returned unchanged."""
    if not isinstance(declaration, dict):
        return declaration
    out: dict[str, JsonValue] = {}
    for variant, form in declaration.items():
        rows = form.get("rows") if isinstance(form, dict) else None
        if isinstance(form, dict) and isinstance(rows, list):
            wired: list[JsonValue] = [
                {**row, "role": V1_ROLE_NAMES.get(str(row.get("role")), row.get("role"))}
                if isinstance(row, dict) and "role" in row
                else row
                for row in rows
            ]
            out[variant] = {**form, "rows": wired}
        else:
            out[variant] = form
    return out
