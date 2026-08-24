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
from app.domain import PossessionStatus
from app.models.animation_response import (
    AlternativePlan,
    AnimationResponse,
    CommentaryTrack,
)
from app.models.field_submission import FieldSubmission
from app.phases import PhaseSearchPolicy, search_tactical_phases
from app.planning import analyze_game_state
from app.scheduling import PhaseAnimationScheduler
from app.tactical_instruction import interpret_tactical_instruction
from app.validation import FieldSubmissionValidationError, validate_field_submission

router = APIRouter(prefix="/field-configurations", tags=["field configurations"])
logger = logging.getLogger("uvicorn.error")


def _base_search_policy() -> PhaseSearchPolicy:
    return PhaseSearchPolicy(
        maximum_depth=8,
        # Retain more competing tactical routes so a distinct second goal plan
        # has a realistic chance to survive until the response-selection step.
        beam_width=8,
        maximum_play_duration_seconds=30,
        maximum_retained_nodes=100,
        maximum_solution_count=2,
    )


def _augment_diagnostics(diagnostics, submission, applied_directives):
    """Attach deterministic instruction interpretation to search telemetry."""
    return diagnostics.model_copy(
        update={
            "tactical_instruction": submission.tactical_instruction,
            "applied_directives": applied_directives,
        }
    )


def _sequence_tactical_signature(sequence) -> tuple:
    """Describe the visible tactical route, not small geometric variations.

    Candidate generation can produce two paths that use different dynamic-space
    IDs or nearby endpoints while showing the same players performing the same
    play. Those are not useful UI alternatives. We therefore compare the action
    chain, participants, and broad lateral channel. Consecutive repetitions of
    the same choice (most commonly a long dribble split across phases) collapse
    into one route step.
    """
    signature = []
    for step in sequence.steps:
        action = step.phase.primary_action
        field_width = step.simulation.previous_state.field.width
        # Three channels preserve genuinely different left/central/right routes
        # without treating a few metres of endpoint noise as a new solution.
        lateral_channel = min(2, int(3 * action.destination.y / field_width))
        route_step = (
            action.action_type.value,
            action.actor_id,
            action.receiver_id,
            lateral_channel,
        )
        if not signature or signature[-1] != route_step:
            signature.append(route_step)
    return tuple(signature)


def _select_distinct_solutions(primary, candidates, maximum_solution_count: int):
    """Keep score order while excluding duplicate tactical routes."""
    selected = [primary]
    signatures = {_sequence_tactical_signature(primary)}
    for candidate in candidates:
        if candidate.id == primary.id:
            continue
        signature = _sequence_tactical_signature(candidate)
        if signature in signatures:
            continue
        selected.append(candidate)
        signatures.add(signature)
        if len(selected) == maximum_solution_count:
            break
    return tuple(selected)


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
    analyzed = analyze_game_state(build_initial_game_state(submission))
    if analyzed.game_state.possession.status != PossessionStatus.CONTROLLED:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "possession_not_controlled",
                "message": "Place the ball close to one unambiguously controlling player",
            },
        )

    base_search_policy = _base_search_policy()
    instruction_policy = interpret_tactical_instruction(
        submission.tactical_instruction,
        base_search_policy,
    )
    result = search_tactical_phases(
        analyzed,
        instruction_policy.search,
        scoring_policy=instruction_policy.scoring,
    )
    attacking_team_id = analyzed.game_state.possession.team_id
    # The public analyze contract is goal-oriented. A high-scoring non-goal
    # frontier node remains useful diagnostics but cannot become the animation.
    scoring_sequences = tuple(
        sequence
        for sequence in result.best_sequences
        if sequence.analyzed_state.game_state.scoring_team_id
        == attacking_team_id
    )
    if not scoring_sequences:
        diagnostics = _augment_diagnostics(
            build_phase_planner_diagnostics(result),
            submission,
            instruction_policy.applied_directives,
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
    selected = scoring_sequences[0]
    selected_solutions = _select_distinct_solutions(
        selected,
        scoring_sequences[1:],
        base_search_policy.maximum_solution_count,
    )
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
            instruction_policy.applied_directives,
        )
        animation_response = animation_response.model_copy(
            update={"diagnostics": diagnostics}
        )
    alternatives = []
    for index, sequence in enumerate(selected_solutions[1:], start=1):
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
