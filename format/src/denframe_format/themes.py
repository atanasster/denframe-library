"""Canonical built-in paint and appearance definitions, shared with the receiver build."""

import json
from importlib.resources import files

from .palette_contrast import STORED_PAIRS, PaletteContrastError, PaletteVerdict, palette_verdict

BUILTIN_THEMES = json.loads(
    files("denframe_format").joinpath("data/themes.json").read_text(encoding="utf-8")
)


def look_palette(look: str, tokens: dict[str, str]) -> dict[str, str]:
    """A look's own tokens with an authored override merged over them."""
    return {**next(item["tokens"] for item in BUILTIN_THEMES if item["look"] == look), **tokens}


def palette_verdict_for(look: str, tokens: dict[str, str]) -> PaletteVerdict | None:
    """The whole gate (fill step 15), the picture scrim included: what a palette the household
    is choosing now has to clear."""
    return palette_verdict(look_palette(look, tokens))


def validate_palette(look: str, tokens: dict[str, str]) -> None:
    """The gate a stored palette was held to, for authored packs and local scenes alike.

    It leaves out the picture scrim, which joined the gate later (fill step 15): a palette
    stored before then still loads and saves on an unrelated edit, and Studio flags it. A
    palette being chosen is judged by `palette_verdict_for`, before this runs.
    """
    verdict = palette_verdict(look_palette(look, tokens), pairs=STORED_PAIRS)
    if verdict is not None:
        raise PaletteContrastError(verdict)
