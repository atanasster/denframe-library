"""Moon & Sky: drawn Moon phases and bright-star patterns, in English and Bulgarian. Star
positions and brightnesses are from SIMBAD (CDS, Strasbourg); see brief.md and provenance.json.
Rewrites this folder's assets and source.json; see ../drawing.py."""

import math
from collections.abc import Sequence
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from drawing import REPOSITORY, SIZE, face, svg, write_pack  # noqa: E402

NIGHT = "#141b2e"
LIT = "#f3ecd4"
DARK = "#39425c"
LINE = "#6f7fa8"
STAR = "#ffffff"

# J2000 right ascension and declination (degrees) and V magnitude, from SIMBAD's basic table
# (queried 27 September 2026; Mizar's V from its primary, SIMBAD lists none for the pair).
STARS = {
    "Dubhe": (165.9319646738126, 61.751034687818226, 1.79),
    "Merak": (165.46033229797294, 56.382433649496384, 2.37),
    "Phecda": (178.45769715249997, 53.69475972916666, 2.44),
    "Megrez": (183.85649936126705, 57.03261697773611, 3.32),
    "Alioth": (193.5072899675, 55.95982295694445, 1.77),
    "Mizar": (200.98141866666666, 54.92535197222222, 2.27),
    "Alkaid": (206.88515734206297, 49.31326672942533, 1.86),
    "Polaris": (37.954560670189856, 89.26410896994187, 2.02),
    "Caph": (2.2945215777878776, 59.14978109800713, 2.27),
    "Schedar": (10.126846007691249, 56.537329217042775, 2.23),
    "Gamma Cas": (14.17721289375, 60.71674002472222, 2.39),
    "Ruchbah": (21.453964462083334, 60.23528402972222, 2.68),
    "Segin": (28.5988920257, 63.670100066329994, 3.37),
    "Betelgeuse": (88.79293899077537, 7.407063995272694, 0.42),
    "Rigel": (78.63446706693006, -8.201638364722209, 0.13),
    "Bellatrix": (81.28276355652378, 6.3497032644440665, 1.64),
    "Mintaka": (83.00166705557675, -0.29909510708333326, 2.41),
    "Alnilam": (84.05338894077023, -1.2019191358333312, 1.69),
    "Alnitak": (85.18969442793068, -1.9425735859722049, 1.77),
    "Saiph": (86.93912016833333, -9.66960491861111, 2.06),
    "Vega": (279.234734787025, 38.783688956244, 0.03),
    "Deneb": (310.35797975307673, 45.280338806527574, 1.25),
    "Altair": (297.69582729638694, 8.868321196436963, 0.76),
}


def project(
    names: list[str], level: tuple[str, str] | None = None
) -> dict[str, tuple[float, float]]:
    """Gnomonic projection about the pattern's centre, north up and east to the left (the sky
    as seen looking up), scaled to fill the picture with a margin."""
    vectors = {}
    for name in names:
        ra, dec, _ = STARS[name]
        a, d = math.radians(ra), math.radians(dec)
        vectors[name] = (math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d))
    sx, sy, sz = (sum(v[i] for v in vectors.values()) for i in range(3))
    norm = math.sqrt(sx * sx + sy * sy + sz * sz)
    centre = (sx / norm, sy / norm, sz / norm)
    ra0 = math.atan2(centre[1], centre[0])
    dec0 = math.asin(centre[2])
    flat = {}
    for name in names:
        ra, dec, _ = STARS[name]
        a, d = math.radians(ra), math.radians(dec)
        cosc = math.sin(dec0) * math.sin(d) + math.cos(dec0) * math.cos(d) * math.cos(a - ra0)
        x = math.cos(d) * math.sin(a - ra0) / cosc
        y = (math.cos(dec0) * math.sin(d) - math.sin(dec0) * math.cos(d) * math.cos(a - ra0)) / cosc
        flat[name] = (-x, y)  # east (increasing right ascension) to the left
    if level:
        # Turned about the centre until `level`'s two stars stand level: the same stars as they
        # stand at another hour of the night (the sky turns about the pole), not a different sky.
        (ax, ay), (bx, by) = flat[level[0]], flat[level[1]]
        turn = -math.atan2(by - ay, bx - ax)
        cos_t, sin_t = math.cos(turn), math.sin(turn)
        flat = {n: (x * cos_t - y * sin_t, x * sin_t + y * cos_t) for n, (x, y) in flat.items()}
    xs = [p[0] for p in flat.values()]
    ys = [p[1] for p in flat.values()]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = SIZE * 0.78 / span
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return {
        n: (SIZE / 2 + (p[0] - mx) * scale, SIZE / 2 - (p[1] - my) * scale) for n, p in flat.items()
    }


