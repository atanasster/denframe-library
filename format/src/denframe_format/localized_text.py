"""A definition's optional words in other languages (D33): name, mood and description by locale.

A definition's own `name` is its words in its author's language; `localized` adds the same three
fields in others (the base mood and description are the catalog entry's), each optional, so a
host shows the page's language where the author wrote it and falls back to the base strings
field by field. The words are plain text, bounded like the catalog's own (a name as long as the
definition's, a mood of 60, a description of 240): no control, bidirectional embedding, override
or isolate characters (right-to-left letters are fine), and never blank: a field needs one
character that is neither whitespace nor a format character (zero-width spaces, joiners and
marks alone are blank).

Locale keys are a small, canonical BCP 47 subset -- a lowercase two- or three-letter language,
an optional title-case script and an optional uppercase region or three-digit area
(`bg`, `pt-BR`, `zh-Hant-TW`, `es-419`) -- so the same language cannot appear twice under two
spellings. At least one locale and at most 16: an empty map says nothing, so it is refused
rather than requiring the token for no words.

A definition that carries `localized` requires `localized-text-v1`. Hosts read definitions
strictly, so an older host refuses the field whatever its manifest says; the token is what lets
the online catalog tell it *Needs a newer Denframe* before anything is downloaded. It is a host
token: the words are the Library's, never sent to a screen.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated, Any, Final, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from .capabilities import LOCALIZED_TEXT_CAPABILITY
from .encoding import forbidden_text_character

__all__ = [
    "LOCALIZED_TEXT_CAPABILITY",
    "Localized",
    "LocalizedText",
    "localized_words",
    "readable_words",
]

LOCALIZED_FIELDS: Final[tuple[str, ...]] = ("name", "mood", "description")
#: Canonical spelling only: `bg`, `pt-BR`, `zh-Hant-TW`, `es-419`.
LOCALE_PATTERN: Final[str] = r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$"
MAX_LOCALES: Final[int] = 16
# Words need one visible character: whitespace and format characters (Unicode `Cf`: zero-width
# spaces and joiners, bidi marks, soft hyphens) alone are blank. The same class in the schema
# (`generate-format-validators.mjs` spells `\s` as `\p{White_Space}` for the browser).
_WORDS = r"[^\s\p{Cf}]"
LocaleTag = Annotated[str, StringConstraints(pattern=LOCALE_PATTERN, max_length=16)]
LocalizedName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=_WORDS)]
LocalizedMood = Annotated[str, StringConstraints(min_length=1, max_length=60, pattern=_WORDS)]
LocalizedDescription = Annotated[
    str, StringConstraints(min_length=1, max_length=240, pattern=_WORDS)
]


def visible(text: str) -> bool:
    """Whether a string has a character that is neither whitespace nor a format character."""
    return any(not char.isspace() and unicodedata.category(char) != "Cf" for char in text)


class LocalizedText(BaseModel):
    """One language's words; each field optional, at least one present."""

    # `minProperties` so a plain JSON Schema reader refuses `{}` as the model does.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})
    name: LocalizedName | None = None
    mood: LocalizedMood | None = None
    description: LocalizedDescription | None = None

    @field_validator(*LOCALIZED_FIELDS)
    @classmethod
    def plain(cls, value: str | None) -> str | None:
        # The archive's JSON layer refuses these already; a catalog source is held to the same.
        if value is None:
            return value
        if any(forbidden_text_character(char) for char in value):
            raise ValueError("Localized text contains control or bidi formatting characters")
        if not visible(value):
            raise ValueError("Localized text needs a visible character")
        return value

    @model_validator(mode="after")
    def some_words(self) -> Self:
        if all(getattr(self, field) is None for field in LOCALIZED_FIELDS):
            raise ValueError("A localized entry needs a name, mood or description")
        return self

    @model_serializer(mode="wrap")
    def omit_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {key: value for key, value in handler(self).items() if value is not None}


# `additionalProperties: false` so a JSON Schema reader refuses a key outside the pattern too.
Localized = Annotated[
    dict[LocaleTag, LocalizedText],
    Field(min_length=1, max_length=MAX_LOCALES, json_schema_extra={"additionalProperties": False}),
]


def localized_words(localized: dict[str, LocalizedText] | None) -> dict[str, dict[str, str]]:
    """The words as plain dictionaries by locale (absent fields left out)."""
    return {locale: text.model_dump(mode="json") for locale, text in (localized or {}).items()}


_FIELD_TYPES: Final[dict[str, TypeAdapter[str]]] = {
    "name": TypeAdapter(LocalizedName),
    "mood": TypeAdapter(LocalizedMood),
    "description": TypeAdapter(LocalizedDescription),
}
_LOCALE_TYPE: Final[TypeAdapter[str]] = TypeAdapter(LocaleTag)


def _readable(field: str, value: object) -> str | None:
    try:
        text = _FIELD_TYPES[field].validate_python(value, strict=True)
        return LocalizedText.plain(text)
    except (ValidationError, ValueError):
        return None


def readable_words(raw: object) -> dict[str, dict[str, str]]:
    """The words a reader keeps from an untrusted mapping (a catalog entry's `localized`): the
    format's own rules, applied field by field rather than refusing the whole -- canonical
    locales, at most `MAX_LOCALES`, each field kept only when it is valid words."""
    if not isinstance(raw, dict):
        return {}
    kept: dict[str, dict[str, str]] = {}
    for locale, words in list(raw.items())[:MAX_LOCALES]:
        try:
            _LOCALE_TYPE.validate_python(locale, strict=True)
        except ValidationError:
            continue
        if not isinstance(words, dict):
            continue
        fields = {
            field: text
            for field in LOCALIZED_FIELDS
            if (text := _readable(field, words.get(field))) is not None
        }
        if fields:
            kept[locale] = fields
    return kept
