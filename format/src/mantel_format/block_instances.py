"""Validated internal instance bindings; not a public scene or package API."""

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from .vocabulary import Importance, Region

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Symbol = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10, pattern=r"^[A-Z][A-Z0-9]*(?:[.\-][A-Z0-9]+)*$"),
]


class InstanceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: Identifier
    output_id: Identifier | None = None


class SourceSlotHint(BaseModel):
    """Local authoring metadata; the receiver receives no instance bindings."""

    model_config = ConfigDict(extra="forbid")
    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
    required: bool = Field(default=True, strict=True)


class InstanceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: Annotated[list[InstanceSource], Field(max_length=12)] = Field(default_factory=list)
    symbols: Annotated[list[Symbol], Field(max_length=6)] | None = None
    source_slot: SourceSlotHint | None = None

    @model_serializer(mode="wrap")
    def omit_absent_slot(self, handler: SerializerFunctionWrapHandler) -> dict:
        data = handler(self)
        if self.source_slot is None:
            data.pop("source_slot", None)
        return data

    @model_validator(mode="after")
    def unique_inputs(self) -> "InstanceBinding":
        ids = [(source.provider_id, source.output_id) for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Instance sources must be unique")
        if self.symbols is not None and len(self.symbols) != len(set(self.symbols)):
            raise ValueError("Instance symbols must be unique")
        return self


class PortableInstancePlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: Region = "auto"
    importance: Importance = "normal"


class PortableBlockInstance(BaseModel):
    """Portable instance contract prototype, separate from local scene API records."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"$id": "urn:mantel:composition:block-instance:1"},
    )
    id: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")]
    type: Annotated[
        str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}/[a-z0-9][a-z0-9-]{0,63}$")
    ]
    config_version: int = Field(alias="configVersion", ge=1, le=2147483647, strict=True)
    enabled: bool = Field(strict=True)
    config: dict[str, JsonValue] = Field(max_length=64)
    query: dict[str, JsonValue] = Field(default_factory=dict, max_length=64)
    inputs: dict[
        Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")],
        Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")],
    ] = Field(
        default_factory=dict, max_length=12, json_schema_extra={"additionalProperties": False}
    )
    placement: PortableInstancePlacement = Field(default_factory=PortableInstancePlacement)