def star_radius(magnitude: float) -> float:
    return max(8.0, 26 - 5 * magnitude)


def sky(
    names: list[str],
    lines: list[tuple[str, str]],
    colours: dict[str, str] | None = None,
    dotted: Sequence[tuple[str, str]] = (),
    level: tuple[str, str] | None = None,
) -> str:
    at = project(names, level)
    parts = []
    for a, b in lines:
        parts.append(
            f'<line x1="{at[a][0]:.1f}" y1="{at[a][1]:.1f}" x2="{at[b][0]:.1f}" '
            f'y2="{at[b][1]:.1f}" stroke="{LINE}" stroke-width="5" stroke-linecap="round"/>'
        )
    for a, b in dotted:
        parts.append(
            f'<line x1="{at[a][0]:.1f}" y1="{at[a][1]:.1f}" x2="{at[b][0]:.1f}" '
            f'y2="{at[b][1]:.1f}" stroke="{LIT}" stroke-width="5" stroke-linecap="round" '
            f'stroke-dasharray="2 20"/>'
        )
    for name in names:
        x, y = at[name]
        radius = star_radius(STARS[name][2])
        colour = (colours or {}).get(name, STAR)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius * 1.9:.1f}" fill="{colour}" '
            f'opacity="0.18"/><circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'fill="{colour}"/>'
        )
    return svg("".join(parts), NIGHT)


def moon_shape(cx: float, cy: float, r: float, lit: float, waxing: bool) -> str:
    """The Moon as seen from the Northern Hemisphere: the whole disc in shadow, and the lit part
    bounded by the limb and the terminator, an ellipse of semi-axis r*|1 - 2*lit|."""
    parts = [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{DARK}"/>']
    if lit >= 0.999:
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{LIT}"/>')
    elif lit > 0.001:
        rx = r * abs(1 - 2 * lit)
        side = 1 if waxing else 0  # waxing: the right limb is lit
        # Limb: top to bottom along the lit side; terminator: bottom back to top, bulging toward
        # the lit side for a crescent and away from it for a gibbous Moon.
        crescent = lit < 0.5
        terminator_sweep = (1 - side) if crescent else side
        parts.append(
            f'<path d="M{cx},{cy - r} A{r},{r} 0 0 {side} {cx},{cy + r} '
            f'A{rx:.2f},{r} 0 0 {terminator_sweep} {cx},{cy - r} Z" fill="{LIT}"/>'
        )
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{LIT}" '
        f'stroke-opacity="0.35" stroke-width="3"/>'
    )
    return "".join(parts)


def moon(lit: float, waxing: bool) -> str:
    return svg(moon_shape(SIZE / 2, SIZE / 2, SIZE * 0.36, lit, waxing), NIGHT)


