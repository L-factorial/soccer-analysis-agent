from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class TacticalObjective(StrEnum):
    """Bounded strategic objectives the LLM may select."""
    BALANCED = "BALANCED"
    FAST_ATTACK = "FAST_ATTACK"
    RETAIN_POSSESSION = "RETAIN_POSSESSION"
    CREATE_SPACE = "CREATE_SPACE"
    WIDE_OVERLOAD = "WIDE_OVERLOAD"


class TacticalTempo(StrEnum):
    """Intent-level pacing preference translated into deterministic policies."""
    PATIENT = "PATIENT"
    BALANCED = "BALANCED"
    FAST = "FAST"


class TacticalIntent(BaseModel):
    """The only tactical decision shape accepted from the LLM."""

    objective: TacticalObjective
    tempo: TacticalTempo = TacticalTempo.BALANCED
    risk_level: float = Field(alias="riskLevel", ge=0, le=1)
    preferred_action_types: list[
        Literal["PASS_TO_PLAYER", "PASS_TO_SPACE", "MOVE_WITH_BALL", "SHOT"]
    ] = Field(default_factory=list, alias="preferredActionTypes", max_length=4)
    preferred_player_ids: list[str] = Field(
        default_factory=list, alias="preferredPlayerIds", max_length=5
    )
    preferred_space_ids: list[str] = Field(
        default_factory=list, alias="preferredSpaceIds", max_length=5
    )
    off_ball_priorities: list[
        Literal["DECOY_RUN", "SUPPORT_BALL", "FORWARD_RUN", "SHIFT_WITH_PLAY"]
    ] = Field(default_factory=list, alias="offBallPriorities", max_length=4)
    reasoning_summary: str = Field(alias="reasoningSummary", max_length=500)


class TacticalObservation(BaseModel):
    """Compact analyzed state sent to the LLM; never the mutable backend state."""
    instruction: str
    attacking_team_id: str = Field(alias="attackingTeamId")
    ball_carrier_id: str = Field(alias="ballCarrierId")
    attacking_direction: str = Field(alias="attackingDirection")
    ball_position: dict[str, float] = Field(alias="ballPosition")
    players: list[dict]
    spaces: list[dict]
    feasible_action_types: list[str] = Field(alias="feasibleActionTypes")


class PlanEvaluation(BaseModel):
    """Deterministic post-search assessment used by the revision loop."""
    goal_scored: bool = Field(alias="goalScored")
    instruction_alignment: float = Field(alias="instructionAlignment", ge=0, le=1)
    reasons: list[str]


class AgentPlanningMetadata(BaseModel):
    """Serializable record of orchestration mode, calls, intent, and fallback."""
    mode: Literal[
        "DETERMINISTIC", "AGENTIC", "TOOL_AGENT", "AGENTIC_FALLBACK"
    ]
    model: str | None = None
    attempts: int = 0
    intent: TacticalIntent | None = None
    evaluation: PlanEvaluation | None = None
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    tool_calls: int = Field(default=0, alias="toolCalls")
    agent_iterations: int = Field(default=0, alias="agentIterations")
