from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.position import Position


class TimedEvent(BaseModel):
    id: str
    player_id: str = Field(serialization_alias="playerId")
    start_time: float = Field(serialization_alias="startTime", ge=0)
    duration: float = Field(gt=0)


class MoveEvent(TimedEvent):
    type: Literal["MOVE", "RUN", "MOVE_WITH_BALL"]
    target: Position


class TurnEvent(TimedEvent):
    type: Literal["TURN"]
    start_orientation: float = Field(serialization_alias="startOrientation")
    target_orientation: float = Field(serialization_alias="targetOrientation")


class PassEvent(TimedEvent):
    type: Literal["PASS"]
    target_player_id: str = Field(serialization_alias="targetPlayerId")


class PassToSpaceEvent(TimedEvent):
    type: Literal["PASS_TO_SPACE"]
    intended_receiver_id: str = Field(serialization_alias="intendedReceiverId")
    space_id: str = Field(serialization_alias="spaceId")
    target: Position


class ShotEvent(TimedEvent):
    type: Literal["SHOT"]
    goal_id: str = Field(serialization_alias="goalId")
    target: Position


class ReceiveEvent(BaseModel):
    id: str
    type: Literal["RECEIVE"]
    player_id: str = Field(serialization_alias="playerId")
    start_time: float = Field(serialization_alias="startTime", ge=0)


AnimationEvent = Annotated[
    MoveEvent | TurnEvent | PassEvent | PassToSpaceEvent | ShotEvent | ReceiveEvent,
    Field(discriminator="type"),
]


class DynamicSpaceDiagnostic(BaseModel):
    id: str
    center: Position
    radius: float


class PhaseIntentionDiagnostic(BaseModel):
    side: Literal["ATTACKING", "DEFENSIVE"]
    player_id: str = Field(serialization_alias="playerId")
    intention_type: str = Field(serialization_alias="intentionType")
    target: Position
    target_player_id: str | None = Field(
        default=None,
        serialization_alias="targetPlayerId",
    )


class SelectedPhaseDiagnostic(BaseModel):
    id: str
    phase_type: str = Field(serialization_alias="phaseType")
    action_type: str = Field(serialization_alias="actionType")
    actor_id: str = Field(serialization_alias="actorId")
    receiver_id: str | None = Field(serialization_alias="receiverId")
    target_zone_id: str | None = Field(serialization_alias="targetZoneId")
    target: Position
    start_time: float = Field(serialization_alias="startTime", ge=0)
    duration: float = Field(gt=0)
    end_time: float = Field(serialization_alias="endTime", ge=0)
    ball_action_start_time: float = Field(
        serialization_alias="ballActionStartTime", ge=0
    )
    offside_line_x: float | None = Field(
        default=None, serialization_alias="offsideLineX"
    )
    possession_before: str = Field(serialization_alias="possessionBefore")
    possession_after: str = Field(serialization_alias="possessionAfter")
    score: float
    scored_goal: bool = Field(serialization_alias="scoredGoal")
    intentions: tuple[PhaseIntentionDiagnostic, ...] = ()


class PlannerDiagnostics(BaseModel):
    objective: Literal["SCORE_GOAL"] = "SCORE_GOAL"
    tactical_instruction: str | None = Field(
        default=None,
        serialization_alias="tacticalInstruction",
    )
    applied_directives: tuple[str, ...] = Field(
        default=(),
        serialization_alias="appliedDirectives",
    )
    agent_mode: Literal[
        "DETERMINISTIC", "AGENTIC", "TOOL_AGENT", "AGENTIC_FALLBACK"
    ] = Field(
        default="DETERMINISTIC",
        serialization_alias="agentMode",
    )
    agent_model: str | None = Field(default=None, serialization_alias="agentModel")
    agent_attempts: int = Field(default=0, serialization_alias="agentAttempts")
    tactical_intent: dict | None = Field(
        default=None,
        serialization_alias="tacticalIntent",
    )
    plan_evaluation: dict | None = Field(
        default=None,
        serialization_alias="planEvaluation",
    )
    agent_fallback_reason: str | None = Field(
        default=None,
        serialization_alias="agentFallbackReason",
    )
    agent_tool_calls: int = Field(default=0, serialization_alias="agentToolCalls")
    agent_iterations: int = Field(default=0, serialization_alias="agentIterations")
    planner_type: Literal["ACTION", "TACTICAL_PHASE"] = Field(
        default="ACTION",
        serialization_alias="plannerType",
    )
    phase_count: int | None = Field(default=None, serialization_alias="phaseCount")
    attacking_team_id: str | None = Field(serialization_alias="attackingTeamId")
    reached_depth: int = Field(serialization_alias="reachedDepth")
    evaluated_candidate_count: int = Field(serialization_alias="evaluatedCandidateCount")
    root_candidate_count: int = Field(serialization_alias="rootCandidateCount")
    root_feasible_candidate_count: int = Field(serialization_alias="rootFeasibleCandidateCount")
    pruned_by_beam_count: int = Field(serialization_alias="prunedByBeamCount")
    pruned_by_duration_count: int = Field(serialization_alias="prunedByDurationCount")
    pruned_by_offside_count: int = Field(
        default=0,
        serialization_alias="prunedByOffsideCount",
    )
    pruned_by_possession_count: int = Field(serialization_alias="prunedByPossessionCount")
    pruned_by_action_pattern_count: int = Field(serialization_alias="prunedByActionPatternCount")
    rejection_reasons: dict[str, int] = Field(serialization_alias="rejectionReasons")
    dynamic_spaces: tuple[DynamicSpaceDiagnostic, ...] = Field(serialization_alias="dynamicSpaces")
    selected_sequence_score: float | None = Field(
        default=None,
        serialization_alias="selectedSequenceScore",
    )
    selected_sequence_depth: int | None = Field(
        default=None,
        serialization_alias="selectedSequenceDepth",
    )
    selected_phases: tuple[SelectedPhaseDiagnostic, ...] = Field(
        default=(),
        serialization_alias="selectedPhases",
    )
    explanation: tuple[str, ...] = ()


class AlternativePlan(BaseModel):
    id: str
    label: str
    reason: str
    duration: float = Field(ge=0)
    events: tuple[AnimationEvent, ...]
    diagnostics: PlannerDiagnostics | None = None


class AnimationResponse(BaseModel):
    duration: float = Field(ge=0)
    events: tuple[AnimationEvent, ...]
    diagnostics: PlannerDiagnostics | None = None
    alternative_plans: tuple[AlternativePlan, ...] = Field(
        default=(), serialization_alias="alternativePlans"
    )
