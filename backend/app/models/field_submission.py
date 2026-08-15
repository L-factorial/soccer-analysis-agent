from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.field import FieldType
from app.models.goal import GoalSide
from app.models.position import Position


class Dimensions(BaseModel):
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    unit: Literal["cm"]


class SubmittedTeam(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    defended_goal_id: str = Field(alias="defendedGoalId", min_length=1)


class SubmittedGoal(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    side: GoalSide
    coordinates: tuple[Position, Position, Position, Position]


class SubmittedPlayer(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    number: int = Field(gt=0, le=99)
    team_id: str = Field(alias="teamId", min_length=1)
    position: Position
    orientation: float = Field(ge=0, lt=360)
    velocity: Position
    speed_category: Literal["BASELINE", "FAST", "SUPER_FAST"] = Field(
        default="BASELINE",
        alias="speedCategory",
    )


class SubmittedBall(BaseModel):
    position: Position
    direction: float = Field(ge=0, lt=360)
    speed: float = Field(ge=0)


class CircularSubmittedOpenSpace(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: Literal["circular"]
    center: Position
    radius: float = Field(gt=0)


class RectangularSubmittedOpenSpace(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: Literal["rectangular"]
    bottom_left: Position = Field(alias="bottomLeft")
    top_right: Position = Field(alias="topRight")


SubmittedOpenSpace = Annotated[
    CircularSubmittedOpenSpace | RectangularSubmittedOpenSpace,
    Field(discriminator="type"),
]


class SubmittedFieldConfiguration(BaseModel):
    label: str = Field(min_length=1)
    field_type: FieldType = Field(alias="fieldType")
    dimensions: Dimensions
    goal_dimensions: Dimensions = Field(alias="goalDimensions")
    teams: tuple[SubmittedTeam, SubmittedTeam]
    goals: tuple[SubmittedGoal, SubmittedGoal]
    players: list[SubmittedPlayer] = Field(default_factory=list)
    ball: SubmittedBall
    open_spaces: list[SubmittedOpenSpace] = Field(
        alias="openSpaces",
        default_factory=list,
    )

class FieldSubmission(BaseModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    tactical_instruction: str | None = Field(
        default=None,
        alias="tacticalInstruction",
        max_length=500,
    )
    field_configuration: SubmittedFieldConfiguration = Field(
        alias="fieldConfiguration"
    )
