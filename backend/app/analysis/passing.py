from dataclasses import dataclass
from enum import StrEnum

from app.analysis.target_zones import UnknownTargetZoneError
from app.analysis.target_points import tactical_target_points
from app.domain import GameState, PossessionStatus, Vector2, is_goalkeeper
from app.spatial import (
    EPSILON,
    UnknownPlayerError,
    closest_point_on_segment,
    direction,
    distance,
    distance_to_segment,
    is_inside_field,
    nearest_point_in_zone,
    orientation_degrees,
    required_speed,
    required_velocity,
    travel_time,
)


class InvalidPassPolicyError(ValueError):
    """Raised when pass-analysis speeds or thresholds are invalid."""


@dataclass(frozen=True, slots=True)
class PassPolicy:
    """Ball speed, timing, pressure, and interception tolerances for passes."""
    ball_speed_cm_per_second: float = 1800
    maximum_ball_speed_cm_per_second: float = 3000
    player_speed_cm_per_second: float = 650
    lane_clearance_cm: float = 150
    interception_margin_seconds: float = 0.15
    # How long a receiver may run before the pass must begin.
    receiver_arrival_tolerance_seconds: float = 5
    # Maximum raw preparation gap before considering overlap with prior play.
    maximum_ball_carrier_hold_seconds: float = 5
    maximum_duration_seconds: float = 10

    def __post_init__(self) -> None:
        if self.ball_speed_cm_per_second <= 0:
            raise InvalidPassPolicyError("Ball speed must be positive")
        if self.maximum_ball_speed_cm_per_second <= 0:
            raise InvalidPassPolicyError("Maximum ball speed must be positive")
        if self.ball_speed_cm_per_second > self.maximum_ball_speed_cm_per_second:
            raise InvalidPassPolicyError(
                "Default ball speed cannot exceed maximum ball speed"
            )
        if self.player_speed_cm_per_second <= 0:
            raise InvalidPassPolicyError("Player speed must be positive")
        if self.lane_clearance_cm < 0:
            raise InvalidPassPolicyError("Lane clearance cannot be negative")
        if self.interception_margin_seconds < 0:
            raise InvalidPassPolicyError("Interception margin cannot be negative")
        if self.receiver_arrival_tolerance_seconds < 0:
            raise InvalidPassPolicyError(
                "Receiver-arrival tolerance cannot be negative"
            )
        if self.maximum_ball_carrier_hold_seconds < 0:
            raise InvalidPassPolicyError(
                "Maximum ball-carrier hold time cannot be negative"
            )
        if self.maximum_duration_seconds <= 0:
            raise InvalidPassPolicyError("Maximum duration must be positive")


class PassType(StrEnum):
    """Direct-to-player versus into-space pass semantics."""
    PASS_TO_PLAYER = "PASS_TO_PLAYER"
    PASS_TO_SPACE = "PASS_TO_SPACE"


class PassIssueCode(StrEnum):
    """Stable reasons a pass analysis is infeasible."""
    PASSER_DOES_NOT_CONTROL_BALL = "passer_does_not_control_ball"
    POSSESSION_UNRESOLVED = "possession_unresolved"
    POSSESSION_CONTESTED = "possession_contested"
    BALL_IS_LOOSE = "ball_is_loose"
    RECEIVER_IS_PASSER = "receiver_is_passer"
    RECEIVER_IS_OPPONENT = "receiver_is_opponent"
    DESTINATION_OUTSIDE_FIELD = "destination_outside_field"
    INVALID_DURATION = "invalid_duration"
    MAXIMUM_DURATION_EXCEEDED = "maximum_duration_exceeded"
    REQUIRED_BALL_SPEED_EXCEEDS_LIMIT = "required_ball_speed_exceeds_limit"
    BLOCKED_PASSING_LANE = "blocked_passing_lane"
    INTERCEPTION_RISK = "interception_risk"
    RECEIVER_ARRIVES_TOO_LATE = "receiver_arrives_too_late"
    EXCESSIVE_BALL_CARRIER_HOLD = "excessive_ball_carrier_hold"


@dataclass(frozen=True, slots=True)
class PassIssue:
    code: PassIssueCode
    message: str


@dataclass(frozen=True, slots=True)
class DefenderInterception:
    defender_id: str
    interception_point: Vector2
    lane_clearance_cm: float
    ball_arrival_time_seconds: float
    defender_arrival_time_seconds: float
    can_intercept: bool


@dataclass(frozen=True, slots=True)
class PassAnalysis:
    pass_type: PassType
    passer_id: str
    receiver_id: str
    target_zone_id: str | None
    start: Vector2
    destination: Vector2
    distance_cm: float
    pass_direction: Vector2
    orientation_degrees: float
    ball_speed_cm_per_second: float
    duration_seconds: float
    ball_velocity: Vector2
    receiver_distance_cm: float
    receiver_arrival_time_seconds: float
    ball_carrier_hold_time_seconds: float
    nearest_defender_interception: DefenderInterception | None
    feasible: bool
    issues: tuple[PassIssue, ...]
    arrival_ball_position: Vector2
    expected_possession_player_id: str | None


