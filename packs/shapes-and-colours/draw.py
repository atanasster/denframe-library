"""Shapes & Colours: drawn shapes in English and Bulgarian. Every shape has a dark outline and
its colour's own pattern (solid, stripes, dots, hatching, checks, grid), so shapes and colours
can be told apart without colour alone. Rewrites this folder's assets and source.json; see
../drawing.py."""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from drawing import REPOSITORY, SIZE, face, svg, write_pack  # noqa: E402

PLATE = "#fbf8f2"
INK = "#26292e"

# Each colour carries a pattern of its own, drawn in a lighter or darker tone of it.
COLOURS = {
    "red": ("#d23c3c", None),
    "blue": (
        "#2f62c9",
        '<pattern id="blue" width="56" height="56" patternUnits="userSpaceOnUse">'
        '<rect width="56" height="56" fill="#2f62c9"/><rect y="36" width="56" height="20" '
        'fill="#9fb8ec"/></pattern>',
    ),
    "yellow": (
        "#f2c230",
        '<pattern id="yellow" width="64" height="64" patternUnits="userSpaceOnUse">'
        '<rect width="64" height="64" fill="#f2c230"/><circle cx="32" cy="32" r="12" '
        'fill="#9a6b00"/></pattern>',
    ),
    "green": (
        "#2e9e5b",
        '<pattern id="green" width="50" height="50" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="50" height="50" fill="#2e9e5b"/>'
        '<rect width="18" height="50" fill="#a8e0bd"/></pattern>',
    ),
    "orange": (
        "#ee7d22",
        '<pattern id="orange" width="80" height="80" patternUnits="userSpaceOnUse">'
        '<rect width="80" height="80" fill="#ee7d22"/><rect width="40" height="40" '
        'fill="#f8c08f"/><rect x="40" y="40" width="40" height="40" fill="#f8c08f"/>'
        "</pattern>",
    ),
    "purple": (
        "#7e4bb5",
        '<pattern id="purple" width="60" height="60" patternUnits="userSpaceOnUse">'
        '<rect width="60" height="60" fill="#7e4bb5"/><path d="M0,0 H60 M0,0 V60" '
        'stroke="#d5c0ee" stroke-width="16"/></pattern>',
    ),
}
PATTERN_WORDS = {
    "en": {
        "red": "solid red",
        "blue": "blue with stripes",
        "yellow": "yellow with dots",
        "green": "green with slanted stripes",
        "orange": "orange with checks",
        "purple": "purple with a grid",
    },
    # Feminine, agreeing with "фигура".
    "bg": {
        "red": "плътно червена",
        "blue": "синя на ивици",
        "yellow": "жълта на точки",
        "green": "зелена на наклонени ивици",
        "orange": "оранжева на квадратчета",
        "purple": "лилава на мрежа",
    },
}


def fill(colour: str) -> str:
    base, pattern = COLOURS[colour]
    return f"url(#{colour})" if pattern else base


def polygon(cx: float, cy: float, r: float, sides: int, rotate: float = 0) -> str:
    points = []
    for index in range(sides):
        angle = math.radians(rotate + index * 360 / sides)
        points.append(f"{cx + r * math.sin(angle):.1f},{cy - r * math.cos(angle):.1f}")
    return " ".join(points)


def shape(kind: str, cx: float, cy: float, r: float, colour: str) -> str:
    style = f'fill="{fill(colour)}" stroke="{INK}" stroke-width="{max(8, r * 0.07):.1f}" stroke-linejoin="round"'
    if kind == "circle":
        return f'<circle cx="{cx}" cy="{cy}" r="{r}" {style}/>'
    if kind == "oval":
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * 0.62:.1f}" {style}/>'
    if kind == "square":
        side = r * 1.6
        return f'<rect x="{cx - side / 2}" y="{cy - side / 2}" width="{side}" height="{side}" {style}/>'
    if kind == "rectangle":
        return (
            f'<rect x="{cx - r}" y="{cy - r * 0.58:.1f}" width="{2 * r}" '
            f'height="{r * 1.16:.1f}" {style}/>'
        )
    if kind == "triangle":
        return f'<polygon points="{polygon(cx, cy + r * 0.18, r * 1.05, 3)}" {style}/>'
    if kind == "pentagon":
        return f'<polygon points="{polygon(cx, cy + r * 0.05, r, 5)}" {style}/>'
    if kind == "hexagon":
        return f'<polygon points="{polygon(cx, cy, r, 6, 30)}" {style}/>'
    if kind == "rhombus":
        return (
            f'<polygon points="{cx},{cy - r} {cx + r * 0.68:.1f},{cy} {cx},{cy + r} '
            f'{cx - r * 0.68:.1f},{cy}" {style}/>'
        )
    if kind == "star":
        points = []
        for index in range(10):
            radius = r if index % 2 == 0 else r * 0.42
            angle = math.radians(index * 36)
            points.append(
                f"{cx + radius * math.sin(angle):.1f},{cy + r * 0.08 - radius * math.cos(angle):.1f}"
            )
        return f'<polygon points="{" ".join(points)}" {style}/>'
    raise ValueError(kind)


