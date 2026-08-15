import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent import (
    AgentConfig,
    AgentPlanningMetadata,
    AgentPlanningRun,
    PlanningMode,
    TacticalAgent,
)
from app.agent.tool_service import ToolAgentNoCompliantPlanError, ToolPlanningAgent
from app.builders import (
    build_initial_game_state,
    build_phase_animation_response,
    build_phase_planner_diagnostics,
)
from app.domain import PossessionStatus
from app.models.animation_response import AlternativePlan, AnimationResponse
from app.models.field_submission import FieldSubmission
from app.phases import PhaseSearchPolicy, search_tactical_phases
from app.planning import analyze_game_state
from app.tactical_instruction import interpret_tactical_instruction
from app.validation import FieldSubmissionValidationError, validate_field_submission

router = APIRouter(prefix="/field-configurations", tags=["field configurations"])
logger = logging.getLogger("uvicorn.error")


def _base_search_policy() -> PhaseSearchPolicy:
    return PhaseSearchPolicy(
        maximum_depth=8,
        beam_width=5,
        maximum_play_duration_seconds=30,
        maximum_retained_nodes=75,
    )


def _run_planner(analyzed, instruction: str | None):
    """Select agentic or deterministic orchestration without changing the engine."""
    config = AgentConfig.from_environment()
    if config.enabled and instruction and instruction.strip():
        try:
            if config.planning_mode == PlanningMode.LLM_TOOL_AGENT:
                return ToolPlanningAgent(config).plan(
                    analyzed,
                    instruction,
                    _base_search_policy(),
                )
            return TacticalAgent(config).plan(
                analyzed,
                instruction,
                _base_search_policy(),
            )
        except ToolAgentNoCompliantPlanError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_instruction_compliant_plan",
                    "message": str(error),
                },
            ) from error
        except Exception as error:  # External failures must preserve core analysis.
            logger.exception("Agentic planning failed; using deterministic fallback")
            fallback_reason = type(error).__name__
    else:
        fallback_reason = None

    instruction_policy = interpret_tactical_instruction(
        instruction,
        _base_search_policy(),
    )
    result = search_tactical_phases(
        analyzed,
        instruction_policy.search,
        scoring_policy=instruction_policy.scoring,
    )
    mode = "AGENTIC_FALLBACK" if fallback_reason else "DETERMINISTIC"
    return AgentPlanningRun(
        result=result,
        metadata=AgentPlanningMetadata(
            mode=mode,
            fallbackReason=fallback_reason,
        ),
        applied_directives=instruction_policy.applied_directives,
    )


def _augment_diagnostics(diagnostics, submission, run):
    metadata = run.metadata
    return diagnostics.model_copy(
        update={
            "tactical_instruction": submission.tactical_instruction,
            "applied_directives": run.applied_directives,
            "agent_mode": metadata.mode,
            "agent_model": metadata.model,
            "agent_attempts": metadata.attempts,
            "tactical_intent": (
                metadata.intent.model_dump(by_alias=True)
                if metadata.intent is not None else None
            ),
            "plan_evaluation": (
                metadata.evaluation.model_dump(by_alias=True)
                if metadata.evaluation is not None else None
            ),
            "agent_fallback_reason": metadata.fallback_reason,
            "agent_tool_calls": metadata.tool_calls,
            "agent_iterations": metadata.agent_iterations,
        }
    )


def _sequence_uses_preferred_space(sequence, preferred_space_ids) -> bool:
    if not preferred_space_ids:
        return True
    return any(
        step.phase.primary_action.target_zone_id in preferred_space_ids
        for step in sequence.steps
    )


class FieldSubmissionReceipt(BaseModel):
    accepted: bool
    schema_version: str = Field(serialization_alias="schemaVersion")
    player_count: int = Field(serialization_alias="playerCount")
    team_count: int = Field(serialization_alias="teamCount")
    goal_count: int = Field(serialization_alias="goalCount")
    open_space_count: int = Field(serialization_alias="openSpaceCount")
    field_submission: FieldSubmission = Field(serialization_alias="fieldSubmission")


