from typing import Annotated

from pydantic import BaseModel, Field

from app.models.position import Position

Direction = Annotated[float, Field(ge=0, lt=360)]


class Player(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    number: int = Field(gt=0, le=99)
    team_id: str = Field(min_length=1)
    position: Position
    orientation: Direction
