"""Portable layout purpose and bounded grid arrangements."""

from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_validator,
    model_serializer,
    model_validator,
)

from .composition import Placement, PortraitPlacement, _whole_number, validate_grid_placement_map

LayoutPurpose = Literal["glance", "gallery", "home", "media"]
InstanceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
CELL_FIELDS = ("col_start", "row_start", "col_span", "row_span")


class ArrangementCell(BaseModel):
    """A complete landscape cell; region and importance remain on the block's hint."""

    model_config = ConfigDict(extra="forbid")
    col_span: int = Field(ge=1, le=12, strict=True)
    row_span: int = Field(ge=1, le=6, strict=True)
    col_start: int = Field(ge=1, le=12, strict=True)
    row_start: int = Field(ge=1, le=6, strict=True)
    _columns: ClassVar[int] = 12
    _rows: ClassVar[int] = 6

    @field_validator(*CELL_FIELDS, mode="before")
    @classmethod
    def whole_number(cls, value: Any) -> Any:
        return _whole_number(value)

    @model_validator(mode="after")
    def fits(self) -> Self:
        if (
            self.col_start + self.col_span - 1 > self._columns
            or self.row_start + self.row_span - 1 > self._rows
        ):
            raise ValueError("Arrangement cell must fit within the grid")
        return self


class PortraitArrangementCell(ArrangementCell):
    """A complete cell on the transposed portrait grid."""

    col_span: int = Field(ge=1, le=6, strict=True)
    row_span: int = Field(ge=1, le=12, strict=True)
    col_start: int = Field(ge=1, le=6, strict=True)
    row_start: int = Field(ge=1, le=12, strict=True)
    _columns: ClassVar[int] = 6
    _rows: ClassVar[int] = 12


class LayoutArrangement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    landscape: dict[InstanceId, ArrangementCell] = Field(min_length=1, max_length=12)
    portrait: dict[InstanceId, PortraitArrangementCell] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="after")
    def valid_cells(self) -> Self:
        validate_grid_placement_map(
            {
                key: Placement.model_validate(cell.model_dump())
                for key, cell in self.landscape.items()
            },
            "landscape",
        )
        validate_grid_placement_map(
            {
                key: PortraitPlacement.model_validate(cell.model_dump())
                for key, cell in self.portrait.items()
            },
            "portrait",
        )
        return self

    @model_serializer(mode="wrap")
    def omit_empty_portrait(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if not self.portrait:
            data.pop("portrait", None)
        return data
