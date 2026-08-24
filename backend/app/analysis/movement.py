from dataclasses import dataclass
from enum import StrEnum

from app.domain import AttackingDirection, GameState, PossessionStatus, Vector2
from app.spatial import (
    EPSILON,
    UnknownPlayerError,
    distance,
    direction,
    is_inside_field,
    nearest_point_in_zone,
    orientation_degrees,
    turn_duration_seconds,
    required_speed,
    required_velocity,
    travel_time,
)
from app.analysis.target_zones import UnknownTargetZoneError
from app.analysis.target_points import tactical_target_points


class InvalidMovementPolicyError(ValueError):
    """Raised when movement speeds or limits are invalid."""


@dataclass(frozen=True, slots=True)
class MovementPolicy:
    """Physical movement limits in centimeters, seconds, and degrees."""
    move_speed_cm_per_second: float = 400
    slow_run_speed_cm_per_second: float = 400
    regular_pace_multiplier: float = 1.5
    sprint_pace_multiplier: float = 1.5
    dribble_to_run_speed_ratio: float = 0.70
    maximum_duration_seconds: float = 30
    turning_speed_degrees_per_second: float = 180

    def __post_init__(self) -> None:
        if self.move_speed_cm_per_second <= 0:
            raise InvalidMovementPolicyError("Move speed must be positive")
        if self.slow_run_speed_cm_per_second <= 0:
            raise InvalidMovementPolicyError("Slow run speed must be positive")
        if self.regular_pace_multiplier <= 0 or self.sprint_pace_multiplier <= 0:
            raise InvalidMovementPolicyError("Pace multipliers must be positive")
        if not 0 < self.dribble_to_run_speed_ratio <= 1:
            raise InvalidMovementPolicyError("Dribble speed ratio must be in (0, 1]")
        if self.maximum_duration_seconds <= 0:
            raise InvalidMovementPolicyError("Maximum duration must be positive")
        if self.turning_speed_degrees_per_second <= 0:
            raise InvalidMovementPolicyError("Turning speed must be positive")


class MovementType(StrEnum):
    """Movement families with different permitted speeds and ball ownership."""
    MOVE = "MOVE"
    RUN = "RUN"
    MOVE_WITH_BALL = "MOVE_WITH_BALL"


class MovementPace(StrEnum):
    """Effort selected per action, independent of intrinsic player capability."""
    SLOW = "SLOW"
    REGULAR = "REGULAR"
    SPRINT = "SPRINT"


class DribbleDirection(StrEnum):
    """Relative target directions sampled when generating dribble candidates."""
    STRAIGHT = "STRAIGHT"
    CUT_LEFT = "CUT_LEFT"
    CUT_RIGHT = "CUT_RIGHT"


class MovementIssueCode(StrEnum):
    """Stable reasons a proposed movement candidate is infeasible."""
    DESTINATION_OUTSIDE_FIELD = "destination_outside_field"
    INVALID_DURATION = "invalid_duration"
    MAXIMUM_DURATION_EXCEEDED = "maximum_duration_exceeded"
    REQUIRED_SPEED_EXCEEDS_LIMIT = "required_speed_exceeds_limit"
    PLAYER_DOES_NOT_CONTROL_BALL = "player_does_not_control_ball"
    POSSESSION_UNRESOLVED = "possession_unresolved"
    POSSESSION_CONTESTED = "possession_contested"
    BALL_IS_LOOSE = "ball_is_loose"


@dataclass(frozen=True, slots=True)
class MovementIssue:
    code: MovementIssueCode
    message: str


@dataclass(frozen=True, slots=True)
class MovementAnalysis:
    player_id: str
    movement_type: MovementType
    pace: MovementPace
    start: Vector2
    destination: Vector2
    target_zone_id: str | None
    distance_cm: float
    movement_direction: Vector2
    orientation_degrees: float
    allowed_speed_cm_per_second: float
    required_speed_cm_per_second: float
    turn_angle_degrees: float
    turn_duration_seconds: float
    travel_duration_seconds: float
    duration_seconds: float
    velocity: Vector2
    feasible: bool
    issues: tuple[MovementIssue, ...]
    arrival_player_position: Vector2
    arrival_ball_position: Vector2
    dribble_direction: DribbleDirection | None = None


def _allowed_speed(
    movement_type: MovementType,
    pace: MovementPace,
    policy: MovementPolicy,
) -> float:
    if movement_type == MovementType.MOVE:
        return policy.move_speed_cm_per_second
    regular = policy.slow_run_speed_cm_per_second * policy.regular_pace_multiplier
    run_speed = {
        MovementPace.SLOW: policy.slow_run_speed_cm_per_second,
        MovementPace.REGULAR: regular,
        MovementPace.SPRINT: regular * policy.sprint_pace_multiplier,
    }[pace]
    return (
        run_speed
        if movement_type == MovementType.RUN
        else run_speed * policy.dribble_to_run_speed_ratio
    )