def cycle() -> str:
    """Eight phases in order, clockwise from the top: new, waxing crescent, first quarter,
    waxing gibbous, full, waning gibbous, last quarter, waning crescent."""
    phases = [
        (0, True),
        (0.25, True),
        (0.5, True),
        (0.75, True),
        (1, True),
        (0.75, False),
        (0.5, False),
        (0.25, False),
    ]
    parts = []
    for index, (lit, waxing) in enumerate(phases):
        angle = math.radians(index * 45)
        x = SIZE / 2 + SIZE * 0.34 * math.sin(angle)
        y = SIZE / 2 - SIZE * 0.34 * math.cos(angle)
        parts.append(moon_shape(round(x, 2), round(y, 2), SIZE * 0.085, lit, waxing))
    # An arrow round the middle, clockwise: the order the phases come in.
    r = SIZE * 0.17
    c = SIZE / 2
    parts.append(
        f'<path d="M{c},{c - r} A{r},{r} 0 1 1 {c - r},{c}" fill="none" stroke="{LINE}" '
        f'stroke-width="8" stroke-linecap="round"/>'
    )
    parts.append(
        f'<path d="M{c - r - 24},{c + 8} L{c - r},{c - 18} L{c - r + 24},{c + 8}" '
        f'fill="none" stroke="{LINE}" stroke-width="8" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )
    return svg("".join(parts), NIGHT)


DIPPER = ["Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"]
DIPPER_LINES = [
    ("Dubhe", "Merak"),
    ("Merak", "Phecda"),
    ("Phecda", "Megrez"),
    ("Megrez", "Dubhe"),
    ("Megrez", "Alioth"),
    ("Alioth", "Mizar"),
    ("Mizar", "Alkaid"),
]
CASSIOPEIA = ["Caph", "Schedar", "Gamma Cas", "Ruchbah", "Segin"]
ORION = ["Betelgeuse", "Bellatrix", "Mintaka", "Alnilam", "Alnitak", "Saiph", "Rigel"]
TRIANGLE = ["Vega", "Deneb", "Altair"]

PICTURES = {
    "full": moon(1, True),
    "first-quarter": moon(0.5, True),
    "waxing-crescent": moon(0.2, True),
    "waxing-gibbous": moon(0.78, True),
    "last-quarter": moon(0.5, False),
    "waning-crescent": moon(0.2, False),
    "cycle": cycle(),
    "big-dipper": sky(DIPPER, DIPPER_LINES),
    "polaris": sky([*DIPPER, "Polaris"], DIPPER_LINES, dotted=[("Merak", "Polaris")]),
    "cassiopeia": sky(
        CASSIOPEIA,
        [
            ("Caph", "Schedar"),
            ("Schedar", "Gamma Cas"),
            ("Gamma Cas", "Ruchbah"),
            ("Ruchbah", "Segin"),
        ],
        # Caph and Segin level, the W the card names (brief.md, Simplifications).
        level=("Segin", "Caph"),
    ),
    "orion": sky(
        ORION,
        [
            ("Betelgeuse", "Bellatrix"),
            ("Betelgeuse", "Alnitak"),
            ("Bellatrix", "Mintaka"),
            ("Mintaka", "Alnilam"),
            ("Alnilam", "Alnitak"),
            ("Alnitak", "Saiph"),
            ("Mintaka", "Rigel"),
        ],
        colours={"Betelgeuse": "#ffb27a", "Rigel": "#cfe0ff"},
    ),
    "summer-triangle": sky(TRIANGLE, [("Vega", "Deneb"), ("Deneb", "Altair"), ("Altair", "Vega")]),
}

MOON = "Original Moon drawing, made in code with AI assistance."
STARS_CREDIT = (
    "Original star chart, made in code with AI assistance. Positions and brightness: SIMBAD "
    "J2000 values (SIMBAD database, operated at CDS, Strasbourg, France)."
)
# The pictures drawn by `sky()`, which credit the star data they are drawn from.
STAR_CHARTS = {"big-dipper", "polaris", "cassiopeia", "orion", "summer-triangle"}
assert STAR_CHARTS <= set(PICTURES)


def credit(key: str) -> dict:
    return {
        "creator": "Mantel",
        "license": "CC0-1.0",
        "attribution": STARS_CREDIT if key in STAR_CHARTS else MOON,
        "source": f"{REPOSITORY}/moon-and-sky",
        "modified": False,
    }


# (id, picture, English prompt/reveal/alt, Bulgarian prompt/reveal/alt)
CARDS = [
    (
        "full-moon",
        "full",
        "Which phase of the Moon is this?",
        "Full moon. The whole side of the Moon that faces us is lit by the Sun.",
        "A round Moon, lit all over, on a dark sky.",
        "Коя фаза на Луната е това?",
        "Пълнолуние. Цялата страна на Луната, обърната към нас, е осветена от Слънцето.",
        "Кръгла Луна, осветена изцяло, на тъмно небе.",
    ),
    (
        "first-quarter",
        "first-quarter",
        "Which phase is this? The right half is lit.",
        "First quarter: half of the disc is lit, and the Moon is growing (waxing). Seen from the "
        "Northern Hemisphere, a growing Moon is lit on the right.",
        "The Moon with its right half lit and its left half dark.",
        "Коя фаза е това? Осветена е дясната половина.",
        "Първа четвърт: осветена е половината от диска и Луната расте. В Северното полукълбо "
        "растящата Луна е осветена отдясно.",
        "Луна с осветена дясна половина и тъмна лява половина.",
    ),
    (
        "waxing-crescent",
        "waxing-crescent",
        "A thin curve of light on the right. Is the Moon growing or shrinking?",
        "Growing. This is a waxing crescent: a few days after the new moon, the lit part gets "
        "bigger each night. (Seen from the Northern Hemisphere; south of the equator it is lit "
        "on the left.)",
        "A thin curved sliver of light on the right edge of the Moon; the rest is dark.",
        "Тънък светъл сърп отдясно. Луната расте ли, или намалява?",
        "Расте. Това е растящ сърп: няколко дни след новолунието осветената част става по-голяма "
        "всяка нощ. (Така я виждаме в Северното полукълбо; на юг от екватора е осветена отляво.)",
        "Тънък светъл сърп по десния край на Луната; останалата част е тъмна.",
    ),
    (
        "waxing-gibbous",
        "waxing-gibbous",
        "More than half of the Moon is lit, on the right. What comes next?",
        "The full moon. This is a waxing gibbous Moon: it keeps growing until the whole face is "
        "lit. (Seen from the Northern Hemisphere; south of the equator it is lit on the left.)",
        "The Moon lit on its right side and across more than half of its face; a narrow dark part "
        "on the left.",
        "Осветена е повече от половината Луна, отдясно. Какво следва?",
        "Пълнолуние. Това е растяща изпъкнала Луна: расте, докато се освети целият ѝ диск. "
        "(Така я виждаме в Северното полукълбо; на юг от екватора е осветена отляво.)",
        "Луна, осветена отдясно и повече от наполовина; тясна тъмна част отляво.",
    ),
    (
        "last-quarter",
        "last-quarter",
        "Which phase is this? The left half is lit.",
        "Last quarter (also called third quarter): half of the disc is lit, and the Moon is "
        "shrinking (waning). Seen from the Northern Hemisphere, a shrinking Moon is lit on the left.",
        "The Moon with its left half lit and its right half dark.",
        "Коя фаза е това? Осветена е лявата половина.",
        "Последна четвърт: осветена е половината от диска и Луната намалява. В Северното "
        "полукълбо намаляващата Луна е осветена отляво.",
        "Луна с осветена лява половина и тъмна дясна половина.",
    ),
    (
        "waning-crescent",
        "waning-crescent",
        "A thin curve of light on the left. What phase comes after it?",
        "The new moon, when we cannot see the lit side at all. This is a waning crescent, the "
        "last thin sliver before it. (Seen from the Northern Hemisphere; south of the equator it "
        "is on the right.)",
        "A thin curved sliver of light on the left edge of the Moon; the rest is dark.",
        "Тънък светъл сърп отляво. Коя фаза идва след него?",
        "Новолунието, когато изобщо не виждаме осветената страна. Това е намаляващ сърп – "
        "последната тънка ивица преди него. (Така го виждаме в Северното полукълбо; на юг от "
        "екватора е отдясно.)",
        "Тънък светъл сърп по левия край на Луната; останалата част е тъмна.",
    ),
    (
        "moon-cycle",
        "cycle",
        "About how many days pass from one full moon to the next?",
        "About 29 and a half days. The Moon goes through all its phases in that time: new, "
        "crescent, quarter, gibbous, full, and back.",
        "Eight small Moons in a ring, in order clockwise from the top: dark, then a growing sliver, "
        "half, more than half, full, and shrinking back.",
        "Колко дни минават приблизително от едно пълнолуние до следващото?",
        "Около 29 дни и половина. За това време Луната минава през всичките си фази: новолуние, "
        "сърп, четвърт, изпъкнала Луна, пълнолуние и обратно.",
        "Осем малки Луни в кръг, по реда на часовниковата стрелка отгоре: тъмна, растящ сърп, "
        "половина, повече от половина, пълна и отново намаляваща.",
    ),
    (
        "big-dipper",
        "big-dipper",
        "Seven stars make a shape like a big ladle. What is it called?",
        "The Big Dipper, also called the Plough. It is part of the constellation Ursa Major, the "
        "Great Bear.",
        "Seven stars joined by lines: four make a bowl and three make a bent handle.",
        "Седем звезди образуват нещо като голям черпак. Как се нарича?",
        "Голямата кола. Тя е част от съзвездието Голямата мечка.",
        "Седем звезди, свързани с линии: четири образуват купа, а три – извита дръжка.",
    ),
    (
        "pole-star",
        "polaris",
        "Draw a line from the bottom of the bowl through its two end stars, out past the top of "
        "the bowl. Which star does it reach?",
        "Polaris, the North Star. It stays almost still above the northern horizon while the other "
        "stars turn around it.",
        "The seven stars of the ladle, with a dotted line from the bottom of the bowl through its "
        "two end stars and out of the bowl to one star on its own.",
        "Продължи линията от дъното на купата през двете ѝ крайни звезди, нагоре извън купата. "
        "До коя звезда стига?",
        "До Полярната звезда. Тя стои почти неподвижно над северния хоризонт, а другите звезди "
        "се въртят около нея.",
        "Седемте звезди на черпака и пунктирна линия от дъното на купата през двете ѝ крайни "
        "звезди и извън купата до една самотна звезда.",
    ),
    (
        "cassiopeia",
        "cassiopeia",
        "Five bright stars make a W (or an M). Which constellation is it?",
        "Cassiopeia. It sits on the other side of the North Star from the Big Dipper.",
        "Five stars joined in a zigzag line shaped like the letter W.",
        "Пет ярки звезди образуват буквата W (или M). Кое съзвездие е това?",
        "Касиопея. Тя е от другата страна на Полярната звезда спрямо Голямата кола.",
        "Пет звезди, свързани в зигзагообразна линия с формата на буквата W.",
    ),
    (
        "orion",
        "orion",
        "Three stars in a short straight row are this hunter's belt. Who is he?",
        "Orion. Look for his belt, reddish Betelgeuse at one shoulder and bright blue-white Rigel "
        "at one foot.",
        "Seven stars: three in a short straight row in the middle, two above it and two below; the "
        "top left star is reddish and the bottom right one blue-white.",
        "Три звезди в къса права редица са коланът на този ловец. Кой е той?",
        "Орион. Потърси колана му, червеникавата Бетелгейзе на едното рамо и ярката синьо-бяла "
        "Ригел при единия крак.",
        "Седем звезди: три в къса права редица по средата, две над нея и две под нея; горната "
        "лява звезда е червеникава, а долната дясна – синьо-бяла.",
    ),
    (
        "summer-triangle",
        "summer-triangle",
        "Three bright stars, each in a different constellation, make a big triangle on summer "
        "nights. What is it called?",
        "The Summer Triangle: Vega, Deneb and Altair.",
        "Three bright stars joined by lines into a tall triangle.",
        "Три ярки звезди, всяка от различно съзвездие, образуват голям триъгълник през летните "
        "нощи. Как се нарича?",
        "Летният триъгълник: Вега, Денеб и Алтаир.",
        "Три ярки звезди, свързани с линии във висок триъгълник.",
    ),
]


SOURCES = [
    {
        "supports": "Phase names and order, the Moon always half lit by the Sun, and the cycle of "
        "about 29.5 days.",
        "url": "https://science.nasa.gov/moon/moon-phases/",
    },
    {
        "supports": "The two end stars of the Big Dipper's bowl (Dubhe and Merak) point to "
        "Polaris, which stays in roughly the same place while other stars circle the pole.",
        "url": "https://science.nasa.gov/solar-system/what-is-the-north-star-and-how-do-you-find-it/",
    },
    {
        "supports": "Cassiopeia's W or M shape.",
        "url": "https://science.nasa.gov/solar-system/skywatching/night-sky-network/feb2024-night-sky-notes/",
    },
    {
        "supports": "The Summer Triangle: Vega (Lyra), Deneb (Cygnus) and Altair (Aquila).",
        "url": "https://science.nasa.gov/solar-system/skywatching/night-sky-network/the-summer-triangles-hidden-treasures/",
    },
    {
        "supports": "Every star's J2000 position and V magnitude (the drawings), the Big Dipper "
        "and Cassiopeia about 12 hours of right ascension apart round the pole (opposite sides "
        "of Polaris), Betelgeuse's red (M) and Rigel's blue-white (B) spectral types. SIMBAD "
        "TAP query of the basic and allfluxes tables, 27 September 2026. This research has made "
        "use of the SIMBAD database, operated at CDS, Strasbourg, France.",
        "url": "https://simbad.cds.unistra.fr/simbad/",
    },
]


def main() -> None:
    items = []
    for ident, key, en_p, en_r, en_alt, bg_p, bg_r, bg_alt in CARDS:
        items.append(
            {
                "id": ident,
                "content_revision": 1,
                "translations": {
                    "en": {"prompt": face(en_p, key, en_alt), "reveal": face(en_r, key, en_alt)},
                    "bg": {"prompt": face(bg_p, key, bg_alt), "reveal": face(bg_r, key, bg_alt)},
                },
                "audio_cues": [],
            }
        )
    order = [item["id"] for item in items]
    timing = {"prompt_seconds": 9, "recall_seconds": 4, "reveal_seconds": 11, "dwell_seconds": 2}
    write_pack(
        HERE,
        header={
            "id": "mantel/moon-and-sky",
            "version": "1.0.0",
            "publisher": "Mantel",
            "definition": {
                "schema_version": 2,
                "kind": "pack",
                "name": "Moon & Sky",
                "description": (
                    "The Moon's phases and five star patterns to find on a clear night, drawn "
                    "from catalogue positions. English and Bulgarian, no sound. Review "
                    "candidate: content and Bulgarian reading pending."
                ),
                "locales": ["en", "bg"],
            },
        },
        pictures=PICTURES,
        credit={key: credit(key) for key in PICTURES},
        items=items,
        activities=[
            {
                "id": "sky-en",
                "name": "Moon and sky",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "en",
                "loop": False,
                "timing": timing,
            },
            {
                "id": "sky-bg",
                "name": "Луната и небето",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "bg",
                "loop": False,
                "timing": timing,
            },
        ],
        provenance={
            "pack": "mantel/moon-and-sky",
            "drawn": "2026-09-27",
            "authorship": "Text and drawing code drafted for Mantel with AI assistance (Claude); "
            "a person reviews every pack before it is approved (plan D26).",
            "narration": "None. eSpeak NG, the only voice the plan allows (D26), was not "
            "installed where the pack was drawn; the cards are text-first and silent.",
            "sources": SOURCES,
        },
    )


if __name__ == "__main__":
    main()
