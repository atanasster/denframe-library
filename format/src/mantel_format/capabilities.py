"""One source of truth for layout- and background-to-capability admission.

A layout mode or a background treatment that changes how a document must be rendered owns
exactly one capability token. Keeping the mapping in one module means the model validator, the
scene advertisement, and package build/read cannot disagree about which token a layout or
background needs -- the drift trap that would otherwise let a package declare a token its
reader never checks.

`frontend/src/composition/composition.ts` mirrors this table because the parser runs in the browser.
`backend/tests/test_responsive_contracts.py` pins the mirror so the two cannot diverge
silently.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final, Protocol

#: The ambient overlay family's own token (legibility step 14). Its own, deliberately: the
#: overlay changes how a document must be composed -- one media owner full-bleed, the rest in
#: a corner -- which is not something a receiver that only knows `block-style-v1` can degrade
#: into, and the plan (step 15) requires it not be hidden under an already-published token.
OVERLAY_LAYOUT_CAPABILITY: Final[str] = "overlay-layout-v1"

LAYOUT_ARRANGEMENT_CAPABILITY: Final[str] = "layout-arrangement-v1"
LAYOUT_SETUP_CAPABILITY: Final[str] = "layout-setup-v1"
LIBRARY_PROVENANCE_CAPABILITY: Final[str] = "library-provenance-v1"

LAYOUT_CAPABILITY: Final[dict[str, str]] = {
    "auto": "responsive-layout-v1",
    "grid": "grid-placement-v1",
    "overlay": OVERLAY_LAYOUT_CAPABILITY,
}

#: The token an authored background needs. Threaded exactly as `LAYOUT_CAPABILITY` is, but a
#: background has no single enum-to-token map: any of several fields can make it "authored"
#: rather than default, so `background_requires_capability` below is the admission rule, not a
#: dict lookup.
BACKGROUND_CANVAS_CAPABILITY: Final[str] = "background-canvas-v1"

#: Backgrounds that always need `BACKGROUND_CANVAS_CAPABILITY`: a photographic background
#: (`artwork`/`album`) or a condition-keyed one (`weather`) renders through `BackgroundCanvas`,
#: a receiver capability, never something a legacy renderer can degrade gracefully into. A
#: flat/gradient background (`theme`/`solid`/`aurora`/`canopy`/`dunes`) is not in this set --
#: it needs the token only if one of the four settings below is authored away from its default.
GATED_BACKGROUND_KINDS: Final[frozenset[str]] = frozenset({"artwork", "album", "weather"})

#: The `Appearance`/`PortableAppearance` field defaults these three settings must equal to stay
#: inert. Mirrored by `DEFAULT_APPEARANCE` in `frontend/src/composition/appearance.ts`; kept here as
#: literals (not introspected from the Pydantic model) so this module stays free of any import
#: on `composition.py`, avoiding a cycle (`composition.py` imports this module already).
DEFAULT_BACKGROUND_MAT: Final[str] = "museum"
DEFAULT_BACKGROUND_MOTION: Final[bool] = False
DEFAULT_BACKGROUND_CADENCE_SECONDS: Final[int] = 45

#: The token an authored canvas or block style needs.
#: Threaded exactly as `BACKGROUND_CANVAS_CAPABILITY` is: the canvas fields' and every
#: block style's defaults are what a receiver without the token already draws, so the token
#: is needed the instant any of them is authored away from its default -- the wire shape an
#: older strict parser rejects -- and pruned again when the last one returns to it.
BLOCK_STYLE_CAPABILITY: Final[str] = "block-style-v1"

#: The canvas defaults, literal for the same no-cycle reason as the background ones.
DEFAULT_MARGIN: Final[str] = "standard"
DEFAULT_FACE: Final[str] = "look"
DEFAULT_RADIUS: Final[str] = "look"

#: The token a picture that fills needs (fill plan D7): a tile that bleeds to the glass, an
#: image fitted `smart`, or an explicit `soft` radius (2u, no longer "the look's own"). Derived
#: from what is actually sent -- the resolved blocks and the appearance -- never stored, like
#: the card tokens: a collection's own `smart` fit reaches the wire without the document
#: naming it, and admission must still see it.
PICTURE_FILL_CAPABILITY: Final[str] = "picture-fill-v1"

#: The kinds whose tiles are pictures, and so read `edges` and `fit`.
PICTURE_KINDS: Final[frozenset[str]] = frozenset({"image", "media"})

#: A picture block's own choices, which the resolver keeps over its source's (fill step 4).
PICTURE_CHOICES: Final[tuple[str, ...]] = ("edges", "fit")


def background_requires_capability(
    background: str,
    *,
    background_source_id: str | None,
    background_mat: str,
    background_motion: bool,
    background_cadence_seconds: int,
) -> bool:
    """Whether a background needs `BACKGROUND_CANVAS_CAPABILITY` to render as authored.

    Takes plain values rather than an `Appearance`/`PortableAppearance` instance so the same
    rule applies to both models (the portable one omits `background_source_id` entirely, but
    still carries `background`/`background_mat`/`background_motion`/`background_cadence_seconds`
    and can equally need the token -- a published `weather` background, for instance).

    A photographic or condition-keyed background (`GATED_BACKGROUND_KINDS`) always needs the
    token. A flat/gradient background needs it too the instant any of the four settings is
    authored away from its default: an *authored* (non-default) setting is exactly the wire
    shape an older receiver's strict parser rejects, so the gate keys off "was anything actually
    set", not "does the current background use it".
    """
    return (
        background in GATED_BACKGROUND_KINDS
        or background_source_id is not None
        or background_mat != DEFAULT_BACKGROUND_MAT
        or background_motion != DEFAULT_BACKGROUND_MOTION
        or background_cadence_seconds != DEFAULT_BACKGROUND_CADENCE_SECONDS
    )


def canvas_requires_capability(*, margin: str, face: str, radius: str) -> bool:
    """Whether the canvas fields are authored away from the values every receiver draws."""
    return margin != DEFAULT_MARGIN or face != DEFAULT_FACE or radius != DEFAULT_RADIUS


def block_style_requires_capability(
    *, margin: str, face: str, radius: str, styled_blocks: int
) -> bool:
    """Whether a document needs `BLOCK_STYLE_CAPABILITY` to render as authored.

    `styled_blocks` is the number of block styles that are not all-default -- the serializer
    drops those, so on the wire it is simply the size of the `styles` map.
    """
    return styled_blocks > 0 or canvas_requires_capability(margin=margin, face=face, radius=radius)


#: The overlay settings' defaults, literal for the same no-cycle reason as the canvas ones.
#: Mirrored by `DEFAULT_APPEARANCE` in `frontend/src/composition/appearance.ts`.
DEFAULT_OVERLAY_CORNER: Final[str] = "bottom-left"
DEFAULT_OVERLAY_SCRIM: Final[str] = "standard"


def overlay_requires_capability(layout: str, *, overlay_corner: str, overlay_scrim: str) -> bool:
    """Whether a document needs `OVERLAY_LAYOUT_CAPABILITY` to render as authored.

    The family itself needs it (that much `LAYOUT_CAPABILITY` already says). The two settings
    need it independently, on the terms every other omitted-at-default field is gated by: the
    serializer drops them while they hold their defaults, so an authored one is exactly the
    wire shape an older strict parser rejects -- even under a non-overlay layout, where the
    settings are inert but still on the wire.
    """
    return (
        layout == "overlay"
        or overlay_corner != DEFAULT_OVERLAY_CORNER
        or overlay_scrim != DEFAULT_OVERLAY_SCRIM
    )


def picture_requires_capability(kind: str, settings: Mapping[str, object]) -> bool:
    """Whether one block's settings need `PICTURE_FILL_CAPABILITY`: a picture that bleeds or
    fits `smart`. `inside`, `fit` and `fill` are what every receiver already draws."""
    return kind in PICTURE_KINDS and (
        settings.get("edges") == "bleed" or settings.get("fit") == "smart"
    )


def radius_requires_picture_fill(radius: str) -> bool:
    """An explicit `soft` is 2u only for a receiver with `PICTURE_FILL_CAPABILITY`; an older
    one reads it as the look's own radius."""
    return radius == "soft"


class _Block(Protocol):
    @property
    def kind(self) -> str: ...

    @property
    def settings(self) -> Mapping[str, object]: ...


def picture_capabilities(radius: str, blocks: Iterable[_Block]) -> set[str]:
    """`{PICTURE_FILL_CAPABILITY}` when the radius or any block sent needs it, else empty.

    An authored `square` or `round` over a picture does not: an older receiver rounds the faces
    and leaves the picture tile square, which degrades rather than misdraws -- and a dashboard
    or package saved before fill step 13 must not start needing a token it never named (D7)."""
    sent = list(blocks)
    needed = radius_requires_picture_fill(radius) or any(
        picture_requires_capability(block.kind, block.settings) for block in sent
    )
    return {PICTURE_FILL_CAPABILITY} if needed else set()