def _possession_issues(state: GameState, passer_id: str) -> list[PassIssue]:
    possession = state.possession
    if possession.status == PossessionStatus.UNRESOLVED:
        return [PassIssue(PassIssueCode.POSSESSION_UNRESOLVED, "Possession is unresolved")]
    if possession.status == PossessionStatus.CONTESTED:
        return [PassIssue(PassIssueCode.POSSESSION_CONTESTED, "Possession is contested")]
    if possession.status == PossessionStatus.LOOSE:
        return [PassIssue(PassIssueCode.BALL_IS_LOOSE, "The ball is loose")]
    if possession.player_id != passer_id:
        return [
            PassIssue(
                PassIssueCode.PASSER_DOES_NOT_CONTROL_BALL,
                f"Player {passer_id} does not control the ball",
            )
        ]
    return []


def _nearest_interception(
    state: GameState,
    passer_team_id: str,
    start: Vector2,
    destination: Vector2,
    ball_speed: float,
    policy: PassPolicy,
) -> DefenderInterception | None:
    candidates: list[DefenderInterception] = []
    for defender in state.players_by_id.values():
        if defender.team_id == passer_team_id:
            continue
        point = closest_point_on_segment(defender.position, start, destination)
        clearance = distance_to_segment(defender.position, start, destination)
        ball_arrival = distance(start, point) / ball_speed if ball_speed > EPSILON else 0
        defender_arrival = travel_time(
            defender.position,
            point,
            policy.player_speed_cm_per_second
            * defender.speed_category.multiplier,
        )
        candidates.append(
            DefenderInterception(
                defender_id=defender.id,
                interception_point=point,
                lane_clearance_cm=clearance,
                ball_arrival_time_seconds=ball_arrival,
                defender_arrival_time_seconds=defender_arrival,
                can_intercept=(
                    defender_arrival
                    <= ball_arrival + policy.interception_margin_seconds
                ),
            )
        )
    return min(
        candidates,
        key=lambda candidate: (
            candidate.defender_arrival_time_seconds
            - candidate.ball_arrival_time_seconds,
            candidate.lane_clearance_cm,
            candidate.defender_id,
        ),
        default=None,
    )


def analyze_pass_to_position(
    state: GameState,
    passer_id: str,
    receiver_id: str,
    destination: Vector2,
    pass_type: PassType,
    requested_duration_seconds: float | None = None,
    policy: PassPolicy = PassPolicy(),
    target_zone_id: str | None = None,
) -> PassAnalysis:
    """Measure one pass proposal without selecting or applying it."""
    passer = state.players_by_id.get(passer_id)
    receiver = state.players_by_id.get(receiver_id)
    if passer is None:
        raise UnknownPlayerError(f"Unknown player: {passer_id}")
    if receiver is None:
        raise UnknownPlayerError(f"Unknown player: {receiver_id}")

    issues = _possession_issues(state, passer_id)
    if receiver.id == passer.id:
        issues.append(PassIssue(PassIssueCode.RECEIVER_IS_PASSER, "Passer and receiver must differ"))
    if receiver.team_id != passer.team_id:
        issues.append(PassIssue(PassIssueCode.RECEIVER_IS_OPPONENT, "Receiver must be a teammate"))
    if not is_inside_field(destination, state.field):
        issues.append(PassIssue(PassIssueCode.DESTINATION_OUTSIDE_FIELD, "Pass destination is outside the field"))

    pass_distance = distance(state.ball.position, destination)
    if requested_duration_seconds is not None and requested_duration_seconds <= 0:
        issues.append(PassIssue(PassIssueCode.INVALID_DURATION, "Requested duration must be greater than zero"))
        duration = 0
        ball_speed = 0
        velocity = Vector2(0, 0)
    elif pass_distance <= EPSILON:
        duration = requested_duration_seconds or 0
        ball_speed = 0
        velocity = Vector2(0, 0)
    elif requested_duration_seconds is None:
        ball_speed = policy.ball_speed_cm_per_second
        duration = travel_time(state.ball.position, destination, ball_speed)
        velocity = required_velocity(state.ball.position, destination, duration)
    else:
        duration = requested_duration_seconds
        ball_speed = required_speed(state.ball.position, destination, duration)
        velocity = required_velocity(state.ball.position, destination, duration)
        if ball_speed > policy.maximum_ball_speed_cm_per_second + EPSILON:
            issues.append(PassIssue(PassIssueCode.REQUIRED_BALL_SPEED_EXCEEDS_LIMIT, "Requested pass requires excessive ball speed"))

    if duration > policy.maximum_duration_seconds:
        issues.append(PassIssue(PassIssueCode.MAXIMUM_DURATION_EXCEEDED, "Pass duration exceeds the configured maximum"))

    receiver_distance = distance(receiver.position, destination)
    receiver_arrival = travel_time(
        receiver.position,
        destination,
        policy.player_speed_cm_per_second * receiver.speed_category.multiplier,
    )
    hold_time = (
        max(0, receiver_arrival - duration)
        if pass_type == PassType.PASS_TO_SPACE
        else 0
    )
    if (
        pass_type == PassType.PASS_TO_SPACE
        and receiver_arrival > duration + policy.receiver_arrival_tolerance_seconds
    ):
        issues.append(PassIssue(PassIssueCode.RECEIVER_ARRIVES_TOO_LATE, "Receiver cannot reach the space in time"))
    if (
        pass_type == PassType.PASS_TO_SPACE
        and hold_time > policy.maximum_ball_carrier_hold_seconds
    ):
        issues.append(
            PassIssue(
                PassIssueCode.EXCESSIVE_BALL_CARRIER_HOLD,
                "The passer would need to wait too long for the receiver",
            )
        )

    interception = (
        _nearest_interception(
            state,
            passer.team_id,
            state.ball.position,
            destination,
            ball_speed,
            policy,
        )
        if ball_speed > EPSILON
        else None
    )
    if interception is not None:
        if interception.lane_clearance_cm <= policy.lane_clearance_cm:
            issues.append(PassIssue(PassIssueCode.BLOCKED_PASSING_LANE, f"Defender {interception.defender_id} occupies the passing corridor"))
        if interception.can_intercept:
            issues.append(PassIssue(PassIssueCode.INTERCEPTION_RISK, f"Defender {interception.defender_id} can reach the passing lane"))

    feasible = not issues
    return PassAnalysis(
        pass_type=pass_type,
        passer_id=passer.id,
        receiver_id=receiver.id,
        target_zone_id=target_zone_id,
        start=state.ball.position,
        destination=destination,
        distance_cm=pass_distance,
        pass_direction=direction(state.ball.position, destination),
        orientation_degrees=orientation_degrees(state.ball.position, destination),
        ball_speed_cm_per_second=ball_speed,
        duration_seconds=duration,
        ball_velocity=velocity,
        receiver_distance_cm=receiver_distance,
        receiver_arrival_time_seconds=receiver_arrival,
        ball_carrier_hold_time_seconds=hold_time,
        nearest_defender_interception=interception,
        feasible=feasible,
        issues=tuple(issues),
        arrival_ball_position=destination,
        expected_possession_player_id=receiver.id if feasible else None,
    )


