"""Tell the Time: twelve drawn clock faces (o'clock, half past, quarter past, quarter to), in
English and Bulgarian. Rewrites this folder's assets and source.json; see ../drawing.py."""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from drawing import REPOSITORY, SIZE, face, numeral, svg, write_pack  # noqa: E402

PLATE = "#f4efe4"
INK = "#26292e"
HOUR = "#1f3a6b"
MINUTE = "#c2410c"

EN_HOURS = [
    "twelve",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
]
BG_HOURS = [
    "дванайсет",
    "един",
    "два",
    "три",
    "четири",
    "пет",
    "шест",
    "седем",
    "осем",
    "девет",
    "десет",
    "единайсет",
    "дванайсет",
]


def clock(hour: int, minute: int) -> str:
    c, radius = SIZE / 2, SIZE * 0.42
    parts = [
        f'<circle cx="{c}" cy="{c}" r="{radius}" fill="#ffffff" stroke="{INK}" stroke-width="16"/>'
    ]
    for tick in range(60):
        angle = math.radians(tick * 6)
        outer = radius - 20
        inner = outer - (26 if tick % 5 == 0 else 12)
        width = 7 if tick % 5 == 0 else 3
        parts.append(
            f'<line x1="{c + inner * math.sin(angle):.2f}" y1="{c - inner * math.cos(angle):.2f}" '
            f'x2="{c + outer * math.sin(angle):.2f}" y2="{c - outer * math.cos(angle):.2f}" '
            f'stroke="{INK}" stroke-width="{width}" stroke-linecap="round"/>'
        )
    for number in range(1, 13):
        angle = math.radians(number * 30)
        at = radius - 88
        parts.append(
            numeral(str(number), c + at * math.sin(angle), c - at * math.cos(angle), 46, INK, 6.5)
        )

    def hand(angle_degrees: float, length: float, width: float, colour: str) -> str:
        angle = math.radians(angle_degrees)
        tail = 0.16 * length
        return (
            f'<line x1="{c - tail * math.sin(angle):.2f}" y1="{c + tail * math.cos(angle):.2f}" '
            f'x2="{c + length * math.sin(angle):.2f}" y2="{c - length * math.cos(angle):.2f}" '
            f'stroke="{colour}" stroke-width="{width}" stroke-linecap="round"/>'
        )

    # The hour hand moves between numbers as the minutes pass: at half past it sits halfway.
    parts.append(hand((hour % 12 + minute / 60) * 30, radius * 0.5, 26, HOUR))
    parts.append(hand(minute * 6, radius * 0.84, 13, MINUTE))
    parts.append(f'<circle cx="{c}" cy="{c}" r="20" fill="{INK}"/>')
    return svg("".join(parts), PLATE)


# The number the long hand points at, for each quarter of the hour.
MINUTE_NUMERAL = {0: "12", 15: "3", 30: "6", 45: "9"}


def alt(hour: int, minute: int, locale: str) -> str:
    """What the picture shows, hand by hand, without naming the time."""
    nxt = hour % 12 + 1
    points = MINUTE_NUMERAL[minute]
    if locale == "en":
        if minute == 0:
            short = f"points straight at {hour}"
        elif minute == 30:
            short = f"is halfway between {hour} and {nxt}"
        elif minute == 15:
            short = f"is just past {hour}"
        else:
            short = f"is nearly at {nxt}"
        return f"A round clock with the numbers 1 to 12. The short hand {short}; the long hand points at {points}."
    if minute == 0:
        short = f"сочи точно {hour}"
    elif minute == 30:
        short = f"е по средата между {hour} и {nxt}"
    elif minute == 15:
        short = f"е малко след {hour}"
    else:
        short = f"е почти на {nxt}"
    return (
        f"Кръгъл часовник с числата от 1 до 12. Малката стрелка {short}, а голямата сочи {points}."
    )


def said(hour: int, minute: int, locale: str) -> str:
    nxt = hour % 12 + 1
    if locale == "en":
        return {
            0: f"{EN_HOURS[hour].capitalize()} o'clock",
            15: f"Quarter past {EN_HOURS[hour]}",
            30: f"Half past {EN_HOURS[hour]}",
            45: f"Quarter to {EN_HOURS[nxt]}",
        }[minute]
    return {
        0: f"{BG_HOURS[hour].capitalize()} часа",
        15: f"{BG_HOURS[hour].capitalize()} и четвърт",
        30: f"{BG_HOURS[hour].capitalize()} и половина",
        45: f"{BG_HOURS[nxt].capitalize()} без четвърт",
    }[minute]


