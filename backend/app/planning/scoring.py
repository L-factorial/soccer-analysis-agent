from dataclasses import dataclass
from enum import StrEnum

from app.analysis import ActionCandidate, PressureLevel, TargetZoneStatus
from app.domain import PossessionStatus
from app.planning.state_analysis import AnalyzedGameState, BranchExpansion


class InvalidScoringPolicyError(ValueError):
    """Raised when deterministic scoring weights are invalid."""


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    forward_progress_weight: float = 30
    goal_proximity_weight: float = 20
    target_space_weight: float = 10
    lane_safety_weight: float = 10
    backward_action_penalty: float = 10
    duration_penalty: float = 5
    possession_weight: float = 25
    controller_pressure_penalty: float = 15
    follow_up_options_weight: float = 10
    available_spaces_weight: float = 10
    goal_scored_reward: float = 1000
    duration_normalizer_seconds: float = 10
    lane_margin_normalizer_seconds: float = 2

    def __post_init__(self) -> None:
        weights = (
            self.forward_progress_weight,
            self.goal_proximity_weight,
            self.target_space_weight,
            self.lane_safety_weight,
            self.backward_action_penalty,
            self.duration_penalty,
            self.possession_weight,
            self.controller_pressure_penalty,
            self.follow_up_options_weight,
            self.available_spaces_weight,
            self.goal_scored_reward,
        )
        if any(weight < 0 for weight in weights):
            raise InvalidScoringPolicyError("Scoring weights cannot be negative")
        if self.duration_normalizer_seconds <= 0:
            raise InvalidScoringPolicyError(
                "Duration normalizer must be positive"
            )
        if self.lane_margin_normalizer_seconds <= 0:
            raise InvalidScoringPolicyError(
                "Lane-margin normalizer must be positive"
            )


class TacticalFlag(StrEnum):
    ADVANCES_TOWARD_GOAL = "advances_toward_goal"
    BACKWARD_ACTION = "backward_action"
    TARGETS_AVAILABLE_SPACE = "targets_available_space"
    TARGETS_CONTESTED_SPACE = "targets_contested_space"
    SAFE_PASSING_LANE = "safe_passing_lane"
    RETAINS_POSSESSION = "retains_possession"
    LOSES_POSSESSION = "loses_possession"
    CONTROLLER_UNDER_PRESSURE = "controller_under_pressure"
    CREATES_MANY_OPTIONS = "creates_many_options"


@dataclass(frozen=True, slots=True)
class ActionScoreBreakdown:
    forward_progress: float
    goal_proximity: float
    target_space: float
    lane_safety: float
    backward_penalty: float
    duration_penalty: float

    @property
    def total(self) -> float:
        return (
            self.forward_progress
            + self.goal_proximity
            + self.target_space
            + self.lane_safety
            + self.backward_penalty
            + self.duration_penalty
        )


@dataclass(frozen=True, slots=True)
class ScoredActionCandidate:
    candidate: ActionCandidate
    score: float
    breakdown: ActionScoreBreakdown
    flags: tuple[TacticalFlag, ...]


@dataclass(frozen=True, slots=True)
class StateScoreBreakdown:
    possession: float
    controller_pressure: float
    follow_up_options: float
    available_spaces: float
    goal_scored: float

    @property
    def total(self) -> float:
        return (
            self.possession
            + self.controller_pressure
            + self.follow_up_options
            + self.available_spaces
            + self.goal_scored
        )


@dataclass(frozen=True, slots=True)
class ScoredResultingState:
    score: float
    breakdown: StateScoreBreakdown
    flags: tuple[TacticalFlag, ...]


@dataclass(frozen=True, slots=True)
class RankedBranch:
    rank: int
    branch: BranchExpansion
    immediate_action: ScoredActionCandidate
    resulting_state: ScoredResultingState
    total_score: float
    flags: tuple[TacticalFlag, ...]


def _clamp(value: float, lower: float = -1, upper: float = 1) -> float:
    return min(upper, max(lower, value))


def score_action_candidate(
    analyzed_state: AnalyzedGameState,
    candidate: ActionCandidate,
    policy: ScoringPolicy = ScoringPolicy(),
) -> ScoredActionCandidate:
    if not candidate.feasible:
        raise ValueError("Only feasible candidates can be scored")

    field_length = analyzed_state.game_state.field.length
    forward_ratio = _clamp(candidate.metrics.forward_progress_cm / field_length)
    goal_ratio = _clamp(
        candidate.metrics.goal_proximity_improvement_cm / field_length
    )
    forward_score = forward_ratio * policy.forward_progress_weight
    goal_score = goal_ratio * policy.goal_proximity_weight
    backward_score = (
        -policy.backward_action_penalty * abs(forward_ratio)
        if forward_ratio < 0
        else 0
    )
    duration_score = -policy.duration_penalty * min(
        1,
        candidate.metrics.duration_seconds / policy.duration_normalizer_seconds,
    )

    target_space_score = 0.0
    flags: list[TacticalFlag] = []
    if candidate.metrics.forward_progress_cm > 0:
        flags.append(TacticalFlag.ADVANCES_TOWARD_GOAL)
    elif candidate.metrics.forward_progress_cm < 0:
        flags.append(TacticalFlag.BACKWARD_ACTION)

    if candidate.target_zone_id is not None:
        actor_team = analyzed_state.game_state.players_by_id[
            candidate.actor_id
        ].team_id
        zone = analyzed_state.target_zones_by_team[actor_team][
            candidate.target_zone_id
        ]
        if zone.status == TargetZoneStatus.AVAILABLE:
            target_space_score = policy.target_space_weight
            flags.append(TacticalFlag.TARGETS_AVAILABLE_SPACE)
        elif zone.status == TargetZoneStatus.CONTESTED:
            target_space_score = -policy.target_space_weight * 0.5
            flags.append(TacticalFlag.TARGETS_CONTESTED_SPACE)
        elif zone.status == TargetZoneStatus.DEFENDER_CONTROLLED:
            target_space_score = -policy.target_space_weight

    lane_score = 0.0
    margin = candidate.metrics.interception_time_margin_seconds
    if margin is not None:
        lane_score = (
            _clamp(margin / policy.lane_margin_normalizer_seconds)
            * policy.lane_safety_weight
        )
        if margin > 0:
            flags.append(TacticalFlag.SAFE_PASSING_LANE)

    breakdown = ActionScoreBreakdown(
        forward_progress=forward_score,
        goal_proximity=goal_score,
        target_space=target_space_score,
        lane_safety=lane_score,
        backward_penalty=backward_score,
        duration_penalty=duration_score,
    )
    return ScoredActionCandidate(
        candidate=candidate,
        score=breakdown.total,
        breakdown=breakdown,
        flags=tuple(flags),
    )