def picture(*shapes: tuple[str, str]) -> str:
    """One shape large, or two or three in a row from left to right."""
    used = {colour for _, colour in shapes}
    defs = "".join(
        COLOURS[colour][1] for colour in COLOURS if colour in used and COLOURS[colour][1]
    )
    if len(shapes) == 1:
        body = shape(shapes[0][0], SIZE / 2, SIZE / 2, SIZE * 0.33, shapes[0][1])
    else:
        step = SIZE / len(shapes)
        body = "".join(
            shape(kind, step * (index + 0.5), SIZE / 2, step * 0.4, colour)
            for index, (kind, colour) in enumerate(shapes)
        )
    return svg(f"<defs>{defs}</defs>{body}", PLATE)


def described(
    shapes: list[tuple[str, str]], locale: str, *, prompt: bool, colour_question: bool = False
) -> str:
    """The shapes by outline and pattern, left to right. On a prompt face the outline is told
    without its count or name (`PROMPT_OUTLINES`), and a card that asks for a colour lists the
    colours apart from the shapes: a screen-reader user answers the same question a sighted child
    does, never reads the answer. The reveal face tells everything (`OUTLINES`)."""
    words = PATTERN_WORDS[locale]
    outlines = (PROMPT_OUTLINES if prompt else OUTLINES)[locale]
    count = len(shapes)
    if prompt and colour_question:
        # The colours turned one place, so their order never pairs them with the shapes.
        turned = shapes[1:] + shapes[:1]
        colours = ", ".join(words[colour] for _, colour in turned)
        listed = ", ".join(SHAPE_NAMES[locale][kind] for kind, _ in shapes)
        if locale == "en":
            return (
                f"{NUMBERS[locale][count]} shapes in a row: {listed}. Their colours, in another "
                f"order: {colours}."
            )
        return f"{NUMBERS[locale][count]} фигури в редица: {listed}. Цветовете им, в друг ред: {colours}."
    parts = [f"{outlines[kind]}, {words[colour]}" for kind, colour in shapes]
    if locale == "en":
        if count == 1:
            return f"One large shape: {parts[0]}."
        return f"{NUMBERS[locale][count]} shapes in a row, left to right: " + "; ".join(parts) + "."
    if count == 1:
        return f"Една голяма фигура: {parts[0]}."
    return f"{NUMBERS[locale][count]} фигури в редица, отляво надясно: " + "; ".join(parts) + "."


NUMBERS = {"en": {2: "Two", 3: "Three"}, "bg": {2: "Две", 3: "Три"}}
SHAPE_NAMES = {
    "en": {
        "star": "a star",
        "oval": "an oval",
        "square": "a square",
        "circle": "a circle",
        "triangle": "a triangle",
    },
    "bg": {
        "star": "звезда",
        "oval": "овал",
        "square": "квадрат",
        "circle": "кръг",
        "triangle": "триъгълник",
    },
}
# A prompt face's outline: what the picture shows, without the count or the name it asks for.
PROMPT_OUTLINES = {
    "en": {
        "circle": "round all the way round",
        "triangle": "pointed at the top, with a flat bottom",
        "square": "straight sides, as tall as it is wide",
        "rectangle": "straight sides, wider than it is tall",
        "star": "pointed arms around its middle",
        "oval": "round but stretched wide, like an egg",
        "hexagon": "straight sides, all the same length, like a honeycomb cell",
        "rhombus": "straight sides, standing on one corner",
        "pentagon": "straight sides, all the same length, with a point at the top",
    },
    "bg": {
        "circle": "кръгла отвсякъде",
        "triangle": "заострена отгоре, с плоско дъно",
        "square": "с прави страни, еднакво висока и широка",
        "rectangle": "с прави страни, по-широка, отколкото висока",
        "star": "с остри лъчи около средата",
        "oval": "закръглена, но разтеглена като яйце",
        "hexagon": "с прави, еднакво дълги страни, като килийка от пчелна пита",
        "rhombus": "с прави страни, изправена на единия си ъгъл",
        "pentagon": "с прави, еднакво дълги страни и връх отгоре",
    },
}
# The cards that ask for a colour.
COLOUR_QUESTIONS = {"which-purple"}