def analyze_pass_to_player(
    state: GameState,
    passer_id: str,
    receiver_id: str,
    requested_duration_seconds: float | None = None,
    policy: PassPolicy = PassPolicy(),
) -> PassAnalysis:
    receiver = state.players_by_id.get(receiver_id)
    if receiver is None:
        raise UnknownPlayerError(f"Unknown player: {receiver_id}")
    return analyze_pass_to_position(
        state,
        passer_id,
        receiver_id,
        receiver.position,
        PassType.PASS_TO_PLAYER,
        requested_duration_seconds,
        policy,
    )


def analyze_pass_to_space(
    state: GameState,
    passer_id: str,
    receiver_id: str,
    zone_id: str,
    requested_duration_seconds: float | None = None,
    policy: PassPolicy = PassPolicy(),
) -> PassAnalysis:
    zone = state.target_zones_by_id.get(zone_id)
    if zone is None:
        raise UnknownTargetZoneError(f"Unknown target zone: {zone_id}")
    if zone.ball_only:
        raise UnknownTargetZoneError(
            f"Target zone {zone_id} is reserved for shots"
        )
    receiver = state.players_by_id.get(receiver_id)
    if receiver is None:
        raise UnknownPlayerError(f"Unknown player: {receiver_id}")
    destination = nearest_point_in_zone(zone, receiver.position)
    return analyze_pass_to_position(
        state,
        passer_id,
        receiver_id,
        destination,
        PassType.PASS_TO_SPACE,
        requested_duration_seconds,
        policy,
        target_zone_id=zone_id,
    )


def analyze_all_passes(
    state: GameState,
    passer_id: str,
    policy: PassPolicy = PassPolicy(),
) -> tuple[PassAnalysis, ...]:
    passer = state.players_by_id.get(passer_id)
    if passer is None:
        raise UnknownPlayerError(f"Unknown player: {passer_id}")
    receivers = tuple(
        state.players_by_id[player_id]
        for player_id in sorted(state.player_ids_by_team[passer.team_id])
        if player_id != passer_id
    )
    direct = tuple(
        analyze_pass_to_player(state, passer_id, receiver.id, policy=policy)
        for receiver in receivers
    )
    space = tuple(
        analyze_pass_to_position(
            state,
            passer_id,
            receiver.id,
            destination,
            PassType.PASS_TO_SPACE,
            policy=policy,
            target_zone_id=zone_id,
        )
        for receiver in receivers
        if not is_goalkeeper(receiver)
        for zone_id in sorted(state.target_zones_by_id)
        if not state.target_zones_by_id[zone_id].ball_only
        and state.target_zones_by_id[zone_id].attacking_team_id
        in {None, passer.team_id}
        for destination in tactical_target_points(
            state,
            state.target_zones_by_id[zone_id],
            passer.team_id,
            receiver.position,
        )
    )
    return direct + space
