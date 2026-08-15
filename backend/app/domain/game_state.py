from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from app.models.field import FieldType
from app.models.goal import GoalSide


@dataclass(frozen=True, slots=True)
class Vector2:
    x: float
    y: float


class AttackingDirection(StrEnum):
    POSITIVE_X = "positive_x"
    NEGATIVE_X = "negative_x"


class PossessionStatus(StrEnum):
    UNRESOLVED = "unresolved"
    CONTROLLED = "controlled"
    LOOSE = "loose"
    CONTESTED = "contested"


class PlayerSpeedCategory(StrEnum):
    BASELINE = "BASELINE"
    FAST = "FAST"
    SUPER_FAST = "SUPER_FAST"

    @property
    def multiplier(self) -> float:
        return {
            PlayerSpeedCategory.BASELINE: 1.0,
            PlayerSpeedCategory.FAST: 1.15,
            PlayerSpeedCategory.SUPER_FAST: 1.20,
        }[self]


class TargetZoneShape(StrEnum):
    CIRCULAR = "circular"
    RECTANGULAR = "rectangular"


class TargetZoneSource(StrEnum):
    USER_DEFINED = "user_defined"
    ATTACKING_GOAL = "attacking_goal"
    DYNAMIC = "dynamic"


@dataclass(frozen=True, slots=True)
class FieldState:
    field_type: FieldType
    length: float
    width: float
    unit: str


@dataclass(frozen=True, slots=True)
class GoalState:
    id: str
    name: str
    side: GoalSide
    coordinates: tuple[Vector2, Vector2, Vector2, Vector2]
    center: Vector2
    bottom_left: Vector2
    top_right: Vector2


@dataclass(frozen=True, slots=True)
class TeamState:
    id: str
    name: str
    color: str
    defended_goal_id: str
    attacking_goal_id: str
    attacking_direction: AttackingDirection


@dataclass(frozen=True, slots=True)
class PlayerState:
    id: str
    name: str
    number: int
    team_id: str
    position: Vector2
    orientation: float
    velocity: Vector2
    speed_category: PlayerSpeedCategory = PlayerSpeedCategory.BASELINE


@dataclass(frozen=True, slots=True)
class BallState:
    position: Vector2
    direction: float
    speed: float
    velocity: Vector2


@dataclass(frozen=True, slots=True)
class TargetZoneState:
    id: str
    name: str
    shape: TargetZoneShape
    source: TargetZoneSource
    center: Vector2
    bottom_left: Vector2
    top_right: Vector2
    radius: float | None = None
    attacking_team_id: str | None = None
    ball_only: bool = False


@dataclass(frozen=True, slots=True)
class PossessionState:
    status: PossessionStatus
    player_id: str | None
    team_id: str | None
    contesting_player_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GameState:
    time_seconds: float
    field: FieldState
    teams_by_id: Mapping[str, TeamState]
    goals_by_id: Mapping[str, GoalState]
    players_by_id: Mapping[str, PlayerState]
    player_ids_by_team: Mapping[str, tuple[str, ...]]
    ball: BallState
    target_zones_by_id: Mapping[str, TargetZoneState]
    possession: PossessionState
    scored_goal_id: str | None = None
    scoring_team_id: str | None = None
