import json
import logging
from uuid import UUID, uuid4
from typing import Literal

from app.analysis_lifecycle import (
    AnalysisCancelled, DuplicateAnalysis, analysis_registry, check_analysis_cancelled,
)

from fastapi import APIRouter, HTTPException, Response
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
from app.rate_limits import LimitExceeded, rate_limiter
from app.scheduling import PhaseAnimationScheduler
from app.solution_cache import configuration_hash, solution_cache
from app.validation import FieldSubmissionValidationError, validate_field_submission

router = APIRouter(prefix="/field-configurations", tags=["field configurations"])
logger = logging.getLogger("uvicorn.error")


def _limit_error(error: LimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"code": error.code, "message": str(error)},
        headers={"Retry-After": str(error.retry_after)},
    )


def _augment_diagnostics(diagnostics, submission, applied_directives):
    """Attach deterministic instruction interpretation to search telemetry."""
    return diagnostics.model_copy(
        update={
            "tactical_instruction": submission.tactical_instruction,
            "applied_directives": applied_directives,
        }
    )


class AnalysisRequest(FieldSubmission):
    analysis_id: UUID = Field(default_factory=uuid4, alias="analysisId")


class CancelAnalysisRequest(BaseModel):
    analysis_id: UUID = Field(alias="analysisId")


@router.get("/metrics")
async def analysis_metrics(response: Response) -> dict[str, int]:
    response.headers["Cache-Control"] = "no-store"
    return analysis_registry.metrics()


@router.post("/cancel-analysis")
async def cancel_analysis(request: CancelAnalysisRequest):
    analysis_id = str(request.analysis_id)
    return {"analysisId": analysis_id, "status": analysis_registry.cancel(analysis_id)}


class FieldSubmissionReceipt(BaseModel):
    accepted: bool
    schema_version: str = Field(serialization_alias="schemaVersion")
    player_count: int = Field(serialization_alias="playerCount")
    team_count: int = Field(serialization_alias="teamCount")
    goal_count: int = Field(serialization_alias="goalCount")
    open_space_count: int = Field(serialization_alias="openSpaceCount")
    field_submission: FieldSubmission = Field(serialization_alias="fieldSubmission")


class SharedSolution(BaseModel):
    field_submission: FieldSubmission = Field(serialization_alias="fieldSubmission")
    animation_response: AnimationResponse = Field(serialization_alias="animationResponse")


@router.get("/solutions/{field_hash}", response_model=SharedSolution)
def get_shared_solution(field_hash: str, response: Response) -> SharedSolution:
    response.headers["Cache-Control"] = "no-store"
    if len(field_hash) != 64 or any(character not in "0123456789abcdef" for character in field_hash):
        raise HTTPException(status_code=404, detail="Saved analysis not found.")
    cached = solution_cache.get(field_hash)
    if cached is None:
        raise HTTPException(status_code=404, detail="This saved analysis is no longer available. The server keeps the 50 most recently used solutions.")
    submission, animation = cached
    return SharedSolution(field_submission=submission, animation_response=animation)


class CommentaryRequest(BaseModel):
    """A completed simulation submitted independently for narration."""
    commentary_enabled: bool = Field(default=False, alias="commentaryEnabled", strict=True)
    field_hash: str | None = Field(default=None, alias="fieldHash", pattern=r"^[0-9a-f]{64}$")
    plan_id: str = Field(default="requested", alias="planId")
    language: Literal["en"] = "en"
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
def analyze_field_configuration(submission: AnalysisRequest) -> AnimationResponse:
    """Reject excess work immediately and release capacity on every exit path."""
    analysis_id = str(getattr(submission, "analysis_id", uuid4()))
    try:
        with rate_limiter.analysis_slot(), analysis_registry.track(analysis_id):
            response = _analyze_field_configuration(submission)
            return response.model_copy(update={"analysis_id": analysis_id})
    except AnalysisCancelled as error:
        raise HTTPException(status_code=409, detail={
            "code": "analysis_cancelled", "message": "Analysis was cancelled.",
            "analysisId": analysis_id,
        }) from error
    except DuplicateAnalysis as error:
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_analysis_id", "message": "Use a new analysis ID for each request.",
        }) from error
    except LimitExceeded as error:
        raise _limit_error(error) from error


def _analyze_field_configuration(submission: FieldSubmission) -> AnimationResponse:
    """Analyze a layout and return its best supported animation sequence."""
    logger.info(
        "Received field analysis request: %s",
        submission.model_dump_json(by_alias=True),
    )
    # Boundary validation rejects malformed soccer layouts before constructing
    # authoritative domain state.
    _validate_submission(submission)
    field_hash = configuration_hash(submission)
    cached = solution_cache.get(field_hash)
    if cached is not None:
        return cached[1]
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

    check_analysis_cancelled()
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
        check_analysis_cancelled()
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
    check_analysis_cancelled()
    animation_response = animation_response.model_copy(update={"field_hash": field_hash})
    return solution_cache.put(field_hash, submission, animation_response)


@router.post(
    "/commentary",
    response_model=CommentaryTrack,
    response_model_by_alias=True,
)
def create_commentary(request: CommentaryRequest) -> CommentaryTrack:
    """Generate narration independently of the simulation request lifecycle."""
    if not request.commentary_enabled:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "commentary_not_enabled",
                "message": "Enable commentary before requesting generation",
            },
        )
    simulation = request.animation_response
    submission = request.field_submission
    if request.field_hash is not None:
        saved = solution_cache.get(request.field_hash)
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved analysis is no longer available.")
        submission, response = saved
        plan = response if request.plan_id == "requested" else next(
            (plan for plan in response.alternative_plans if plan.id == request.plan_id), None
        )
        if plan is None:
            raise HTTPException(status_code=404, detail="Saved plan not found.")
        if plan.commentary is not None:
            return plan.commentary
        # Narrate the authoritative saved plan, not a client-supplied timeline.
        simulation = CommentarySimulationInput.model_validate(plan.model_dump(mode="json", by_alias=True))
    try:
        rate_limiter.reserve_commentary()
    except LimitExceeded as error:
        raise _limit_error(error) from error
    commentary = generate_commentary(
        simulation,
        submission,
    )
    if commentary is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "commentary_unavailable",
                "message": "Commentary is disabled, unconfigured, or could not be generated",
            },
        )
    if request.field_hash is not None:
        return solution_cache.save_commentary(request.field_hash, request.plan_id, commentary)
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