# A reveal face's outline: everything the picture shows, counts included.
OUTLINES = {
    "en": {
        "circle": "round, with no corners",
        "triangle": "three straight sides and three corners",
        "square": "four equal sides and four square corners",
        "rectangle": "four sides, two long and two short",
        "star": "five points",
        "oval": "round but stretched wide, like an egg",
        "hexagon": "six equal sides",
        "rhombus": "four equal sides, standing on one corner",
        "pentagon": "five equal sides",
    },
    "bg": {
        "circle": "кръгла, без ъгли",
        "triangle": "три прави страни и три ъгъла",
        "square": "четири равни страни и четири прави ъгъла",
        "rectangle": "четири страни, две дълги и две къси",
        "star": "пет лъча",
        "oval": "закръглена, но разтеглена като яйце",
        "hexagon": "шест равни страни",
        "rhombus": "четири равни страни, изправена на единия си ъгъл",
        "pentagon": "пет равни страни",
    },
}

# (id, shapes, English prompt, English reveal, Bulgarian prompt, Bulgarian reveal)
CARDS = [
    (
        "circle",
        [("circle", "red")],
        "What shape is this?",
        "A circle. It is round and has no corners. This circle is red.",
        "Каква фигура е това?",
        "Кръг. Той е кръгъл и няма ъгли. Този кръг е червен.",
    ),
    (
        "triangle",
        [("triangle", "blue")],
        "What shape is this? Count its corners.",
        "A triangle: three sides and three corners. This one is blue, with stripes.",
        "Каква фигура е това? Преброй ъглите ѝ.",
        "Триъгълник: три страни и три ъгъла. Този е син, на ивици.",
    ),
    (
        "square",
        [("square", "yellow")],
        "What shape is this? Look at its sides.",
        "A square: four sides, all the same length, and four square corners. This one is yellow, "
        "with dots.",
        "Каква фигура е това? Разгледай страните ѝ.",
        "Квадрат: четири еднакво дълги страни и четири прави ъгъла. Този е жълт, на точки.",
    ),
    (
        "rectangle",
        [("rectangle", "green")],
        "Four sides, but not all the same length. What shape is this?",
        "A rectangle: two long sides and two short sides. This one is green, with slanted stripes.",
        "Четири страни, но не еднакво дълги. Каква фигура е това?",
        "Правоъгълник: две дълги и две къси страни. Този е зелен, на наклонени ивици.",
    ),
    (
        "star",
        [("star", "orange")],
        "What shape is this? Count its points.",
        "A star with five points. This one is orange, with checks.",
        "Каква фигура е това? Преброй лъчите ѝ.",
        "Звезда с пет лъча. Тази е оранжева, на квадратчета.",
    ),
    (
        "oval",
        [("oval", "purple")],
        "Round, but stretched like an egg. What shape is this?",
        "An oval. It has no corners, like a circle, but it is longer one way. This one is purple, "
        "with a grid.",
        "Кръгла, но разтеглена като яйце. Каква фигура е това?",
        "Овал. Няма ъгли, като кръга, но е по-дълъг в едната посока. Този е лилав, на мрежа.",
    ),
    (
        "hexagon",
        [("hexagon", "blue")],
        "Bees build honeycomb cells in this shape. How many sides does it have?",
        "Six. A shape with six sides is a hexagon. This one is blue, with stripes.",
        "Пчелите правят килийките на пчелната пита с тази форма. Колко страни има тя?",
        "Шест. Фигура с шест страни е шестоъгълник. Този е син, на ивици.",
    ),
    (
        "rhombus",
        [("rhombus", "red")],
        "Four sides the same length, standing on a corner. What shape is this?",
        "A rhombus, often called a diamond. It is like a square pushed over. This one is red.",
        "Четири еднакво дълги страни, изправена на ъгъл. Каква фигура е това?",
        "Ромб. Прилича на наклонен квадрат. Този е червен.",
    ),
    (
        "pentagon",
        [("pentagon", "green")],
        "How many sides does this shape have?",
        "Five. A shape with five sides is a pentagon. This one is green, with slanted stripes.",
        "Колко страни има тази фигура?",
        "Пет. Фигура с пет страни е петоъгълник. Този е зелен, на наклонени ивици.",
    ),
    (
        "three-corners",
        [("circle", "yellow"), ("square", "green"), ("triangle", "red")],
        "Which shape has three corners: the one on the left, in the middle or on the right?",
        "The triangle, on the right. It is red. The circle has no corners and the square has four.",
        "Коя фигура има три ъгъла: лявата, средната или дясната?",
        "Триъгълникът, вдясно. Той е червен. Кръгът няма ъгли, а квадратът има четири.",
    ),
    (
        "which-purple",
        [("star", "orange"), ("oval", "purple"), ("square", "blue")],
        "Which shape is purple: the star, the oval or the square?",
        "The oval, in the middle: purple, with a grid. The star is orange with checks; the square "
        "is blue with stripes.",
        "Коя фигура е лилава: звездата, овалът или квадратът?",
        "Овалът, в средата: лилав, на мрежа. Звездата е оранжева на квадратчета, а квадратът е "
        "син на ивици.",
    ),
    (
        "can-roll",
        [("triangle", "orange"), ("circle", "blue"), ("square", "red")],
        "Which of these shapes could roll along the floor?",
        "The circle, in the middle. It has no corners, so it can roll. Corners stop the triangle "
        "and the square.",
        "Коя от тези фигури може да се търкаля по пода?",
        "Кръгът, в средата. Той няма ъгли и затова може да се търкаля. Ъглите спират "
        "триъгълника и квадрата.",
    ),
]

