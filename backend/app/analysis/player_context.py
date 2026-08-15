from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from app.domain import AttackingDirection, GameState, PossessionStatus
from app.spatial import (
    UnknownPlayerError,
    distance,
    distance_to_goal,
    nearest_opponent,
    nearest_teammate,
    opponents,
    players_sorted_by_distance,
    teammates,
)


class InvalidPressurePolicyError(ValueError):
    """Raised when player-context distance thresholds are invalid."""


@dataclass(frozen=True, slots=True)
class PressurePolicy:
    immediate_pressure_radius_cm: float = 150
    nearby_pressure_radius_cm: float = 400
    support_radius_cm: float = 600

    def __post_init__(self) -> None:
        if self.immediate_pressure_radius_cm < 0:
            raise InvalidPressurePolicyError(
                "Immediate-pressure radius cannot be negative"
            )
        if self.nearby_pressure_radius_cm < self.immediate_pressure_radius_cm:
            raise InvalidPressurePolicyError(
                "Nearby-pressure radius cannot be smaller than immediate radius"
            )
        if self.support_radius_cm < 0:
            raise InvalidPressurePolicyError("Support radius cannot be negative")


class PressureLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PossessionRole(StrEnum):
    BALL_HOLDER = "ball_holder"
    CONTESTING = "contesting"
    TEAM_IN_POSSESSION = "team_in_possession"
    OPPOSING_TEAM = "opposing_team"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class PlayerContext:
    player_id: str
    team_id: str
    distance_to_ball_cm: float
    possession_role: PossessionRole
    nearest_teammate_id: str | None
    nearest_teammate_distance_cm: float | None
    nearest_opponent_id: str | None
    nearest_opponent_distance_cm: float | None
    supporting_teammate_ids: tuple[str, ...]
    nearby_opponent_ids: tuple[str, ...]
    immediate_pressure_opponent_ids: tuple[str, ...]
    pressure_score: float
    pressure_level: PressureLevel
    distance_to_defended_goal_cm: float
    distance_to_attacking_goal_cm: float
    normalized_forward_position: float


def _possession_role(state: GameState, player_id: str, team_id: str) -> PossessionRole:
    possession = state.possession
    if possession.status == PossessionStatus.CONTROLLED:
        if possession.player_id == player_id:
            return PossessionRole.BALL_HOLDER
        if possession.team_id == team_id:
            return PossessionRole.TEAM_IN_POSSESSION
        return PossessionRole.OPPOSING_TEAM
    if (
        possession.status == PossessionStatus.CONTESTED
        and player_id in possession.contesting_player_ids
    ):
        return PossessionRole.CONTESTING
    return PossessionRole.NEUTRAL


def _pressure_level(
    immediate_count: int,
    nearby_count: int,
) -> PressureLevel:
    if immediate_count > 0:
        return PressureLevel.HIGH
    if nearby_count >= 2:
        return PressureLevel.MEDIUM
    if nearby_count == 1:
        return PressureLevel.LOW
    return PressureLevel.NONE


def _normalized_forward_position(state: GameState, team_id: str, x: float) -> float:
    team = state.teams_by_id[team_id]
    raw_position = (
        x / state.field.length
        if team.attacking_direction == AttackingDirection.POSITIVE_X
        else (state.field.length - x) / state.field.length
    )
    return min(1, max(0, raw_position))


def analyze_player_context(
    state: GameState,
    player_id: str,
    policy: PressurePolicy = PressurePolicy(),
) -> PlayerContext:
    """Calculate measurable local context without making tactical decisions.

    TODO: Include orientation-derived visibility or facing pressure only after
    orientation becomes a reliable editor or tracking input.
    """
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")

    nearest_team_player = nearest_teammate(state, player_id)
    nearest_other_player = nearest_opponent(state, player_id)
    ordered_teammates = players_sorted_by_distance(teammates(state, player_id), player.position)
    ordered_opponents = players_sorted_by_distance(opponents(state, player_id), player.position)
    supporting_players = tuple(
        candidate
        for candidate in ordered_teammates
        if distance(player.position, candidate.position) <= policy.support_radius_cm
    )
    nearby_opponents = tuple(
        candidate
        for candidate in ordered_opponents
        if distance(player.position, candidate.position)
        <= policy.nearby_pressure_radius_cm
    )
    immediate_opponents = tuple(
        candidate
        for candidate in nearby_opponents
        if distance(player.position, candidate.position)
        <= policy.immediate_pressure_radius_cm
    )
    nearest_opponent_distance = (
        distance(player.position, nearest_other_player.position)
        if nearest_other_player
        else None
    )
    pressure_score = (
        max(
            0,
            1 - nearest_opponent_distance / policy.nearby_pressure_radius_cm,
        )
        if nearest_opponent_distance is not None
        and policy.nearby_pressure_radius_cm > 0
        else 0
    )
    team = state.teams_by_id[player.team_id]

    return PlayerContext(
        player_id=player.id,
        team_id=player.team_id,
        distance_to_ball_cm=distance(player.position, state.ball.position),
        possession_role=_possession_role(state, player.id, player.team_id),
        nearest_teammate_id=(nearest_team_player.id if nearest_team_player else None),
        nearest_teammate_distance_cm=(
            distance(player.position, nearest_team_player.position)
            if nearest_team_player
            else None
        ),
        nearest_opponent_id=(nearest_other_player.id if nearest_other_player else None),
        nearest_opponent_distance_cm=nearest_opponent_distance,
        supporting_teammate_ids=tuple(candidate.id for candidate in supporting_players),
        nearby_opponent_ids=tuple(candidate.id for candidate in nearby_opponents),
        immediate_pressure_opponent_ids=tuple(
            candidate.id for candidate in immediate_opponents
        ),
        pressure_score=pressure_score,
        pressure_level=_pressure_level(
            len(immediate_opponents),
            len(nearby_opponents),
        ),
        distance_to_defended_goal_cm=distance_to_goal(
            player.position,
            state.goals_by_id[team.defended_goal_id],
        ),
        distance_to_attacking_goal_cm=distance_to_goal(
            player.position,
            state.goals_by_id[team.attacking_goal_id],
        ),
        normalized_forward_position=_normalized_forward_position(
            state,
            player.team_id,
            player.position.x,
        ),
    )


def analyze_all_players(
    state: GameState,
    policy: PressurePolicy = PressurePolicy(),
) -> Mapping[str, PlayerContext]:
    return MappingProxyType(
        {
            player_id: analyze_player_context(state, player_id, policy)
            for player_id in sorted(state.players_by_id)
        }
    )