def score_resulting_state(
    analyzed_state: AnalyzedGameState,
    acting_team_id: str,
    policy: ScoringPolicy = ScoringPolicy(),
) -> ScoredResultingState:
    possession = analyzed_state.game_state.possession
    flags: list[TacticalFlag] = []
    if (
        possession.status == PossessionStatus.CONTROLLED
        and possession.team_id == acting_team_id
    ):
        possession_score = policy.possession_weight
        flags.append(TacticalFlag.RETAINS_POSSESSION)
    elif possession.status == PossessionStatus.CONTROLLED:
        possession_score = -policy.possession_weight
        flags.append(TacticalFlag.LOSES_POSSESSION)
    else:
        possession_score = -policy.possession_weight * 0.5

    controller_pressure_score = 0.0
    if possession.player_id is not None:
        context = analyzed_state.player_contexts[possession.player_id]
        controller_pressure_score = (
            -context.pressure_score * policy.controller_pressure_penalty
        )
        if context.pressure_level != PressureLevel.NONE:
            flags.append(TacticalFlag.CONTROLLER_UNDER_PRESSURE)

    candidate_count = analyzed_state.diagnostics.candidate_count
    feasible_count = analyzed_state.diagnostics.feasible_candidate_count
    option_ratio = feasible_count / candidate_count if candidate_count else 0
    follow_up_score = option_ratio * policy.follow_up_options_weight
    if option_ratio >= 0.75:
        flags.append(TacticalFlag.CREATES_MANY_OPTIONS)

    team_zones = analyzed_state.target_zones_by_team[acting_team_id]
    available_count = sum(
        zone.status == TargetZoneStatus.AVAILABLE
        for zone_id, zone in team_zones.items()
        if not analyzed_state.game_state.target_zones_by_id[zone_id].ball_only
    )
    ordinary_zone_count = sum(
        not analyzed_state.game_state.target_zones_by_id[zone_id].ball_only
        for zone_id in team_zones
    )
    available_ratio = (
        available_count / ordinary_zone_count if ordinary_zone_count else 0
    )
    available_space_score = available_ratio * policy.available_spaces_weight
    goal_score = (
        policy.goal_scored_reward
        if analyzed_state.game_state.scoring_team_id == acting_team_id
        else 0
    )

    breakdown = StateScoreBreakdown(
        possession=possession_score,
        controller_pressure=controller_pressure_score,
        follow_up_options=follow_up_score,
        available_spaces=available_space_score,
        goal_scored=goal_score,
    )
    return ScoredResultingState(
        score=breakdown.total,
        breakdown=breakdown,
        flags=tuple(flags),
    )


def rank_branches(
    parent: AnalyzedGameState,
    branches: tuple[BranchExpansion, ...],
    policy: ScoringPolicy = ScoringPolicy(),
) -> tuple[RankedBranch, ...]:
    scored: list[tuple[BranchExpansion, ScoredActionCandidate, ScoredResultingState]] = []
    for branch in branches:
        action_score = score_action_candidate(
            parent,
            branch.selected_candidate,
            policy,
        )
        acting_team_id = parent.game_state.players_by_id[
            branch.selected_candidate.actor_id
        ].team_id
        state_score = score_resulting_state(
            branch.resulting_analysis,
            acting_team_id,
            policy,
        )
        scored.append((branch, action_score, state_score))

    ordered = sorted(
        scored,
        key=lambda item: (
            -(item[1].score + item[2].score),
            -item[2].breakdown.possession,
            -item[0].selected_candidate.metrics.forward_progress_cm,
            item[0].selected_candidate.metrics.duration_seconds,
            item[0].selected_candidate.id,
        ),
    )
    return tuple(
        RankedBranch(
            rank=rank,
            branch=branch,
            immediate_action=action_score,
            resulting_state=state_score,
            total_score=action_score.score + state_score.score,
            flags=tuple(dict.fromkeys((*action_score.flags, *state_score.flags))),
        )
        for rank, (branch, action_score, state_score) in enumerate(
            ordered,
            start=1,
        )
    )
