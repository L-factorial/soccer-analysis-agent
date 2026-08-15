from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from app.analysis.movement import (
    MovementAnalysis,
    MovementPolicy,
    MovementType,
    analyze_short_dribble_movements,
    analyze_player_zone_movements,
)
from app.analysis.passing import PassAnalysis, PassPolicy, analyze_all_passes
from app.analysis.shooting import ShotAnalysis, ShotPolicy, analyze_all_shots
from app.domain import GameState, PossessionStatus, Vector2, is_goalkeeper
from app.spatial import EPSILON, distance_to_goal, forward_progress


class ActionType(StrEnum):
    MOVE = "MOVE"
    RUN = "RUN"
    MOVE_WITH_BALL = "MOVE_WITH_BALL"
    PASS_TO_PLAYER = "PASS_TO_PLAYER"
    PASS_TO_SPACE = "PASS_TO_SPACE"
    SHOT = "SHOT"


@dataclass(frozen=True, slots=True)
class ActionMetrics:
    distance_cm: float
    duration_seconds: float
    forward_progress_cm: float
    goal_proximity_improvement_cm: float
    required_speed_cm_per_second: float
    lane_clearance_cm: float | None = None
    interception_time_margin_seconds: float | None = None
    receiver_arrival_time_seconds: float | None = None
    ball_travel_duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    id: str
    originating_state_fingerprint: str
    action_type: ActionType
    actor_id: str
    receiver_id: str | None
    target_zone_id: str | None
    start: Vector2
    destination: Vector2
    feasible: bool
    issue_codes: tuple[str, ...]
    issue_messages: tuple[str, ...]
    metrics: ActionMetrics
    source_analysis: MovementAnalysis | PassAnalysis | ShotAnalysis


@dataclass(frozen=True, slots=True)
class ActionCandidateSet:
    all: tuple[ActionCandidate, ...]
    feasible: tuple[ActionCandidate, ...]
    rejected: tuple[ActionCandidate, ...]


def game_state_fingerprint(state: GameState) -> str:
    """Return a stable identity for action-relevant immutable state."""
    players = tuple(
        (
            player.id,
            player.position.x,
            player.position.y,
            player.orientation,
            player.velocity.x,
            player.velocity.y,
            player.speed_category.value,
        )
        for player in sorted(state.players_by_id.values(), key=lambda item: item.id)
    )
    value = (
        state.time_seconds,
        players,
        (
            state.ball.position.x,
            state.ball.position.y,
            state.ball.direction,
            state.ball.speed,
            state.ball.velocity.x,
            state.ball.velocity.y,
        ),
        (
            state.possession.status.value,
            state.possession.player_id,
            state.possession.team_id,
            state.possession.contesting_player_ids,
        ),
        state.scored_goal_id,
        state.scoring_team_id,
    )
    return sha256(repr(value).encode("utf-8")).hexdigest()


def _goal_improvement(
    state: GameState,
    actor_id: str,
    start: Vector2,
    destination: Vector2,
) -> float:
    player = state.players_by_id[actor_id]
    team = state.teams_by_id[player.team_id]
    attacking_goal = state.goals_by_id[team.attacking_goal_id]
    return distance_to_goal(start, attacking_goal) - distance_to_goal(
        destination,
        attacking_goal,
    )


def movement_to_candidate(
    state: GameState,
    analysis: MovementAnalysis,
    candidate_id: str,
) -> ActionCandidate:
    player = state.players_by_id[analysis.player_id]
    attacking_direction = state.teams_by_id[player.team_id].attacking_direction
    return ActionCandidate(
        id=candidate_id,
        originating_state_fingerprint=game_state_fingerprint(state),
        action_type=ActionType(analysis.movement_type.value),
        actor_id=analysis.player_id,
        receiver_id=None,
        target_zone_id=analysis.target_zone_id,
        start=analysis.start,
        destination=analysis.destination,
        feasible=analysis.feasible,
        issue_codes=tuple(issue.code.value for issue in analysis.issues),
        issue_messages=tuple(issue.message for issue in analysis.issues),
        metrics=ActionMetrics(
            distance_cm=analysis.distance_cm,
            duration_seconds=analysis.duration_seconds,
            forward_progress_cm=forward_progress(
                attacking_direction,
                analysis.start,
                analysis.destination,
            ),
            goal_proximity_improvement_cm=_goal_improvement(
                state,
                analysis.player_id,
                analysis.start,
                analysis.destination,
            ),
            required_speed_cm_per_second=analysis.required_speed_cm_per_second,
        ),
        source_analysis=analysis,
    )


