"""Versioned, data-only pack contracts. These do not enable receiver capabilities."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_PACK_ARCHIVE = 128 * 1024 * 1024
MAX_PACK_EXPANDED = 256 * 1024 * 1024
MAX_PACK_FILES = 2048
MAX_PACK_DOCUMENTS = 4 * 1024 * 1024
MAX_PACK_ITEMS = 1000
MAX_PACK_INSTALLED = 2 * 1024 * 1024 * 1024
MAX_PACK_INSTALLED_FILES = 16_384
MAX_PACK_STAGING = 512 * 1024 * 1024
MAX_PACK_JOBS = 2
MAX_PACK_IMAGE = 8 * 1024 * 1024
MAX_PACK_AUDIO = 2 * 1024 * 1024
MAX_PACK_AUDIO_SECONDS = 30
MAX_PACK_COMPRESSION_RATIO = 100
MAX_PACK_WINDOW = 16 * 1024
PACK_PROJECTION_BUDGET = 12 * 1024
MAX_PACK_CHECKPOINT = 2 * 1024

PackId = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*$", max_length=100)
]
ReleaseVersion = Annotated[
    str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=30)
]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
Locale = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$", max_length=6)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
DisplayText = Annotated[str, StringConstraints(min_length=1, max_length=240, pattern=r"\S")]
ResourcePath = Annotated[
    str, StringConstraints(pattern=r"^assets/[a-f0-9]{64}\.(?:png|jpg|webp|mp3)$")
]
License = Literal["CC0-1.0", "CC-BY-4.0", "MIT"]

# Known contracts are not advertised until their implementation is available.
PACK_CAPABILITIES = {
    "pack-format-v2": "host",
    "reveal-sequence-v1": "host",
    "card-v1": "receiver",
    "pack-window-v1": "receiver",
    "pack-audio-v1": "receiver",
}
PackErrorCode = Literal[
    "invalid-format",
    "invalid-content",
    "unsupported-capability",
    "integrity-failed",
    "quota-exceeded",
    "cancelled",
    "expired",
    "conflict",
    "unauthorized",
    "unavailable",
]


class PackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PackCredit(PackModel):
    model_config = ConfigDict(
        json_schema_extra={
            "if": {"properties": {"license": {"enum": ["CC-BY-4.0", "MIT"]}}},
            "then": {
                "required": ["attribution"],
                "properties": {"attribution": {"pattern": r"\S"}},
            },
        }
    )
    creator: ShortText
    license: License
    attribution: Annotated[str, StringConstraints(max_length=500)] = ""
    source: Annotated[str, StringConstraints(max_length=500)] = ""
    modified: bool = False

    @model_validator(mode="after")
    def attribution_required(self) -> Self:
        if self.license in {"CC-BY-4.0", "MIT"} and not self.attribution.strip():
            raise ValueError("Attributed resources require their license/credit notice")
        return self


class PackResource(PackModel):
    model_config = ConfigDict(
        json_schema_extra={
            "if": {"properties": {"media_type": {"const": "audio/mpeg"}}},
            "then": {
                "required": ["duration_seconds"],
                "properties": {
                    "length": {"maximum": MAX_PACK_AUDIO},
                    "duration_seconds": {"type": "number"},
                    "path": {"pattern": r"\.mp3$"},
                },
            },
            "else": {"properties": {"duration_seconds": {"type": "null"}}},
            "allOf": [
                {
                    "if": {"properties": {"media_type": {"const": mime}}},
                    "then": {"properties": {"path": {"pattern": rf"\.{extension}$"}}},
                }
                for mime, extension in (
                    ("image/png", "png"),
                    ("image/jpeg", "jpg"),
                    ("image/webp", "webp"),
                )
            ],
        }
    )
    path: ResourcePath
    sha256: Digest
    length: int = Field(ge=1, le=MAX_PACK_IMAGE)
    media_type: Literal["image/png", "image/jpeg", "image/webp", "audio/mpeg"]
    duration_seconds: float | None = Field(default=None, ge=0.01, le=MAX_PACK_AUDIO_SECONDS)
    credit: PackCredit

    @model_validator(mode="after")
    def consistent(self) -> Self:
        extensions = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "audio/mpeg": "mp3",
        }
        if self.path != f"assets/{self.sha256}.{extensions[self.media_type]}":
            raise ValueError("Resource filename must match its digest and media type")
        audio = self.media_type == "audio/mpeg"
        if audio != (self.duration_seconds is not None):
            raise ValueError("Only audio requires a duration")
        if audio and self.length > MAX_PACK_AUDIO:
            raise ValueError("Audio resource exceeds limit")
        return self


class PackFace(PackModel):
    model_config = ConfigDict(
        json_schema_extra={
            "if": {"required": ["image"], "properties": {"image": {"type": "string"}}},
            "then": {"required": ["alt_text"], "properties": {"alt_text": {"type": "string"}}},
            "else": {"properties": {"alt_text": {"type": "null"}}},
        }
    )
    text: DisplayText
    image: ResourcePath | None = None
    alt_text: DisplayText | None = None

    @model_validator(mode="after")
    def image_alternative(self) -> Self:
        if (self.image is None) != (self.alt_text is None):
            raise ValueError("An image requires alternative text")
        return self


class PackTranslation(PackModel):
    prompt: PackFace
    reveal: PackFace


class PackAudioCue(PackModel):
    resource: ResourcePath
    locale: Locale
    phase: Literal["prompt", "reveal"]
    role: Literal["narration", "effect"]
    transcript: DisplayText


class PackItem(PackModel):
    id: ItemId
    content_revision: int = Field(ge=1, le=2_147_483_647)
    translations: dict[Locale, PackTranslation] = Field(
        min_length=1,
        max_length=8,
        json_schema_extra={
            "propertyNames": {"pattern": r"^[a-z]{2,3}(?:-[A-Z]{2})?$", "maxLength": 6},
            "additionalProperties": False,
        },
    )
    audio_cues: list[PackAudioCue] = Field(default_factory=list, max_length=4)


class PackTiming(PackModel):
    prompt_seconds: int = Field(default=3, ge=1, le=30)
    recall_seconds: int = Field(default=3, ge=0, le=30)
    reveal_seconds: int = Field(default=4, ge=1, le=30)
    dwell_seconds: int = Field(default=2, ge=1, le=30)


class PackActivity(PackModel):
    id: ItemId
    name: ShortText
    kind: Literal["reveal-sequence-v1"] = "reveal-sequence-v1"
    item_ids: list[ItemId] = Field(
        min_length=1, max_length=MAX_PACK_ITEMS, json_schema_extra={"uniqueItems": True}
    )
    locale: Locale
    loop: bool = False
    timing: PackTiming = Field(default_factory=PackTiming)

    @model_validator(mode="after")
    def unique_items(self) -> Self:
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("Activity contains duplicate items")
        return self


class PackDefinition(PackModel):
    schema_version: Literal[2] = 2
    kind: Literal["pack"] = "pack"
    name: ShortText
    description: DisplayText
    locales: list[Locale] = Field(
        min_length=1, max_length=8, json_schema_extra={"uniqueItems": True}
    )
    resources: list[PackResource] = Field(default_factory=list, max_length=MAX_PACK_FILES - 2)
    items: list[PackItem] = Field(min_length=1, max_length=MAX_PACK_ITEMS)
    activities: list[PackActivity] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def references(self) -> Self:
        for values in (
            self.locales,
            [r.path for r in self.resources],
            [i.id for i in self.items],
            [a.id for a in self.activities],
        ):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate pack identity")
        resources = {r.path: r for r in self.resources}
        items = {i.id: i for i in self.items}
        used = set()
        for item in self.items:
            if set(item.translations) != set(self.locales):
                raise ValueError("Each item must supply the declared locales")
            for translation in item.translations.values():
                for face in (translation.prompt, translation.reveal):
                    if face.image is not None:
                        resource = resources.get(face.image)
                        if resource is None or not resource.media_type.startswith("image/"):
                            raise ValueError("Image reference is missing or has wrong media type")
                        used.add(face.image)
            for cue in item.audio_cues:
                resource = resources.get(cue.resource)
                if (
                    cue.locale not in self.locales
                    or resource is None
                    or resource.media_type != "audio/mpeg"
                ):
                    raise ValueError("Audio reference or locale is invalid")
                used.add(cue.resource)
        referenced_items = set()
        for activity in self.activities:
            if activity.locale not in self.locales or len(set(activity.item_ids)) != len(
                activity.item_ids
            ):
                raise ValueError("Activity locale or item order is invalid")
            if not set(activity.item_ids) <= set(items):
                raise ValueError("Activity references missing items")
            referenced_items.update(activity.item_ids)
        if used != set(resources) or referenced_items != set(items):
            raise ValueError("Unreferenced pack content")
        return self


class PackManifest(PackModel):
    format: Literal["denframepack"] = "denframepack"
    schema_version: Literal[2] = 2
    id: PackId
    version: ReleaseVersion
    publisher: ShortText
    definition_sha256: Digest
    entrypoint: Literal["definition.json"] = "definition.json"
    required_capabilities: list[Literal["pack-format-v2", "reveal-sequence-v1"]] = Field(
        default_factory=lambda: ["pack-format-v2", "reveal-sequence-v1"],
        min_length=2,
        max_length=2,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def capabilities(self) -> Self:
        if set(self.required_capabilities) != {"pack-format-v2", "reveal-sequence-v1"}:
            raise ValueError("Pack manifest requires format and activity capabilities")
        return self


class PackContentRef(PackModel):
    id: PackId
    version: ReleaseVersion
    definition_sha256: Digest
    archive_sha256: Digest
    activity_id: ItemId


class CardBlockSettings(PackModel):
    schema_version: Literal[1] = 1
    content_ref: PackContentRef
    locale: Locale
    item_ids: list[ItemId] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PACK_ITEMS,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def unique_subset(self) -> Self:
        if self.item_ids is not None and len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("Card subset contains duplicate items")
        return self


class PackAudioPolicy(PackModel):
    schema_version: Literal[1] = 1
    enabled: bool = False
    volume: float = Field(default=0.5, ge=0, le=1)
    narration: bool = True
    effects: bool = True


PACK_SCHEMAS = {
    "definition": PackDefinition,
    "manifest": PackManifest,
    "card-settings": CardBlockSettings,
    "audio-policy": PackAudioPolicy,
}
