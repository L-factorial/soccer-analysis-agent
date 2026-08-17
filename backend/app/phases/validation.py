from dataclasses import dataclass

from app.analysis import ActionType
from app.domain import GameState
from app.spatial import distance, is_inside_field
from app.phases.models import (
    PhaseIssue,
    PhaseIssueCode,
    PhaseValidation,
    TacticalPhase,
)


@dataclass(frozen=True, slots=True)
class PhaseValidationPolicy:
    """Static duration, arrival, field-boundary, and possession tolerances."""
    maximum_phase_duration_seconds: float = 12
    attacker_speed_cm_per_second: float = 650
    arrival_tolerance_cm: float = 25


def validate_tactical_phase(
    state: GameState,
    phase: TacticalPhase,
    policy: PhaseValidationPolicy = PhaseValidationPolicy(),
) -> PhaseValidation:
    issues: list[PhaseIssue] = []
    if not phase.primary_action.feasible:
        issues.append(
            PhaseIssue(
                PhaseIssueCode.INFEASIBLE_PRIMARY_ACTION,
                "The primary ball action is infeasible",
                phase.primary_action.actor_id,
            )
        )
    if phase.duration_seconds <= 0 or phase.duration_seconds > policy.maximum_phase_duration_seconds:
        issues.append(
            PhaseIssue(
                PhaseIssueCode.PHASE_DURATION_EXCEEDED,
                "The phase duration is outside the supported window",
            )
        )
    assigned = [intention.player_id for intention in phase.attacking_intentions]
    assigned += [intention.player_id for intention in phase.defensive_intentions]
    duplicates = {player_id for player_id in assigned if assigned.count(player_id) > 1}
    for player_id in sorted(duplicates):
        issues.append(
            PhaseIssue(
                PhaseIssueCode.PLAYER_ACTION_CONFLICT,
                f"Player {player_id} has conflicting phase intentions",
                player_id,
            )
        )
    for intention in (*phase.attacking_intentions, *phase.defensive_intentions):
        if not is_inside_field(intention.target, state.field):
            issues.append(
                PhaseIssue(
                    PhaseIssueCode.TARGET_OUTSIDE_FIELD,
                    f"Player {intention.player_id} has an out-of-field target",
                    intention.player_id,
                )
            )
    if phase.primary_action.action_type == ActionType.PASS_TO_SPACE:
        receiver_intention = next(
            (
                intention
                for intention in phase.attacking_intentions
                if intention.player_id == phase.primary_action.receiver_id
            ),
            None,
        )
        if receiver_intention is None:
            issues.append(
                PhaseIssue(
                    PhaseIssueCode.RECEIVER_CANNOT_ARRIVE,
                    "A space pass requires a coordinated receiver run",
                    phase.primary_action.receiver_id,
                )
            )
        else:
            receiver = state.players_by_id[receiver_intention.player_id]
            available_time = phase.duration_seconds - receiver_intention.start_offset_seconds
            if distance(receiver.position, receiver_intention.target) > (
                policy.attacker_speed_cm_per_second * available_time
                * receiver.speed_category.multiplier
                + policy.arrival_tolerance_cm
            ):
                issues.append(
                    PhaseIssue(
                        PhaseIssueCode.RECEIVER_CANNOT_ARRIVE,
                        "The receiver cannot reach the pass target during the phase",
                        receiver.id,
                    )
                )
    return PhaseValidation(valid=not issues, issues=tuple(issues))


def validate_phase_result(
    phase: TacticalPhase,
    resulting_state: GameState,
    initial: PhaseValidation,
) -> PhaseValidation:
    issues = list(initial.issues)
    action = phase.primary_action
    if action.action_type == ActionType.SHOT:
        if resulting_state.scoring_team_id != phase.attacking_team_id:
            issues.append(
                PhaseIssue(
                    PhaseIssueCode.GOAL_NOT_SCORED,
                    "The shot phase did not produce a goal",
                    action.actor_id,
                )
            )
    elif (
        resulting_state.possession.team_id != phase.attacking_team_id
        or resulting_state.possession.player_id
        not in {action.actor_id, action.receiver_id}
    ):
        issues.append(
            PhaseIssue(
                PhaseIssueCode.POSSESSION_NOT_RETAINED,
                "The attacking team did not retain controlled possession",
            )
        )
    return PhaseValidation(valid=not issues, issues=tuple(issues))
