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
    """Direction in which progress toward a team's opponent goal is measured."""
    POSITIVE_X = "positive_x"
    NEGATIVE_X = "negative_x"


class PossessionStatus(StrEnum):
    """Mutually exclusive result of possession analysis for one snapshot."""
    UNRESOLVED = "unresolved"
    CONTROLLED = "controlled"
    LOOSE = "loose"
    CONTESTED = "contested"


class PlayerSpeedCategory(StrEnum):
    """UI-selectable multiplier applied to movement speeds, not tactical priority."""
    BASELINE = "BASELINE"
    FAST = "FAST"
    SUPER_FAST = "SUPER_FAST"

    @property
    def multiplier(self) -> float:
        return {
            PlayerSpeedCategory.BASELINE: 1.0,
            PlayerSpeedCategory.FAST: 1.20,
            # SUPER_FAST is 30% above FAST: 1.20 * 1.30 = 1.56.
            PlayerSpeedCategory.SUPER_FAST: 1.56,
        }[self]


class TargetZoneShape(StrEnum):
    """Geometry supported by both submitted and computed tactical zones."""
    CIRCULAR = "circular"
    RECTANGULAR = "rectangular"


class TargetZoneSource(StrEnum):
    """Provenance used to distinguish coach input from engine-derived zones."""
    USER_DEFINED = "user_defined"
    ATTACKING_GOAL = "attacking_goal"
    DYNAMIC = "dynamic"


@dataclass(frozen=True, slots=True)
class FieldState:
    """Immutable field dimensions; length is X and width is Y, in `unit`."""
    field_type: FieldType
    length: float
    width: float
    unit: str


@dataclass(frozen=True, slots=True)
class GoalState:
    """Normalized goal geometry derived from the submitted four-point polygon."""
    id: str
    name: str
    side: GoalSide
    coordinates: tuple[Vector2, Vector2, Vector2, Vector2]
    center: Vector2
    bottom_left: Vector2
    top_right: Vector2


@dataclass(frozen=True, slots=True)
class TeamState:
    """A team with resolved defended/attacking goals and attack direction."""
    id: str
    name: str
    color: str
    defended_goal_id: str
    attacking_goal_id: str
    attacking_direction: AttackingDirection


@dataclass(frozen=True, slots=True)
class PlayerState:
    """One player's physical snapshot. Position is centimeters, facing is degrees."""
    id: str
    name: str
    number: int
    team_id: str
    position: Vector2
    orientation: float
    velocity: Vector2
    speed_category: PlayerSpeedCategory = PlayerSpeedCategory.BASELINE
    # Optional coach-facing label; `name` remains the stable internal name.
    profile_name: str | None = None


@dataclass(frozen=True, slots=True)
class BallState:
    """Ball snapshot with scalar direction/speed and derived velocity vector."""
    position: Vector2
    direction: float
    speed: float
    velocity: Vector2


@dataclass(frozen=True, slots=True)
class TargetZoneState:
    """A bounded space that may be coach-defined, goal-derived, or dynamic."""
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
    """Controller/team when controlled, or contestant IDs when ambiguous."""
    status: PossessionStatus
    player_id: str | None
    team_id: str | None
    contesting_player_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GameState:
    """Complete immutable world snapshot consumed and produced by simulation.

    `scored_goal_id` and `scoring_team_id` form the terminal scoring marker and
    should either both be absent or both describe the same completed shot.
    """
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