def pass_to_candidate(
    state: GameState,
    analysis: PassAnalysis,
    candidate_id: str,
) -> ActionCandidate:
    passer = state.players_by_id[analysis.passer_id]
    attacking_direction = state.teams_by_id[passer.team_id].attacking_direction
    interception = analysis.nearest_defender_interception
    return ActionCandidate(
        id=candidate_id,
        originating_state_fingerprint=game_state_fingerprint(state),
        action_type=ActionType(analysis.pass_type.value),
        actor_id=analysis.passer_id,
        receiver_id=analysis.receiver_id,
        target_zone_id=analysis.target_zone_id,
        start=analysis.start,
        destination=analysis.destination,
        feasible=analysis.feasible,
        issue_codes=tuple(issue.code.value for issue in analysis.issues),
        issue_messages=tuple(issue.message for issue in analysis.issues),
        metrics=ActionMetrics(
            distance_cm=analysis.distance_cm,
            duration_seconds=(
                max(
                    analysis.duration_seconds,
                    analysis.receiver_arrival_time_seconds,
                )
                if analysis.pass_type.value == "PASS_TO_SPACE"
                else analysis.duration_seconds
            ),
            forward_progress_cm=forward_progress(
                attacking_direction,
                analysis.start,
                analysis.destination,
            ),
            goal_proximity_improvement_cm=_goal_improvement(
                state,
                analysis.passer_id,
                analysis.start,
                analysis.destination,
            ),
            required_speed_cm_per_second=analysis.ball_speed_cm_per_second,
            lane_clearance_cm=(
                interception.lane_clearance_cm if interception else None
            ),
            interception_time_margin_seconds=(
                interception.defender_arrival_time_seconds
                - interception.ball_arrival_time_seconds
                if interception
                else None
            ),
            receiver_arrival_time_seconds=analysis.receiver_arrival_time_seconds,
            ball_travel_duration_seconds=analysis.duration_seconds,
        ),
        source_analysis=analysis,
    )


def shot_to_candidate(
    state: GameState,
    analysis: ShotAnalysis,
    candidate_id: str,
) -> ActionCandidate:
    return ActionCandidate(
        id=candidate_id,
        originating_state_fingerprint=game_state_fingerprint(state),
        action_type=ActionType.SHOT,
        actor_id=analysis.player_id,
        receiver_id=None,
        target_zone_id=analysis.goal_space_id,
        start=analysis.start,
        destination=analysis.destination,
        feasible=analysis.feasible,
        issue_codes=tuple(issue.code.value for issue in analysis.issues),
        issue_messages=tuple(issue.message for issue in analysis.issues),
        metrics=ActionMetrics(
            distance_cm=analysis.distance_cm,
            duration_seconds=analysis.duration_seconds,
            forward_progress_cm=forward_progress(
                state.teams_by_id[analysis.team_id].attacking_direction,
                analysis.start,
                analysis.destination,
            ),
            goal_proximity_improvement_cm=distance_to_goal(
                analysis.start,
                state.goals_by_id[analysis.goal_id],
            ),
            required_speed_cm_per_second=analysis.ball_speed_cm_per_second,
            interception_time_margin_seconds=analysis.interception_margin_seconds,
            ball_travel_duration_seconds=analysis.duration_seconds,
        ),
        source_analysis=analysis,
    )


def generate_action_candidates(
    state: GameState,
    movement_policy: MovementPolicy = MovementPolicy(),
    pass_policy: PassPolicy = PassPolicy(),
    shot_policy: ShotPolicy = ShotPolicy(),
) -> ActionCandidateSet:
    """Generate a stable, planner-facing view of current action options."""
    analyses: list[MovementAnalysis | PassAnalysis | ShotAnalysis] = []
    controller_id = (
        state.possession.player_id
        if state.possession.status == PossessionStatus.CONTROLLED
        else None
    )

    for player_id in sorted(state.players_by_id):
        player = state.players_by_id[player_id]
        movement_types = [MovementType.MOVE]
        if not is_goalkeeper(player):
            movement_types.append(MovementType.RUN)
        if player_id == controller_id and not is_goalkeeper(player):
            movement_types.append(MovementType.MOVE_WITH_BALL)
        analyses.extend(
            analyze_player_zone_movements(
                state,
                player_id,
                tuple(movement_types),
                movement_policy,
            )
        )

    if controller_id is not None:
        controller = state.players_by_id[controller_id]
        if not is_goalkeeper(controller):
            analyses.extend(
                analyze_short_dribble_movements(
                    state,
                    controller_id,
                    policy=movement_policy,
                )
            )
        analyses.extend(analyze_all_passes(state, controller_id, pass_policy))
        if not is_goalkeeper(controller):
            analyses.extend(
                shot
                for shot in analyze_all_shots(
                    state,
                    controller_id,
                    shot_policy,
                )
                if shot.distance_cm > EPSILON
            )

    analyses = [
        analysis for analysis in analyses if analysis.distance_cm > EPSILON
    ]

    candidates = tuple(
        movement_to_candidate(state, analysis, f"candidate-{index:04d}")
        if isinstance(analysis, MovementAnalysis)
        else (
            pass_to_candidate(state, analysis, f"candidate-{index:04d}")
            if isinstance(analysis, PassAnalysis)
            else shot_to_candidate(state, analysis, f"candidate-{index:04d}")
        )
        for index, analysis in enumerate(analyses, start=1)
    )
    return ActionCandidateSet(
        all=candidates,
        feasible=tuple(candidate for candidate in candidates if candidate.feasible),
        rejected=tuple(candidate for candidate in candidates if not candidate.feasible),
    )
