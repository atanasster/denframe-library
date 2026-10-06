"""Display vocabularies shared by the local composition record and the domain models.

These live in their own module because `models/scenes.py` imports `composition.py`: a value used by
both cannot be defined in either without a cycle. Keeping one definition per vocabulary is what
stops a new member from being added in one place and silently missed in another.
"""

from __future__ import annotations

from typing import Literal, get_args

# Frame treatments for photographic content. `appearance.background_mat` and the media block's
# `mat_style` are the same vocabulary, deliberately.
MatStyle = Literal["full_bleed", "modern", "museum", "shadow_box"]
MAT_STYLES: tuple[MatStyle, ...] = get_args(MatStyle)

# Canvas treatments. `weather` is a condition-keyed gradient over the aurora/canopy/dunes
# system; `artwork` and `album` name a photographic source held in `background_source_id`.
BackgroundKind = Literal[
    "theme", "solid", "aurora", "canopy", "dunes", "artwork", "album", "weather"
]
BACKGROUND_KINDS: tuple[BackgroundKind, ...] = get_args(BackgroundKind)

Font = Literal["theme", "sans", "serif"]
FONTS: tuple[Font, ...] = get_args(Font)

# The gap between blocks. `tight` is accepted from inspector step 1 and honoured by the
# resolvers' `gapFor` from step 4 (until then it draws as `standard`).
Spacing = Literal["tight", "standard", "relaxed"]
SPACINGS: tuple[Spacing, ...] = get_args(Spacing)

# The dashboard's own canvas inset, added to the screen's safe area; the `u` step per value
# is the table in `docs/reference/DASHBOARD_EDITOR.md` §2.4 and the geometry that reads it.
# Overscan stays a screen fact and is never reduced.
Margin = Literal["none", "tight", "standard", "wide"]
MARGINS: tuple[Margin, ...] = get_args(Margin)

# The block surface every block inherits: `look` is whatever the look draws (Painting's
# transparent-over-shade, Glass's blurred panel); the others override it.
Face = Literal["look", "card", "transparent", "outlined"]
FACES: tuple[Face, ...] = get_args(Face)

# Corner radius of block faces and picture tiles. `look` is the look's own radius (the
# default, never on the wire); `soft` is an explicit 2u since fill step 4, when it stopped
# meaning "whatever the look does" -- no stored dashboard held `soft`, which was stripped
# as the default, so nothing changes meaning.
Radius = Literal["look", "square", "soft", "round"]
RADII: tuple[Radius, ...] = get_args(Radius)

# Where a picture tile paints (fill plan D3): `bleed` out to the glass on every side its cell
# shares with the canvas edge, `inside` its cell like any block. Absent means `inside`.
PictureEdges = Literal["bleed", "inside"]
PICTURE_EDGES: tuple[PictureEdges, ...] = get_args(PictureEdges)

# One block's own style (`composition.BlockStyle`).
# `inherit`/`auto`/`start` are "whatever the dashboard does", so an all-default style is no
# style at all and is dropped from the wire. What each family honours is §2.5.
BlockPadding = Literal["inherit", "none", "tight", "standard", "roomy"]
BLOCK_PADDINGS: tuple[BlockPadding, ...] = get_args(BlockPadding)
BlockFace = Literal["inherit", "card", "transparent", "outlined"]
BLOCK_FACES: tuple[BlockFace, ...] = get_args(BlockFace)
TextSize = Literal["smaller", "inherit", "larger"]
TEXT_SIZES: tuple[TextSize, ...] = get_args(TextSize)
Detail = Literal["auto", "compact", "line", "glance"]
DETAILS: tuple[Detail, ...] = get_args(Detail)
Heading = Literal["inherit", "hidden"]
HEADINGS: tuple[Heading, ...] = get_args(Heading)
Align = Literal["start", "center", "end"]
ALIGNS: tuple[Align, ...] = get_args(Align)
Accent = Literal["inherit", "accent", "muted"]
ACCENTS: tuple[Accent, ...] = get_args(Accent)

#: The authored composition families. `overlay` (legibility step 14, plan §3.5) is the
#: ambient one: a single media owner full-bleed with the other blocks' glance forms stacked
#: in one corner over a scrim. The name is the *layout family* -- unrelated to the receiver's
#: alert overlay (`display.css`) or Studio's editing overlay (`DisplayFrame.tsx`), neither of
#: which is an authored layout; those are chrome drawn over whatever family is resolved.
#: `wall` (family calendar step 12, plan §5) is the calendar wall: one calendar block owns the
#: canvas and the other blocks read in a measured dock along one edge, nothing drawn over it.
Layout = Literal["auto", "flow", "columns", "stage", "grid", "overlay", "wall"]
LAYOUTS: tuple[Layout, ...] = get_args(Layout)

#: Which corner of the safe area the overlay stacks its text into. Appearance, not geometry:
#: the rectangle the corner gets is measured (`overlayLayoutFor`), this only says which one.
OverlayCorner = Literal["bottom-left", "bottom-right", "top-left", "top-right"]
OVERLAY_CORNERS: tuple[OverlayCorner, ...] = get_args(OverlayCorner)
#: How strongly the scrim under that corner darkens the media. The contrast measurement that
#: makes a strength sufficient arrives with legibility step 15; step 14 carries the setting so
#: the vocabulary, the wire and the capability land once.
OverlayScrim = Literal["soft", "standard", "strong"]
OVERLAY_SCRIMS: tuple[OverlayScrim, ...] = get_args(OverlayScrim)

#: Which edge of the canvas holds the calendar wall's dock: along the `top`, or down the leading
#: `side` (a landscape canvas only; a portrait or square one docks at the top whatever this
#: says). Appearance, not geometry: the dock's size is measured (`wallLayoutFor`).
WallDock = Literal["top", "side"]
WALL_DOCKS: tuple[WallDock, ...] = get_args(WallDock)

#: The calendar block's views (family calendar plan step 2, §5). `auto` lets the cell's
#: measurement choose; `columns` and `lanes` are the person views; `month` is only ever authored.
#: Carried as the calendar's own `view` override; the views themselves arrive in steps 8-11.
CalendarView = Literal[
    "auto", "next", "agenda", "week", "columns", "lanes", "rolling_month", "month"
]
CALENDAR_VIEWS: tuple[CalendarView, ...] = get_args(CalendarView)

Region = Literal["auto", "header", "main", "secondary", "stage", "side"]
Importance = Literal["required", "normal", "optional"]

# Renderer names exported to the shared vocabulary alongside authored layout names.
DisplayLayout = Literal["stack", "stage", "focus", "calibration"]
#: The reading roles of a content ladder's rows (legibility step 5, plan §3.1): `vital` is the
#: principal reading within a block (the time, the temperature), `essential` what must still be
#: readable, `incidental` attribution, credits and status. `content-ladder-v1` wrote `hero` and
#: `secondary` for the first and the last; both names are accepted and normalised at import.
ReadingRole = Literal["vital", "essential", "incidental"]
DisplayArea = Literal["anchor", "primary", "secondary", "stage", "side", "focus", "calibration"]
WeekdayAbbreviation = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
