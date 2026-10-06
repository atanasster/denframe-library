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
    # An art collection installed into the host's gallery (art backgrounds plan, D2). Receivers
    # only ever see resolved gallery windows, never the pack, so the token is the host's alone.
    "gallery-pack-v1": "host",
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


#: The most works one art collection holds.
MAX_GALLERY_WORKS = 200

#: The URI of a gallery's only licence, CC0: public domain dedication (D6.1).
CC0_URI = "https://creativecommons.org/publicdomain/zero/1.0/"

HexColour = Annotated[str, StringConstraints(pattern=r"^#[0-9a-f]{6}$")]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$", max_length=1000)]
Instant = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
        max_length=40,
    ),
]
OptionalText = Annotated[str, StringConstraints(max_length=240)] | None
JpegPath = Annotated[str, StringConstraints(pattern=r"^assets/[a-f0-9]{64}\.jpg$")]
WebpPath = Annotated[str, StringConstraints(pattern=r"^assets/[a-f0-9]{64}\.webp$")]


class GalleryCredit(PackCredit):
    license: Literal["CC0-1.0"]


class GalleryResource(PackResource):
    """A gallery's file: a work's JPEG or a WebP thumbnail or strip, dedicated to the public
    domain (D6.1)."""

    media_type: Literal["image/jpeg", "image/webp"]
    credit: GalleryCredit


class GalleryPresentation(PackModel):
    """How the collection is shown by default; a household changes it on its Artwork page."""

    fit: Literal["fit", "fill", "smart"] = "fit"
    mat_style: Literal["full_bleed", "modern", "museum", "shadow_box"] = "museum"
    placard_seconds: int = Field(default=12, ge=5, le=120)
    cadence_seconds: int = Field(default=45, ge=15, le=86_400)


class GalleryPlacard(PackModel):
    title: DisplayText
    creator: DisplayText
    date: ShortText
    medium: OptionalText = None
    dimensions: OptionalText = None
    institution: ShortText
    canonical_url: HttpsUrl


class GalleryEvidence(PackModel):
    """What the provider answered when the work was curated: the field, its value and when."""

    provider_field: ShortText
    provider_value: bool | ShortText
    image_url: HttpsUrl
    observed_at: Instant
    image_field: ShortText | None = None
    uuid: ShortText | None = None


class GalleryRights(PackModel):
    license: Literal["CC0-1.0"] = "CC0-1.0"
    uri: Literal["https://creativecommons.org/publicdomain/zero/1.0/"] = CC0_URI
    evidence: GalleryEvidence


class GalleryWork(PackModel):
    id: ItemId
    image: JpegPath
    thumbnail: WebpPath
    alt_text: DisplayText
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    orientation: Literal["landscape", "portrait"]
    focal_x: float = Field(default=0.5, ge=0, le=1)
    focal_y: float = Field(default=0.5, ge=0, le=1)
    mean_colour: HexColour
    placard: GalleryPlacard
    rights: GalleryRights

    @model_validator(mode="after")
    def faces_its_way(self) -> Self:
        if (self.height > self.width) != (self.orientation == "portrait"):
            raise ValueError("A work's orientation must match its size")
        return self


class GalleryDefinition(PackModel):
    """An art collection (art backgrounds plan, D2): works with placards and CC0 rights evidence,
    no locales and no activities. The host installs it into its gallery, never into a card."""

    model_config = ConfigDict(
        json_schema_extra={
            "if": {"properties": {"shape": {"const": "landscape"}}},
            "then": {
                "properties": {
                    "works": {"items": {"properties": {"orientation": {"const": "landscape"}}}}
                }
            },
            "else": {
                "properties": {
                    "works": {"items": {"properties": {"orientation": {"const": "portrait"}}}}
                }
            },
        }
    )

    schema_version: Literal[2] = 2
    kind: Literal["gallery"] = "gallery"
    name: ShortText
    description: DisplayText
    shape: Literal["landscape", "portrait"]
    presentation: GalleryPresentation = Field(default_factory=GalleryPresentation)
    strip: WebpPath
    resources: list[GalleryResource] = Field(min_length=3, max_length=MAX_PACK_FILES - 2)
    works: list[GalleryWork] = Field(min_length=1, max_length=MAX_GALLERY_WORKS)

    @model_validator(mode="after")
    def references(self) -> Self:
        paths = [r.path for r in self.resources]
        if len(set(paths)) != len(paths) or len({w.id for w in self.works}) != len(self.works):
            raise ValueError("Duplicate gallery identity")
        resources = {r.path: r for r in self.resources}
        used = {self.strip}
        if resources.get(self.strip) is None or resources[self.strip].media_type != "image/webp":
            raise ValueError("The strip must be a WebP resource")
        for work in self.works:
            image, thumbnail = resources.get(work.image), resources.get(work.thumbnail)
            if image is None or image.media_type != "image/jpeg":
                raise ValueError("A work's image must be a JPEG resource")
            if thumbnail is None or thumbnail.media_type != "image/webp":
                raise ValueError("A work's thumbnail must be a WebP resource")
            if work.orientation != self.shape:
                raise ValueError("Every work must face the collection's shape")
            used.update((work.image, work.thumbnail))
        if used != set(resources):
            raise ValueError("Unreferenced gallery content")
        return self


AnyPackDefinition = PackDefinition | GalleryDefinition

#: The capabilities a pack's manifest requires, by the definition it carries.
PACK_KIND_CAPABILITIES: dict[str, tuple[str, str]] = {
    "pack": ("pack-format-v2", "reveal-sequence-v1"),
    "gallery": ("pack-format-v2", "gallery-pack-v1"),
}


def parse_pack_definition(value: object) -> AnyPackDefinition:
    """A pack definition by its kind: an activity pack, or an art collection."""
    if isinstance(value, dict) and value.get("kind") == "gallery":
        return GalleryDefinition.model_validate(value)
    return PackDefinition.model_validate(value)


class PackManifest(PackModel):
    format: Literal["denframepack"] = "denframepack"
    schema_version: Literal[2] = 2
    id: PackId
    version: ReleaseVersion
    publisher: ShortText
    definition_sha256: Digest
    entrypoint: Literal["definition.json"] = "definition.json"
    required_capabilities: list[
        Literal["pack-format-v2", "reveal-sequence-v1", "gallery-pack-v1"]
    ] = Field(
        default_factory=lambda: ["pack-format-v2", "reveal-sequence-v1"],
        min_length=2,
        max_length=2,
        json_schema_extra={"uniqueItems": True, "contains": {"const": "pack-format-v2"}},
    )

    @model_validator(mode="after")
    def capabilities(self) -> Self:
        allowed = [set(pair) for pair in PACK_KIND_CAPABILITIES.values()]
        if set(self.required_capabilities) not in allowed:
            raise ValueError("Pack manifest requires format and activity or gallery capabilities")
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
    "gallery-definition": GalleryDefinition,
    "manifest": PackManifest,
    "card-settings": CardBlockSettings,
    "audio-policy": PackAudioPolicy,
}
