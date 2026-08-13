from typing import Annotated

from pydantic import BaseModel, Field

from app.models.position import Position

Direction = Annotated[float, Field(ge=0, lt=360)]


class Ball(BaseModel):
    position: Position
    direction: Direction
    speed: float = Field(ge=0)