def _possession_issues(
    state: GameState,
    player_id: str,
    movement_type: MovementType,
) -> list[MovementIssue]:
    if movement_type != MovementType.MOVE_WITH_BALL:
        return []
    possession = state.possession
    if possession.status == PossessionStatus.UNRESOLVED:
        return [
            MovementIssue(
                MovementIssueCode.POSSESSION_UNRESOLVED,
                "Possession must be resolved before moving with the ball",
            )
        ]
    if possession.status == PossessionStatus.CONTESTED:
        return [
            MovementIssue(
                MovementIssueCode.POSSESSION_CONTESTED,
                "A player cannot move with a contested ball",
            )
        ]
    if possession.status == PossessionStatus.LOOSE:
        return [
            MovementIssue(
                MovementIssueCode.BALL_IS_LOOSE,
                "A player cannot move with a loose ball",
            )
        ]
    if possession.player_id != player_id:
        return [
            MovementIssue(
                MovementIssueCode.PLAYER_DOES_NOT_CONTROL_BALL,
                f"Player {player_id} does not control the ball",
            )
        ]
    return []


def analyze_movement_to_position(
    state: GameState,
    player_id: str,
    movement_type: MovementType,
    destination: Vector2,
    requested_duration_seconds: float | None = None,
    policy: MovementPolicy = MovementPolicy(),
    target_zone_id: str | None = None,
    dribble_direction: DribbleDirection | None = None,
    pace: MovementPace = MovementPace.REGULAR,
) -> MovementAnalysis:
    """Evaluate one possible movement without mutating or selecting a path.

    TODO: Account for turn time only after player orientation becomes a reliable
    editor or tracking input. The output orientation is still calculated for
    animation and future state transitions.
    """
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")

    issues = _possession_issues(state, player_id, movement_type)
    allowed_speed = (
        _allowed_speed(movement_type, pace, policy) * player.speed_category.multiplier
    )
    delta_distance = distance(player.position, destination)
    target_orientation = orientation_degrees(player.position, destination)
    orientation_delta = abs((target_orientation - player.orientation) % 360)
    # Keep reporting the geometric angle even while its physical time cost is
    # disabled; this preserves diagnostics for re-enabling turn time later.
    turn_angle = min(orientation_delta, 360 - orientation_delta)
    turn_duration = (
        turn_duration_seconds(
            player.orientation,
            target_orientation,
            policy.turning_speed_degrees_per_second,
        )
        if delta_distance > EPSILON
        else 0
    )
    if not is_inside_field(destination, state.field):
        issues.append(
            MovementIssue(
                MovementIssueCode.DESTINATION_OUTSIDE_FIELD,
                "Movement destination is outside the field",
            )
        )

    if requested_duration_seconds is not None and requested_duration_seconds <= 0:
        issues.append(
            MovementIssue(
                MovementIssueCode.INVALID_DURATION,
                "Requested duration must be greater than zero",
            )
        )
        duration = 0
        travel_duration = 0
        turn_duration = 0
        movement_required_speed = 0
        velocity = Vector2(0, 0)
    elif delta_distance <= EPSILON:
        travel_duration = requested_duration_seconds or 0
        duration = travel_duration
        movement_required_speed = 0
        velocity = Vector2(0, 0)
    elif requested_duration_seconds is None:
        travel_duration = travel_time(player.position, destination, allowed_speed)
        duration = travel_duration + turn_duration
        movement_required_speed = allowed_speed
        velocity = required_velocity(player.position, destination, travel_duration)
    else:
        travel_duration = requested_duration_seconds
        duration = travel_duration + turn_duration
        movement_required_speed = required_speed(
            player.position,
            destination,
            travel_duration,
        )
        velocity = required_velocity(player.position, destination, travel_duration)
        if movement_required_speed > allowed_speed + EPSILON:
            issues.append(
                MovementIssue(
                    MovementIssueCode.REQUIRED_SPEED_EXCEEDS_LIMIT,
                    "Requested arrival requires a speed above the movement limit",
                )
            )

    if duration > policy.maximum_duration_seconds:
        issues.append(
            MovementIssue(
                MovementIssueCode.MAXIMUM_DURATION_EXCEEDED,
                "Movement duration exceeds the configured maximum",
            )
        )

    ball_arrival = (
        destination
        if movement_type == MovementType.MOVE_WITH_BALL and not issues
        else state.ball.position
    )
    return MovementAnalysis(
        player_id=player.id,
        movement_type=movement_type,
        pace=pace,
        start=player.position,
        destination=destination,
        target_zone_id=target_zone_id,
        distance_cm=delta_distance,
        movement_direction=direction(player.position, destination),
        orientation_degrees=target_orientation,
        allowed_speed_cm_per_second=allowed_speed,
        required_speed_cm_per_second=movement_required_speed,
        turn_angle_degrees=turn_angle,
        turn_duration_seconds=turn_duration,
        travel_duration_seconds=travel_duration,
        duration_seconds=duration,
        velocity=velocity,
        feasible=not issues,
        issues=tuple(issues),
        arrival_player_position=destination,
        arrival_ball_position=ball_arrival,
        dribble_direction=dribble_direction,
    )


