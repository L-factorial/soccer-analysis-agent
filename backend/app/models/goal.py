from enum import StrEnum

from pydantic import BaseModel

from app.models.position import Position


class GoalSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class Goal(BaseModel):
    id: str
    name: str
    side: GoalSide
    coordinates: tuple[Position, Position, Position, Position]