def _validate_submission(submission: FieldSubmission) -> None:
    try:
        validate_field_submission(submission)
    except FieldSubmissionValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_field_configuration",
                "issues": [issue.model_dump() for issue in error.issues],
            },
        ) from error


@router.post(
    "/analyze",
    response_model=AnimationResponse,
    response_model_by_alias=True,
)
def analyze_field_configuration(submission: FieldSubmission) -> AnimationResponse:
    """Analyze a layout and return its best supported animation sequence."""
    logger.info(
        "Received field analysis request: %s",
        json.dumps(submission.model_dump(by_alias=True)),
    )
    _validate_submission(submission)
    analyzed = analyze_game_state(build_initial_game_state(submission))
    if analyzed.game_state.possession.status != PossessionStatus.CONTROLLED:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "possession_not_controlled",
                "message": "Place the ball close to one unambiguously controlling player",
            },
        )

    run = _run_planner(analyzed, submission.tactical_instruction)
    result = run.result
    attacking_team_id = analyzed.game_state.possession.team_id
    preferred_space_ids = (
        run.metadata.intent.preferred_space_ids
        if run.metadata.intent is not None
        else ()
    )
    scoring_sequences = tuple(
        sequence
        for sequence in result.best_sequences
        if sequence.analyzed_state.game_state.scoring_team_id
        == attacking_team_id
        and _sequence_uses_preferred_space(
            sequence,
            preferred_space_ids,
        )
    )
    if not scoring_sequences:
        diagnostics = _augment_diagnostics(
            build_phase_planner_diagnostics(result),
            submission,
            run,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_goal_scoring_sequence",
                "message": (
                    "No goal-scoring sequence satisfying the requested tactical "
                    "spaces was found within the current search limits"
                    if preferred_space_ids
                    else "No goal-scoring sequence was found within the current "
                    "search depth and shooting range"
                ),
                "diagnostics": diagnostics.model_dump(by_alias=True),
            },
        )
    selected = scoring_sequences[0]
    animation_response = build_phase_animation_response(
        selected,
        build_phase_planner_diagnostics(result, selected),
    )
    if animation_response.diagnostics is not None:
        diagnostics = _augment_diagnostics(
            animation_response.diagnostics,
            submission,
            run,
        )
        animation_response = animation_response.model_copy(
            update={"diagnostics": diagnostics}
        )
    alternatives = []
    for index, sequence in enumerate(run.alternative_sequences[:2]):
        alternative = build_phase_animation_response(
            sequence,
            build_phase_planner_diagnostics(result, sequence),
        )
        alternatives.append(
            AlternativePlan(
                id=sequence.id,
                label=f"Alternative {index + 1}",
                reason=(
                    run.alternative_reasons[index]
                    if index < len(run.alternative_reasons)
                    else "A tactically different goal-scoring option."
                ),
                duration=alternative.duration,
                events=alternative.events,
                diagnostics=alternative.diagnostics,
            )
        )
    animation_response = animation_response.model_copy(
        update={"alternative_plans": tuple(alternatives)}
    )
    logger.info(
        "Returning animation response to frontend: %s",
        json.dumps(animation_response.model_dump(by_alias=True)),
    )
    return animation_response


@router.post("", response_model=FieldSubmissionReceipt)
def receive_field_configuration(
    submission: FieldSubmission,
) -> FieldSubmissionReceipt:
    """Validate and accept a static tactical field snapshot."""
    _validate_submission(submission)

    field = submission.field_configuration

    return FieldSubmissionReceipt(
        accepted=True,
        schema_version=submission.schema_version,
        player_count=len(field.players),
        team_count=len(field.teams),
        goal_count=len(field.goals),
        open_space_count=len(field.open_spaces),
        field_submission=submission,
    )