CREDIT = {
    "creator": "Denframe",
    "license": "CC0-1.0",
    "attribution": "Original shape drawing, made in code with AI assistance.",
    "source": f"{REPOSITORY}/shapes-and-colours",
    "modified": False,
}


SOURCES = [
    {
        "supports": "Shape names and properties (sides, corners) are elementary geometry; the "
        "colour-and-pattern pairing is this pack's own design so no card depends on colour "
        "alone.",
        "url": None,
    },
]


def main() -> None:
    pictures, items = {}, []
    for ident, shapes, en_p, en_r, bg_p, bg_r in CARDS:
        pictures[ident] = picture(*shapes)
        asks_colour = ident in COLOUR_QUESTIONS
        alt = {
            (locale, phase): described(
                shapes, locale, prompt=phase == "prompt", colour_question=asks_colour
            )
            for locale in ("en", "bg")
            for phase in ("prompt", "reveal")
        }
        items.append(
            {
                "id": ident,
                "content_revision": 1,
                "translations": {
                    "en": {
                        "prompt": face(en_p, ident, alt["en", "prompt"]),
                        "reveal": face(en_r, ident, alt["en", "reveal"]),
                    },
                    "bg": {
                        "prompt": face(bg_p, ident, alt["bg", "prompt"]),
                        "reveal": face(bg_r, ident, alt["bg", "reveal"]),
                    },
                },
                "audio_cues": [],
            }
        )
    order = [item["id"] for item in items]
    timing = {"prompt_seconds": 7, "recall_seconds": 3, "reveal_seconds": 8, "dwell_seconds": 2}
    write_pack(
        HERE,
        header={
            "id": "denframe/shapes-and-colours",
            "version": "1.0.1",
            "publisher": "Denframe",
            "definition": {
                "schema_version": 2,
                "kind": "pack",
                "name": "Shapes & Colours",
                "description": (
                    "Name nine shapes and six colours, then find them in a row. Each colour has "
                    "its own pattern, so no card needs colour alone. English and Bulgarian, no "
                    "sound."
                ),
                "locales": ["en", "bg"],
            },
        },
        pictures=pictures,
        credit={key: CREDIT for key in pictures},
        items=items,
        activities=[
            {
                "id": "shapes-en",
                "name": "Shapes and colours",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "en",
                "loop": False,
                "timing": timing,
            },
            {
                "id": "shapes-bg",
                "name": "Фигури и цветове",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "bg",
                "loop": False,
                "timing": timing,
            },
        ],
        provenance={
            "pack": "denframe/shapes-and-colours",
            "drawn": "2026-09-27",
            "authorship": "Text and drawing code drafted for Denframe with AI assistance (Claude); "
            "a person reviews every pack before it is approved (plan D26).",
            "narration": "None. eSpeak NG, the only voice the plan allows (D26), was not "
            "installed where the pack was drawn; the cards are text-first and silent.",
            "sources": SOURCES,
        },
    )


if __name__ == "__main__":
    main()