def analyze_movement_to_zone(
    state: GameState,
    player_id: str,
    movement_type: MovementType,
    zone_id: str,
    requested_duration_seconds: float | None = None,
    policy: MovementPolicy = MovementPolicy(),
) -> MovementAnalysis:
    zone = state.target_zones_by_id.get(zone_id)
    if zone is None:
        raise UnknownTargetZoneError(f"Unknown target zone: {zone_id}")
    if zone.ball_only:
        raise UnknownTargetZoneError(
            f"Target zone {zone_id} is reserved for the ball"
        )
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")
    destination = nearest_point_in_zone(zone, player.position)
    return analyze_movement_to_position(
        state,
        player_id,
        movement_type,
        destination,
        requested_duration_seconds,
        policy,
        target_zone_id=zone_id,
    )


def analyze_player_zone_movements(
    state: GameState,
    player_id: str,
    movement_types: tuple[MovementType, ...] = (
        MovementType.MOVE,
        MovementType.RUN,
        MovementType.MOVE_WITH_BALL,
    ),
    policy: MovementPolicy = MovementPolicy(),
) -> tuple[MovementAnalysis, ...]:
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")
    return tuple(
        analyze_movement_to_position(
            state,
            player_id,
            movement_type,
            destination,
            policy=policy,
            target_zone_id=zone_id,
        )
        for zone_id in sorted(state.target_zones_by_id)
        if not state.target_zones_by_id[zone_id].ball_only
        and state.target_zones_by_id[zone_id].attacking_team_id
        in {None, player.team_id}
        for destination in tactical_target_points(
            state,
            state.target_zones_by_id[zone_id],
            player.team_id,
            player.position,
        )
        for movement_type in movement_types
    )


def analyze_short_dribble_movements(
    state: GameState,
    player_id: str,
    durations_seconds: tuple[float, ...] = (1.5, 3.0),
    cut_lateral_fraction: float = 0.55,
    policy: MovementPolicy = MovementPolicy(),
) -> tuple[MovementAnalysis, ...]:
    """Generate short straight and diagonal dribble options.

    Orientation is intentionally deferred. Left and right are currently field-
    relative lateral directions, while forward follows the team's attack axis.
    """
    player = state.players_by_id.get(player_id)
    if player is None:
        raise UnknownPlayerError(f"Unknown player: {player_id}")
    team = state.teams_by_id[player.team_id]
    attacking_goal = state.goals_by_id[team.attacking_goal_id]
    goal_mouth_x = (
        attacking_goal.bottom_left.x
        if team.attacking_direction == AttackingDirection.POSITIVE_X
        else attacking_goal.top_right.x
    )
    forward_sign = (
        1 if team.attacking_direction == AttackingDirection.POSITIVE_X else -1
    )
    directions = (
        (DribbleDirection.STRAIGHT, 0.0),
        (DribbleDirection.CUT_LEFT, -cut_lateral_fraction),
        (DribbleDirection.CUT_RIGHT, cut_lateral_fraction),
    )
    analyses: list[MovementAnalysis] = []
    for duration in durations_seconds:
        for pace in MovementPace:
            travel_distance = (
                _allowed_speed(MovementType.MOVE_WITH_BALL, pace, policy)
                * player.speed_category.multiplier
                * duration
            )
            for variant, lateral_fraction in directions:
                lateral_distance = travel_distance * lateral_fraction
                forward_distance = (
                    travel_distance
                    if variant == DribbleDirection.STRAIGHT
                    else (travel_distance**2 - lateral_distance**2) ** 0.5
                )
                destination = Vector2(
                    (
                        min(player.position.x + forward_distance, goal_mouth_x)
                        if forward_sign > 0
                        else max(player.position.x - forward_distance, goal_mouth_x)
                    ),
                    player.position.y + lateral_distance,
                )
                analyses.append(
                    analyze_movement_to_position(
                        state,
                        player_id,
                        MovementType.MOVE_WITH_BALL,
                        destination,
                        requested_duration_seconds=duration,
                        policy=policy,
                        dribble_direction=variant,
                        pace=pace,
                    )
                )
    return tuple(analyses)
