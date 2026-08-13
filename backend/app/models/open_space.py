from enum import StrEnum
from typing import Self

from pydantic import BaseModel, model_validator

from app.models.position import Position


class OpenSpaceType(StrEnum):
    CIRCULAR = "circular"
    RECTANGULAR = "rectangular"


class OpenSpace(BaseModel):
    type: OpenSpaceType
    center: Position | None = None
    top_left: Position | None = None
    bottom_right: Position | None = None

    @model_validator(mode="after")
    def validate_coordinates(self) -> Self:
        if self.type == OpenSpaceType.CIRCULAR:
            if self.center is None:
                raise ValueError("A circular open space requires center coordinates")
            if self.top_left is not None or self.bottom_right is not None:
                raise ValueError(
                    "A circular open space cannot have rectangular coordinates"
                )
        elif self.top_left is None or self.bottom_right is None:
            raise ValueError(
                "A rectangular open space requires top-left and bottom-right coordinates"
            )
        elif self.center is not None:
            raise ValueError("A rectangular open space cannot have center coordinates")

        return self
