from dataclasses import dataclass
from enum import StrEnum

from app.analysis import ActionCandidate
from app.domain import GameState, Vector2


class AttackingIntentionType(StrEnum):
    RECEIVE_IN_SPACE = "RECEIVE_IN_SPACE"
    SUPPORT_BALL = "SUPPORT_BALL"
    FORWARD_RUN = "FORWARD_RUN"
    HOLD_POSITION = "HOLD_POSITION"
    SHIFT_WITH_PLAY = "SHIFT_WITH_PLAY"
    DECOY_RUN = "DECOY_RUN"


class DefensiveIntentionType(StrEnum):
    PRESS_BALL_CARRIER = "PRESS_BALL_CARRIER"
    TRACK_RECEIVER = "TRACK_RECEIVER"
    COVER_GOAL = "COVER_GOAL"
    HOLD_SHAPE = "HOLD_SHAPE"
    COVER_PASSING_LANE = "COVER_PASSING_LANE"


class PhaseTemplateType(StrEnum):
    DIRECT_PASS = "DIRECT_PASS"
    PASS_INTO_SPACE = "PASS_INTO_SPACE"
    DRIBBLE_WITH_SUPPORT = "DRIBBLE_WITH_SUPPORT"
    SHOT = "SHOT"


class PhaseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    INVALID = "INVALID"
    INTERCEPTED = "INTERCEPTED"
    POSSESSION_LOST = "POSSESSION_LOST"
    TIMING_CONFLICT = "TIMING_CONFLICT"
    TACKLED = "TACKLED"


class PhaseIssueCode(StrEnum):
    INFEASIBLE_PRIMARY_ACTION = "infeasible_primary_action"
    PLAYER_ACTION_CONFLICT = "player_action_conflict"
    TARGET_OUTSIDE_FIELD = "target_outside_field"
    RECEIVER_CANNOT_ARRIVE = "receiver_cannot_arrive"
    PHASE_DURATION_EXCEEDED = "phase_duration_exceeded"
    POSSESSION_NOT_RETAINED = "possession_not_retained"
    GOAL_NOT_SCORED = "goal_not_scored"
    BALL_CARRIER_TACKLED_BEFORE_RELEASE = "ball_carrier_tackled_before_release"
    DRIBBLER_TACKLED = "dribbler_tackled"


@dataclass(frozen=True, slots=True)
class AttackingIntention:
    player_id: str
    intention_type: AttackingIntentionType
    target: Vector2
    start_offset_seconds: float
    required_arrival_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class DefensiveIntention:
    player_id: str
    intention_type: DefensiveIntentionType
    target: Vector2
    target_player_id: str | None
    start_offset_seconds: float = 0


@dataclass(frozen=True, slots=True)
class TacticalPhase:
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
    code: PhaseIssueCode
    message: str
    player_id: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseValidation:
    valid: bool
    issues: tuple[PhaseIssue, ...]


@dataclass(frozen=True, slots=True)
class PhaseSimulationResult:
    phase: TacticalPhase
    previous_state: GameState
    resulting_state: GameState
    status: PhaseStatus
    validation: PhaseValidation
    changed_player_ids: tuple[str, ...]
    actual_duration_seconds: float
