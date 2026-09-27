"""Look distinctness in OKLab (design.md): how far a submitted look sits from every catalog look.

Runs inside the review sandbox with only the standard library and `mantel_format`.
"""

from __future__ import annotations

import itertools
import math

# The roles that make a look recognisable. Border and the two status colours are left out:
# every shipped look uses near-identical positive/negative hues, and borders are decorative.
ROLES = ("background", "surface", "text", "mutedText", "accent", "accentText")
# design.md: the minimum distance a new look keeps from every catalog look, in OKLab ΔE x 100.
THRESHOLD = 2.0


def _linear(byte: int) -> float:
    value = byte / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def oklab(color: str) -> tuple[float, float, float]:
    """Björn Ottosson's OKLab of an sRGB `#rrggbb`."""
    red, green, blue = (_linear(int(color[index : index + 2], 16)) for index in (1, 3, 5))
    long = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    long, medium, short = (math.copysign(abs(x) ** (1 / 3), x) for x in (long, medium, short))
    return (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )


def delta_e(first: str, second: str) -> float:
    """OKLab Euclidean distance, scaled by 100 (1.0 here is 0.01 in OKLab units)."""
    return 100 * math.dist(oklab(first), oklab(second))


def role_distances(first: dict[str, str], second: dict[str, str]) -> dict[str, float]:
    return {role: delta_e(first[role], second[role]) for role in ROLES}


def distance(first: dict[str, str], second: dict[str, str]) -> float:
    """The mean per-role ΔE after dropping the single largest one.

    Dropping the largest makes the measure blind to one swapped colour: a catalog look with
    only its accent changed scores the same as the look itself, so "beyond swapping one
    accent" (plan §5.1) is what has to clear the threshold.
    """
    values = sorted(role_distances(first, second).values(), reverse=True)[1:]
    return sum(values) / len(values)


def nearest(palette: dict[str, str], looks: dict[str, dict[str, str]]) -> list[dict]:
    """Every catalog look by distance, nearest first."""
    rows = [
        {
            "look": name,
            "distance": round(distance(palette, tokens), 2),
            "roles": {
                role: round(value, 2) for role, value in role_distances(palette, tokens).items()
            },
        }
        for name, tokens in looks.items()
    ]
    return sorted(rows, key=lambda row: (row["distance"], row["look"]))


def pairwise(looks: dict[str, dict[str, str]]) -> list[dict]:
    """Every pair of catalog looks by distance, closest first (the calibration table)."""
    rows = [
        {"pair": [a, b], "distance": round(distance(looks[a], looks[b]), 2)}
        for a, b in itertools.combinations(sorted(looks), 2)
    ]
    return sorted(rows, key=lambda row: (row["distance"], row["pair"]))
