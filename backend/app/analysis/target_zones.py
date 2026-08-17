from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from app.domain import AttackingDirection, GameState, PlayerState, TargetZoneState, Vector2
from app.spatial import (
    distance_to_zone,
    forward_progress,
    nearest_point_in_zone,
    travel_time,
)


class InvalidTargetZonePolicyError(ValueError):
    """Raised when target-zone analysis thresholds are invalid."""


class UnknownTargetZoneError(ValueError):
    """Raised when a target-zone ID is absent from game state."""


class UnknownTeamError(ValueError):
    """Raised when a team ID is absent from game state."""


@dataclass(frozen=True, slots=True)
class TargetZonePolicy:
    """Geometric tolerances for deciding whether entities occupy target zones."""
    attacker_speed_cm_per_second: float = 650
    defender_speed_cm_per_second: float = 650
    reachable_horizon_seconds: float = 5
    contested_arrival_margin_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.attacker_speed_cm_per_second <= 0:
            raise InvalidTargetZonePolicyError("Attacker speed must be positive")
        if self.defender_speed_cm_per_second <= 0:
            raise InvalidTargetZonePolicyError("Defender speed must be positive")
        if self.reachable_horizon_seconds < 0:
            raise InvalidTargetZonePolicyError(
                "Reachable horizon cannot be negative"
            )
        if self.contested_arrival_margin_seconds < 0:
            raise InvalidTargetZonePolicyError(
                "Contested arrival margin cannot be negative"
            )


class TargetZoneStatus(StrEnum):
    """Whether a target zone is available, occupied, or otherwise contested."""
    AVAILABLE = "available"
    CONTESTED = "contested"
    DEFENDER_CONTROLLED = "defender_controlled"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class TargetZoneAnalysis:
    zone_id: str
    attacking_team_id: str
    status: TargetZoneStatus
    nearest_attacker_id: str | None
    nearest_attacker_distance_cm: float | None
    nearest_attacker_entry_point: Vector2 | None
    attacker_arrival_time_seconds: float | None
    nearest_defender_id: str | None
    nearest_defender_distance_cm: float | None
    nearest_defender_entry_point: Vector2 | None
    defender_arrival_time_seconds: float | None
    reachable_attacker_ids: tuple[str, ...]
    ball_distance_cm: float
    ball_entry_point: Vector2
    forward_progress_from_ball_cm: float
    normalized_forward_value: float
    arrival_advantage_seconds: float | None


def _players_for_team(state: GameState, team_id: str) -> tuple[PlayerState, ...]:
    return tuple(
        state.players_by_id[player_id]
        for player_id in state.player_ids_by_team[team_id]
    )


def _opponents_of_team(state: GameState, team_id: str) -> tuple[PlayerState, ...]:
    return tuple(
        player
        for player in state.players_by_id.values()
        if player.team_id != team_id
    )


def _ordered_by_zone_distance(
    players: tuple[PlayerState, ...],
    zone: TargetZoneState,
) -> tuple[PlayerState, ...]:
    return tuple(
        sorted(
            players,
            key=lambda player: (
                distance_to_zone(zone, player.position),
                player.id,
            ),
        )
    )


def _arrival(
    player: PlayerState | None,
    zone: TargetZoneState,
    speed: float,
) -> tuple[float | None, float | None, Vector2 | None]:
    if player is None:
        return None, None, None
    entry_point = nearest_point_in_zone(zone, player.position)
    distance = distance_to_zone(zone, player.position)
    return (
        distance,
        travel_time(
            player.position,
            entry_point,
            speed * player.speed_category.multiplier,
        ),
        entry_point,
    )


def _status(
    attacker_arrival: float | None,
    defender_arrival: float | None,
    policy: TargetZonePolicy,
) -> tuple[TargetZoneStatus, float | None]:
    if attacker_arrival is None:
        return TargetZoneStatus.UNREACHABLE, None
    if defender_arrival is None:
        return TargetZoneStatus.AVAILABLE, None

    advantage = defender_arrival - attacker_arrival
    if abs(advantage) <= policy.contested_arrival_margin_seconds:
        return TargetZoneStatus.CONTESTED, advantage
    if advantage > 0:
        return TargetZoneStatus.AVAILABLE, advantage
    return TargetZoneStatus.DEFENDER_CONTROLLED, advantage


