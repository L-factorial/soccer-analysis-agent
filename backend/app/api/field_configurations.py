import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.builders import (
    build_initial_game_state,
    build_phase_planner_diagnostics,
)
from app.commentary import generate_commentary
from app.commentary.models import CommentarySimulationInput
from app.game_engine import (
    PossessionNotControlledError,
    SoccerGameEngine,
)
from app.models.animation_response import (
    AlternativePlan,
    AnimationResponse,
    CommentaryTrack,
)
from app.models.field_submission import FieldSubmission
from app.scheduling import PhaseAnimationScheduler
from app.validation import FieldSubmissionValidationError, validate_field_submission

router = APIRouter(prefix="/field-configurations", tags=["field configurations"])
logger = logging.getLogger("uvicorn.error")


def _augment_diagnostics(diagnostics, submission, applied_directives):
    """Attach deterministic instruction interpretation to search telemetry."""
    return diagnostics.model_copy(
        update={
            "tactical_instruction": submission.tactical_instruction,
            "applied_directives": applied_directives,
        }
    )


class FieldSubmissionReceipt(BaseModel):
    accepted: bool
    schema_version: str = Field(serialization_alias="schemaVersion")
    player_count: int = Field(serialization_alias="playerCount")
    team_count: int = Field(serialization_alias="teamCount")
    goal_count: int = Field(serialization_alias="goalCount")
    open_space_count: int = Field(serialization_alias="openSpaceCount")
    field_submission: FieldSubmission = Field(serialization_alias="fieldSubmission")


class CommentaryRequest(BaseModel):
    """A completed simulation submitted independently for narration."""
    field_submission: FieldSubmission = Field(alias="fieldSubmission")
    # This is the camelCase representation previously returned to the frontend,
    # not an internal AnimationResponse reconstructed from snake_case fields.
    animation_response: CommentarySimulationInput = Field(alias="animationResponse")


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
    # Boundary validation rejects malformed soccer layouts before constructing
    # authoritative domain state.
    _validate_submission(submission)
    try:
        engine_plan = SoccerGameEngine().plan(
            build_initial_game_state(submission),
            submission.tactical_instruction,
        )
    except PossessionNotControlledError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "possession_not_controlled",
                "message": "Place the ball close to one unambiguously controlling player",
            },
        ) from error

    result = engine_plan.search_result
    if engine_plan.primary_solution is None:
        diagnostics = _augment_diagnostics(
            build_phase_planner_diagnostics(result),
            submission,
            engine_plan.instruction_policy.applied_directives,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_goal_scoring_sequence",
                "message": (
                    "No goal-scoring sequence was found within the current "
                    "search depth and shooting range"
                ),
                "diagnostics": diagnostics.model_dump(by_alias=True),
            },
        )
    selected = engine_plan.primary_solution
    # Scheduling is deliberately last: it projects the selected immutable plan
    # onto timestamps and never changes search or simulation decisions.
    scheduler = PhaseAnimationScheduler()
    animation_response = scheduler.schedule(
        selected,
        build_phase_planner_diagnostics(result, selected),
    )
    if animation_response.diagnostics is not None:
        diagnostics = _augment_diagnostics(
            animation_response.diagnostics,
            submission,
            engine_plan.instruction_policy.applied_directives,
        )
        animation_response = animation_response.model_copy(
            update={"diagnostics": diagnostics}
        )
    alternatives = []
    for index, sequence in enumerate(engine_plan.selected_solutions[1:], start=1):
        alternative = scheduler.schedule(
            sequence,
            build_phase_planner_diagnostics(result, sequence),
        )
        alternatives.append(
            AlternativePlan(
                id=sequence.id,
                label=f"Alternative {index}",
                reason="A distinct goal-scoring route retained by beam search.",
                duration=alternative.duration,
                events=alternative.events,
                diagnostics=alternative.diagnostics,
                phase_snapshots=alternative.phase_snapshots,
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


@router.post(
    "/commentary",
    response_model=CommentaryTrack,
    response_model_by_alias=True,
)
def create_commentary(request: CommentaryRequest) -> CommentaryTrack:
    """Generate narration independently of the simulation request lifecycle."""
    commentary = generate_commentary(
        request.animation_response,
        request.field_submission,
    )
    if commentary is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "commentary_unavailable",
                "message": "Commentary is disabled, unconfigured, or could not be generated",
            },
        )
    return commentary


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
