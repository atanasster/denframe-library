"""A dashboard's own choices for a provider-backed block.

They live in one reserved object, `DisplayBlockConfig.settings["overrides"]`, which no provider
payload and no portable setting may name (D1): the resolver lifts it before a block reaches the
wire, so nothing a source sends can clobber it and nothing in it can shadow a source. An absent
object or field means "what the source says" -- no inherit sentinel is ever stored (D2).

Two readings of the same models (D7): `clean_overrides` is the lenient one every read and write
of a stored scene goes through (a field that no longer validates is dropped, never fatal, so a
dashboard can always load), and `strict_overrides` is the one the scene API applies to what a
request actually changed, answering 422 with the field's reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from .vocabulary import CalendarView

OVERRIDES_KEY = "overrides"
#: A package whose blocks carry overrides says so: the host reads them at import (a receiver
#: never sees them), so this is a host-only token (`display_capabilities.HOST_ONLY_CAPABILITIES`)
#: and a host that predates overrides refuses the package with a reason rather than choking on
#: an unknown portable setting.
BLOCK_OVERRIDES_CAPABILITY = "block-overrides-v1"
#: What never travels in a package: which of *this* household's people a block filters to.
LOCAL_OVERRIDE_FIELDS = frozenset({"profile_ids"})

#: The caps the tasks and notes sources already hold (`tasks.MAX_VISIBLE_TASKS`,
#: `notes.MAX_VISIBLE_NOTES`); a dashboard only narrows within them. Spelled here rather than
#: imported because both modules import `app.models`, which imports this one.
MAX_VISIBLE_TASKS = 3
MAX_VISIBLE_NOTES = 4

ProfileId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProfileIds = Annotated[list[ProfileId], Field(min_length=1, max_length=20)]


class _Overrides(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeatherOverrides(_Overrides):
    unit_system: Literal["metric", "imperial"] | None = None
    # The two outlooks the weather ladder is measured for (`weatherLadder.ts`).
    forecast_days: Literal[3, 7] | None = None
    show_wear_guidance: bool | None = None
    show_air_quality: bool | None = None


#: The most stories a headlines block lists at once (its full form's six).
MAX_SHOWN_STORIES = 6
#: How often a headlines block moves on by a story: a whole number of the wall clock's
#: half-minute ticks, which is when a screen redraws it.
TakeTurnsSeconds = Literal[30, 60, 120]


class NewsOverrides(_Overrides):
    max_stories: Annotated[int, Field(ge=1, le=MAX_SHOWN_STORIES)] | None = None
    show_summary: bool | None = None
    show_pictures: bool | None = None
    take_turns_seconds: TakeTurnsSeconds | None = None


class _PeopleOverrides(_Overrides):
    # A filter after the source's own audience guard: it can hide, never reveal (D6).
    profile_ids: ProfileIds | None = None

    @field_validator("profile_ids")
    @classmethod
    def once_each(cls, value: list[str] | None) -> list[str] | None:
        # After each id is validated and stripped, so `" mia"` and `"mia"` are one person.
        if value is not None and len(value) != len(set(value)):
            raise ValueError("list each person once")
        return value


class TasksOverrides(_PeopleOverrides):
    max_visible: Annotated[int, Field(ge=1, le=MAX_VISIBLE_TASKS)] | None = None


class NotesOverrides(_PeopleOverrides):
    max_visible: Annotated[int, Field(ge=1, le=MAX_VISIBLE_NOTES)] | None = None


class CalendarOverrides(_Overrides):
    horizon_days: Annotated[int, Field(ge=1, le=90)] | None = None
    private_events: Literal["show", "title_redacted", "time_only", "hidden"] | None = None
    show_all_day: bool | None = None
    # The calendar's view choices (family calendar plan step 2; drawn from step 8 on). Absent
    # is the default -- for the view, the list every calendar drew before the views (`auto`
    # must be chosen, so no existing dashboard changes); following the time of day where the
    # dashboard's purpose turns it on (Home); and no lock -- so a package that leaves them
    # alone stays byte-identical to one written before they existed. The older portable
    # `settings.view` (`day` | `week`, `elements.SETTINGS`) is still accepted and read by
    # nothing: it never reached a screen, so it maps to that same absent list.
    view: CalendarView | None = None
    follow_time_of_day: bool | None = None
    view_lock: bool | None = None


#: A quote's name as the block prints it: an equity symbol (`AAPL`, `BRK.B`) or a currency pair
#: (`EUR/USD`); what `marketQuoteName` in `marketLadder.ts` compares against.
FocusSymbol = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=12,
        pattern=r"^[A-Z][A-Z0-9]*(?:[.\-][A-Z0-9]+)*(?:/[A-Z]{3})?$",
    ),
]


class MarketOverrides(_Overrides):
    #: The quote the block leads with -- its move is the vital row of the line and glance forms
    #: (legibility step 8); the first quote when unset or when the source no longer has it.
    focus_symbol: FocusSymbol | None = None


#: The one registry: the kinds a dashboard may override, and how. A kind that is not here
#: carries no overrides at all (the validator drops the object).
OVERRIDE_MODELS: Mapping[str, type[_Overrides]] = {
    "weather": WeatherOverrides,
    "news": NewsOverrides,
    "tasks": TasksOverrides,
    "notes": NotesOverrides,
    "calendar": CalendarOverrides,
    "market": MarketOverrides,
}

_KIND_LABELS = {
    "weather": "Weather",
    "news": "Headlines",
    "tasks": "Tasks",
    "notes": "Notes",
    "calendar": "Calendar",
    "market": "Markets",
}

#: Each field in the household's words, for a refusal's detail.
_FIELD_LABELS = {
    "unit_system": "temperature units",
    "forecast_days": "outlook",
    "show_wear_guidance": "clothing advice",
    "show_air_quality": "air quality",
    "max_stories": "number of stories",
    "show_summary": "summaries",
    "profile_ids": "people",
    "max_visible": "number shown",
    "horizon_days": "days ahead",
    "private_events": "private events",
    "show_all_day": "all-day events",
    "view": "view",
    "follow_time_of_day": "follow the time of day",
    "view_lock": "view lock",
    "focus_symbol": "lead quote",
}


def kind_label(kind: str) -> str:
    """A block kind as the household reads it ("Tasks", "Headlines")."""
    return _KIND_LABELS.get(kind, kind.title())


def _dump(model: type[_Overrides], value: Mapping[str, Any]) -> dict[str, Any]:
    return model.model_validate(value, strict=True).model_dump(mode="json", exclude_none=True)


def clean_overrides(kind: str, value: object) -> dict[str, Any] | None:
    """The valid part of a stored `overrides` object, or `None` when nothing valid is left.

    Field by field and strict (a string is not a number, `1` is not `True`): a field that does
    not validate, an unknown key, a `None`, a non-object value and a kind without overrides are
    all dropped rather than refused, because a stored dashboard must always load.
    """
    model = OVERRIDE_MODELS.get(kind)
    if model is None or not isinstance(value, Mapping):
        return None
    kept: dict[str, Any] = {}
    for key, item in value.items():
        if key not in model.model_fields or item is None:
            continue
        try:
            kept.update(_dump(model, {key: item}))
        except ValidationError:
            # A people list that doesn't validate whole keeps its valid ids, and one with none
            # left is kept empty -- a filter that matches no one, so unassigned items stay and
            # assigned ones hide -- rather than going, which would open the filter to everyone
            # on this read and every write after it (second implementation audit). A request
            # can't author `[]`: `strict_overrides` still refuses it.
            if key == "profile_ids":
                kept["profile_ids"] = _valid_people(item)[:20]
    return kept or None


def people_filter(value: object) -> frozenset[str] | None:
    """The people a tasks or notes block keeps (`profile_ids`), for its projector: `None` when
    the block chose no one (no filter), otherwise the valid ids of what it stored.

    Fail-closed where `clean_overrides` is lenient: a stored list that doesn't validate whole
    (a repeat, more than twenty, an overlong id, `[]`, not a list) keeps the ids that do rather
    than dropping the filter and showing everyone (found in the implementation audit). An empty
    result still filters: it matches no one, so unassigned items stay and assigned ones hide.
    """
    if not isinstance(value, Mapping) or value.get("profile_ids") is None:
        return None
    return frozenset(_valid_people(value["profile_ids"]))


def _valid_people(value: object) -> list[str]:
    """The valid person ids in a stored list, stripped, once each, in its order."""
    if not isinstance(value, list):
        return []
    ids = (item.strip() for item in value if isinstance(item, str))
    return list(dict.fromkeys(item for item in ids if 1 <= len(item) <= 100))


def strict_overrides(
    kind: str, value: object, *, where: str = "on this dashboard"
) -> dict[str, Any]:
    """`value` validated whole, for a request or a package that authored it; `ValueError` says
    which setting was refused, in the household's words, `where` naming what is being written
    (a dashboard, or a package being imported)."""
    model = OVERRIDE_MODELS.get(kind)
    label = kind_label(kind)
    if model is None:
        raise ValueError(f"{label} has no settings of its own on a dashboard")
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} {where}: its settings must be an object")
    try:
        return _dump(model, value)
    except ValidationError as exc:
        error = exc.errors()[0]
        field = str(error["loc"][0]) if error["loc"] else "settings"
        if error["type"] == "extra_forbidden":
            raise ValueError(f"{label} {where} has no setting called {field}") from exc
        reason = str(error["msg"]).removeprefix("Value error, ")
        name = _FIELD_LABELS.get(field, field)
        raise ValueError(f"{label} {where}: {name} -- {reason}") from exc


def portable_overrides(kind: str, value: object) -> dict[str, Any] | None:
    """A block's overrides as a package carries them: cleaned, less anything that names this
    household's own people; `None` when nothing portable is left."""
    cleaned = clean_overrides(kind, value) or {}
    portable = {key: item for key, item in cleaned.items() if key not in LOCAL_OVERRIDE_FIELDS}
    return portable or None
