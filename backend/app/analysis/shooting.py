from dataclasses import dataclass
from enum import StrEnum

from app.domain import GameState, PossessionStatus, Vector2
from app.spatial import (
    EPSILON,
    closest_point_on_segment,
    direction,
    distance,
    orientation_degrees,
    required_velocity,
    travel_time,
)

# The top of a standard penalty arc is approximately 22 yards from the goal
# line: the penalty spot is 12 yards out and the arc has a 10-yard radius. The
# product requirement allows shots for another five yards beyond that area.
YARD_TO_CM = 91.44
MAXIMUM_SHOT_DISTANCE_YARDS = 22 + 5
MAXIMUM_SHOT_DISTANCE_CM = MAXIMUM_SHOT_DISTANCE_YARDS * YARD_TO_CM


@dataclass(frozen=True, slots=True)
class ShotPolicy:
    """Range, ball-speed, and geometric constraints for shot candidates."""
    ball_speed_cm_per_second: float = 2400
    defender_speed_cm_per_second: float = 500
    maximum_shot_distance_cm: float = MAXIMUM_SHOT_DISTANCE_CM
    interception_margin_seconds: float = 0.1
    goal_mouth_side_target_fraction: float = 0.15

    def __post_init__(self) -> None:
        if min(
            self.ball_speed_cm_per_second,
            self.defender_speed_cm_per_second,
            self.maximum_shot_distance_cm,
        ) <= 0:
            raise ValueError("Shot speeds and maximum distance must be positive")
        if self.interception_margin_seconds < 0:
            raise ValueError("Shot interception margin cannot be negative")
        if not 0 < self.goal_mouth_side_target_fraction < 0.5:
            raise ValueError(
                "Goal-mouth side target fraction must be between zero and one half"
            )


class ShotIssueCode(StrEnum):
    """Stable reasons a shot candidate cannot be attempted."""
    SHOOTER_DOES_NOT_CONTROL_BALL = "shooter_does_not_control_ball"
    SHOT_OUT_OF_RANGE = "shot_out_of_range"
    SHOT_CAN_BE_INTERCEPTED = "shot_can_be_intercepted"


@dataclass(frozen=True, slots=True)
class ShotIssue:
    code: ShotIssueCode
    message: str


@dataclass(frozen=True, slots=True)
class ShotAnalysis:
    player_id: str
    team_id: str
    goal_id: str
    goal_space_id: str
    start: Vector2
    destination: Vector2
    distance_cm: float
    duration_seconds: float
    ball_speed_cm_per_second: float
    ball_velocity: Vector2
    shot_direction: Vector2
    orientation_degrees: float
    nearest_defender_id: str | None
    interception_margin_seconds: float | None
    feasible: bool
    issues: tuple[ShotIssue, ...]


def analyze_shot(
    state: GameState,
    player_id: str,
    policy: ShotPolicy = ShotPolicy(),
    destination: Vector2 | None = None,
) -> ShotAnalysis:
    player = state.players_by_id[player_id]
    team = state.teams_by_id[player.team_id]
    goal = state.goals_by_id[team.attacking_goal_id]
    destination = destination or goal.center
    shot_distance = distance(state.ball.position, destination)
    duration = travel_time(
        state.ball.position,
        destination,
        policy.ball_speed_cm_per_second,
    )
    issues: list[ShotIssue] = []
    if (
        state.possession.status != PossessionStatus.CONTROLLED
        or state.possession.player_id != player_id
    ):
        issues.append(
            ShotIssue(
                ShotIssueCode.SHOOTER_DOES_NOT_CONTROL_BALL,
                f"Player {player_id} does not control the ball",
            )
        )
    if shot_distance > policy.maximum_shot_distance_cm + EPSILON:
        issues.append(
            ShotIssue(
                ShotIssueCode.SHOT_OUT_OF_RANGE,
                (
                    "The attacking goal is more than five yards beyond the "
                    "top of the penalty arc"
                ),
            )
        )

    threats = []
    for defender in state.players_by_id.values():
        if defender.team_id == player.team_id:
            continue
        point = closest_point_on_segment(
            defender.position,
            state.ball.position,
            destination,
        )
        ball_arrival = distance(state.ball.position, point) / policy.ball_speed_cm_per_second
        defender_arrival = travel_time(
            defender.position,
            point,
            policy.defender_speed_cm_per_second
            * defender.speed_category.multiplier,
        )
        threats.append(
            (
                defender_arrival - ball_arrival,
                defender.id,
            )
        )
    nearest_threat = min(threats, default=None)
    interception_margin = nearest_threat[0] if nearest_threat else None
    if (
        interception_margin is not None
        and interception_margin <= policy.interception_margin_seconds
    ):
        issues.append(
            ShotIssue(
                ShotIssueCode.SHOT_CAN_BE_INTERCEPTED,
                f"Defender {nearest_threat[1]} can intercept the shot",
            )
        )

    return ShotAnalysis(
        player_id=player.id,
        team_id=player.team_id,
        goal_id=goal.id,
        goal_space_id=f"GoalSpace-{player.team_id}",
        start=state.ball.position,
        destination=destination,
        distance_cm=shot_distance,
        duration_seconds=duration,
        ball_speed_cm_per_second=policy.ball_speed_cm_per_second,
        ball_velocity=(
            Vector2(0, 0)
            if duration <= EPSILON
            else required_velocity(state.ball.position, destination, duration)
        ),
        shot_direction=direction(state.ball.position, destination),
        orientation_degrees=orientation_degrees(state.ball.position, destination),
        nearest_defender_id=nearest_threat[1] if nearest_threat else None,
        interception_margin_seconds=interception_margin,
        feasible=not issues,
        issues=tuple(issues),
    )


def goal_mouth_targets(
    state: GameState,
    player_id: str,
    policy: ShotPolicy = ShotPolicy(),
) -> tuple[Vector2, Vector2, Vector2]:
    """Return center and two inset post-side targets in top-down field space."""
    player = state.players_by_id[player_id]
    team = state.teams_by_id[player.team_id]
    goal = state.goals_by_id[team.attacking_goal_id]
    goal_width = goal.top_right.y - goal.bottom_left.y
    inset = goal_width * policy.goal_mouth_side_target_fraction
    # TODO: Add elevated upper/lower corner choices if the simulation gains a
    # vertical ball axis. These targets only vary across the 2D goal mouth.
    return (
        goal.center,
        Vector2(goal.center.x, goal.bottom_left.y + inset),
        Vector2(goal.center.x, goal.top_right.y - inset),
    )


def analyze_all_shots(
    state: GameState,
    player_id: str,
    policy: ShotPolicy = ShotPolicy(),
) -> tuple[ShotAnalysis, ...]:
    return tuple(
        analyze_shot(state, player_id, policy, destination)
        for destination in goal_mouth_targets(state, player_id, policy)
    )