def why(hour: int, minute: int, locale: str) -> str:
    nxt = hour % 12 + 1
    digital = f"{hour}:{minute:02d}"
    if locale == "en":
        return {
            0: f"The long hand is on 12, so it is exactly {hour}. That is {digital}.",
            15: f"The long hand is on 3: a quarter of the way round, 15 minutes past {hour}. That is {digital}.",
            30: f"The long hand is on 6: halfway round, 30 minutes past {hour}. That is {digital}.",
            45: f"The long hand is on 9: 15 minutes are left until {nxt}. That is {digital}.",
        }[minute]
    return {
        0: f"Голямата стрелка е на 12, значи часът е точно {hour}. Това е {digital}.",
        15: f"Голямата стрелка е на 3: една четвърт от кръга, 15 минути след {hour}. Това е {digital}.",
        30: f"Голямата стрелка е на 6: половин кръг, 30 минути след {hour}. Това е {digital}.",
        45: f"Голямата стрелка е на 9: остават 15 минути до {nxt}. Това е {digital}.",
    }[minute]


# Familiar -> new -> recall -> transfer: o'clock, then half past, quarter past and quarter to,
# then a mixed recall. No time whose hands lie over each other (12:00, 8:45 and the like): the
# card teaches the short hand from the long one, so both must show.
TIMES = [
    (3, 0, "learn"),
    (9, 0, "learn"),
    (7, 0, "learn"),
    (6, 30, "learn"),
    (2, 30, "learn"),
    (4, 15, "learn"),
    (10, 15, "learn"),
    (10, 45, "learn"),
    (1, 45, "learn"),
    (5, 30, "recall"),
    (7, 15, "recall"),
    (11, 45, "recall"),
]

PROMPTS = {
    "learn": {
        "en": "What time is it? The short hand shows the hour; the long hand shows the minutes.",
        "bg": "Колко е часът? Малката стрелка показва часа, а голямата – минутите.",
    },
    "recall": {"en": "Your turn: what time is it?", "bg": "Сега ти: колко е часът?"},
}

CREDIT = {
    "creator": "Mantel",
    "license": "CC0-1.0",
    "attribution": "Original clock drawing, made in code with AI assistance.",
    "source": f"{REPOSITORY}/tell-the-time",
    "modified": False,
}


SOURCES = [
    {
        "supports": "Clock geometry: the minute hand turns 6 degrees a minute and the hour hand "
        "30 degrees an hour, so at half past it is halfway between two numbers. Computed, not "
        "copied: see clock() above.",
        "url": None,
    },
    {
        "supports": "English and Bulgarian ways of saying the time (o'clock / часа, half past / "
        "и половина, quarter past / и четвърт, quarter to / без четвърт): ordinary language, "
        "for a fluent reader to confirm.",
        "url": None,
    },
]


def main() -> None:
    pictures, items = {}, []
    for hour, minute, stage in TIMES:
        key = f"clock-{hour:02d}{minute:02d}"
        pictures[key] = clock(hour, minute)
        translations = {}
        for locale in ("en", "bg"):
            description = alt(hour, minute, locale)
            translations[locale] = {
                "prompt": face(PROMPTS[stage][locale], key, description),
                "reveal": face(
                    f"{said(hour, minute, locale)}. {why(hour, minute, locale)}", key, description
                ),
            }
        items.append(
            {
                "id": f"time-{hour:02d}{minute:02d}",
                "content_revision": 1,
                "translations": translations,
                "audio_cues": [],
            }
        )
    order = [item["id"] for item in items]
    timing = {"prompt_seconds": 8, "recall_seconds": 4, "reveal_seconds": 9, "dwell_seconds": 2}
    write_pack(
        HERE,
        header={
            "id": "mantel/tell-the-time",
            "version": "1.0.1",
            "publisher": "Mantel",
            "definition": {
                "schema_version": 2,
                "kind": "pack",
                "name": "Tell the Time",
                "description": (
                    "Read a clock face: o'clock, half past, quarter past and quarter to. Twelve "
                    "drawn clocks in English and Bulgarian, no sound."
                ),
                "locales": ["en", "bg"],
            },
        },
        pictures=pictures,
        credit={key: CREDIT for key in pictures},
        items=items,
        activities=[
            {
                "id": "clock-en",
                "name": "Tell the time",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "en",
                "loop": False,
                "timing": timing,
            },
            {
                "id": "clock-bg",
                "name": "Колко е часът",
                "kind": "reveal-sequence-v1",
                "item_ids": order,
                "locale": "bg",
                "loop": False,
                "timing": timing,
            },
        ],
        provenance={
            "pack": "mantel/tell-the-time",
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
