from enum import StrEnum

from pydantic import BaseModel, Field as PydanticField

from app.models.ball import Ball
from app.models.goal import Goal
from app.models.open_space import OpenSpace
from app.models.player import Player
from app.models.team import Team


class FieldType(StrEnum):
    FIVE_V_FIVE = "5v5"
    SEVEN_V_SEVEN = "7v7"
    NINE_V_NINE = "9v9"
    ELEVEN_V_ELEVEN = "11v11"


class Field(BaseModel):
    name: str = PydanticField(min_length=1)
    field_type: FieldType
    ball: Ball
    goals: tuple[Goal, Goal]
    teams: tuple[Team, Team]
    players: list[Player] = PydanticField(default_factory=list)
    open_spaces: list[OpenSpace] = PydanticField(default_factory=list)
