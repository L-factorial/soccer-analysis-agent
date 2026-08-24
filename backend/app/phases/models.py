from dataclasses import dataclass
from enum import StrEnum

from app.analysis import ActionCandidate
from app.domain import GameState, Vector2


class AttackingIntentionType(StrEnum):
    """Supported off-ball roles coordinated around a primary attacking action."""
    RECEIVE_IN_SPACE = "RECEIVE_IN_SPACE"
    SUPPORT_BALL = "SUPPORT_BALL"
    FORWARD_RUN = "FORWARD_RUN"
    HOLD_POSITION = "HOLD_POSITION"
    SHIFT_WITH_PLAY = "SHIFT_WITH_PLAY"
    DECOY_RUN = "DECOY_RUN"


class DefensiveIntentionType(StrEnum):
    """Supported defender reactions that run concurrently with an attack."""
    PRESS_BALL_CARRIER = "PRESS_BALL_CARRIER"
    TRACK_RECEIVER = "TRACK_RECEIVER"
    COVER_GOAL = "COVER_GOAL"
    HOLD_SHAPE = "HOLD_SHAPE"
    COVER_PASSING_LANE = "COVER_PASSING_LANE"


class PhaseTemplateType(StrEnum):
    """High-level coordinated patterns generated from feasible primary actions."""
    DIRECT_PASS = "DIRECT_PASS"
    PASS_INTO_SPACE = "PASS_INTO_SPACE"
    DRIBBLE_WITH_SUPPORT = "DRIBBLE_WITH_SUPPORT"
    SHOT = "SHOT"


class PhaseStatus(StrEnum):
    """Outcome of simulating one complete tactical phase."""
    SUCCESS = "SUCCESS"
    INVALID = "INVALID"
    INTERCEPTED = "INTERCEPTED"
    POSSESSION_LOST = "POSSESSION_LOST"
    TIMING_CONFLICT = "TIMING_CONFLICT"
    TACKLED = "TACKLED"


class PhaseIssueCode(StrEnum):
    """Stable machine-readable reasons a phase cannot be accepted."""
    INFEASIBLE_PRIMARY_ACTION = "infeasible_primary_action"
    PLAYER_ACTION_CONFLICT = "player_action_conflict"
    TARGET_OUTSIDE_FIELD = "target_outside_field"
    RECEIVER_CANNOT_ARRIVE = "receiver_cannot_arrive"
    PHASE_DURATION_EXCEEDED = "phase_duration_exceeded"
    POSSESSION_NOT_RETAINED = "possession_not_retained"
    GOAL_NOT_SCORED = "goal_not_scored"
    BALL_CARRIER_TACKLED_BEFORE_RELEASE = "ball_carrier_tackled_before_release"
    DRIBBLER_TACKLED = "dribbler_tackled"
    SHOT_BLOCKED = "shot_blocked"


@dataclass(frozen=True, slots=True)
class AttackingIntention:
    """Scheduled off-ball assignment relative to the start of its phase."""
    player_id: str
    intention_type: AttackingIntentionType
    target: Vector2
    start_offset_seconds: float
    required_arrival_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class DefensiveIntention:
    """Scheduled defensive assignment, optionally tracking a specific player."""
    player_id: str
    intention_type: DefensiveIntentionType
    target: Vector2
    target_player_id: str | None
    start_offset_seconds: float = 0


@dataclass(frozen=True, slots=True)
class TacticalPhase:
    """One primary action plus all concurrent player intentions.

    `duration_seconds` bounds every intention. The ball action may begin later
    than the phase via `ball_action_start_offset_seconds` to allow a run first.
    """
    id: str
    template_type: PhaseTemplateType
    attacking_team_id: str
    primary_action: ActionCandidate
    attacking_intentions: tuple[AttackingIntention, ...]
    defensive_intentions: tuple[DefensiveIntention, ...]
    duration_seconds: float
    ball_action_start_offset_seconds: float


@dataclass(frozen=True, slots=True)
class PhaseIssue:
    """One validation problem, optionally attributed to a player."""
    code: PhaseIssueCode
    message: str
    player_id: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseValidation:
    """Aggregate validity result; valid phases always have no blocking issues."""
    valid: bool
    issues: tuple[PhaseIssue, ...]


@dataclass(frozen=True, slots=True)
class PhaseSimulationResult:
    """Immutable before/after states and outcome for a simulated phase."""
    phase: TacticalPhase
    previous_state: GameState
    resulting_state: GameState
    status: PhaseStatus
    validation: PhaseValidation
    changed_player_ids: tuple[str, ...]
    actual_duration_seconds: float