def _normalized_forward_value(
    state: GameState,
    team_id: str,
    zone: TargetZoneState,
) -> float:
    team = state.teams_by_id[team_id]
    raw_value = (
        zone.center.x / state.field.length
        if team.attacking_direction == AttackingDirection.POSITIVE_X
        else (state.field.length - zone.center.x) / state.field.length
    )
    return min(1, max(0, raw_value))


def analyze_target_zone(
    state: GameState,
    zone_id: str,
    attacking_team_id: str,
    policy: TargetZonePolicy = TargetZonePolicy(),
) -> TargetZoneAnalysis:
    zone = state.target_zones_by_id.get(zone_id)
    if zone is None:
        raise UnknownTargetZoneError(f"Unknown target zone: {zone_id}")
    if attacking_team_id not in state.teams_by_id:
        raise UnknownTeamError(f"Unknown team: {attacking_team_id}")
    if (
        zone.attacking_team_id is not None
        and zone.attacking_team_id != attacking_team_id
    ):
        raise UnknownTargetZoneError(
            f"Target zone {zone_id} is not available to team {attacking_team_id}"
        )

    attackers = _ordered_by_zone_distance(
        _players_for_team(state, attacking_team_id),
        zone,
    )
    defenders = _ordered_by_zone_distance(
        _opponents_of_team(state, attacking_team_id),
        zone,
    )
    nearest_attacker = attackers[0] if attackers else None
    nearest_defender = defenders[0] if defenders else None
    attacker_distance, attacker_arrival, attacker_entry = _arrival(
        nearest_attacker,
        zone,
        policy.attacker_speed_cm_per_second,
    )
    defender_distance, defender_arrival, defender_entry = _arrival(
        nearest_defender,
        zone,
        policy.defender_speed_cm_per_second,
    )
    status, advantage = _status(attacker_arrival, defender_arrival, policy)
    reachable_attackers = tuple(
        player.id
        for player in attackers
        if travel_time(
            player.position,
            nearest_point_in_zone(zone, player.position),
            policy.attacker_speed_cm_per_second
            * player.speed_category.multiplier,
        )
        <= policy.reachable_horizon_seconds
    )
    ball_entry_point = nearest_point_in_zone(zone, state.ball.position)
    team = state.teams_by_id[attacking_team_id]

    return TargetZoneAnalysis(
        zone_id=zone.id,
        attacking_team_id=attacking_team_id,
        status=status,
        nearest_attacker_id=nearest_attacker.id if nearest_attacker else None,
        nearest_attacker_distance_cm=attacker_distance,
        nearest_attacker_entry_point=attacker_entry,
        attacker_arrival_time_seconds=attacker_arrival,
        nearest_defender_id=nearest_defender.id if nearest_defender else None,
        nearest_defender_distance_cm=defender_distance,
        nearest_defender_entry_point=defender_entry,
        defender_arrival_time_seconds=defender_arrival,
        reachable_attacker_ids=reachable_attackers,
        ball_distance_cm=distance_to_zone(zone, state.ball.position),
        ball_entry_point=ball_entry_point,
        forward_progress_from_ball_cm=forward_progress(
            team.attacking_direction,
            state.ball.position,
            zone.center,
        ),
        normalized_forward_value=_normalized_forward_value(
            state,
            attacking_team_id,
            zone,
        ),
        arrival_advantage_seconds=advantage,
    )


def analyze_all_target_zones(
    state: GameState,
    attacking_team_id: str,
    policy: TargetZonePolicy = TargetZonePolicy(),
) -> Mapping[str, TargetZoneAnalysis]:
    if attacking_team_id not in state.teams_by_id:
        raise UnknownTeamError(f"Unknown team: {attacking_team_id}")
    return MappingProxyType(
        {
            zone_id: analyze_target_zone(
                state,
                zone_id,
                attacking_team_id,
                policy,
            )
            for zone_id in sorted(state.target_zones_by_id)
            if state.target_zones_by_id[zone_id].attacking_team_id
            in {None, attacking_team_id}
        }
    )
