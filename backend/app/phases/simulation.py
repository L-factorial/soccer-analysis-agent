from dataclasses import dataclass, replace
from types import MappingProxyType

from app.analysis import ActionType
from app.domain import GameState, PlayerState, Vector2
from app.spatial import distance, move_toward, orientation_degrees
from app.transitions import TransitionPolicy, apply_action_candidate
from app.phases.models import (
    DefensiveIntentionType,
    PhaseIssue,
    PhaseIssueCode,
    PhaseSimulationResult,
    PhaseStatus,
    PhaseValidation,
    TacticalPhase,
)
from app.phases.validation import (
    PhaseValidationPolicy,
    validate_phase_result,
    validate_tactical_phase,
)
from app.phases.interception import earliest_linear_interception


@dataclass(frozen=True, slots=True)
class PhaseSimulationPolicy:
    """Physical timing and movement bounds used while executing a phase.

    Speeds are centimeters/second, turning is degrees/second, and tolerances are
    centimeters or seconds according to the field name.
    """
    attacker_speed_cm_per_second: float = 650
    defender_speed_cm_per_second: float = 500
    tracking_distance_cm: float = 250
    tackle_radius_cm: float = 150
    turning_speed_degrees_per_second: float = 180
    validation: PhaseValidationPolicy = PhaseValidationPolicy()


def _move_player(
    player: PlayerState,
    target: Vector2,
    maximum_distance: float,
) -> PlayerState:
    destination = move_toward(player.position, target, maximum_distance)
    return replace(
        player,
        position=destination,
        orientation=orientation_degrees(player.position, target),
        velocity=Vector2(0, 0),
    )


def _turn_duration_seconds(
    player: PlayerState,
    target: Vector2,
    turning_speed_degrees_per_second: float,
) -> float:
    target_orientation = orientation_degrees(player.position, target)
    orientation_delta = abs((target_orientation - player.orientation) % 360)
    turn_angle = min(orientation_delta, 360 - orientation_delta)
    return turn_angle / turning_speed_degrees_per_second


def simulate_tactical_phase(
    state: GameState,
    phase: TacticalPhase,
    policy: PhaseSimulationPolicy = PhaseSimulationPolicy(),
) -> PhaseSimulationResult:
    validation = validate_tactical_phase(state, phase, policy.validation)
    if not validation.valid:
        return PhaseSimulationResult(
            phase=phase,
            previous_state=state,
            resulting_state=state,
            status=PhaseStatus.INVALID,
            validation=validation,
            changed_player_ids=(),
            actual_duration_seconds=0,
        )

    # Resolve pressure before a stationary passer releases the ball. Previously
    # only the end state was inspected, allowing a defender to reach the ball
    # carrier several seconds before an eventual successful pass.
    if phase.primary_action.action_type in {
        ActionType.PASS_TO_PLAYER,
        ActionType.PASS_TO_SPACE,
    }:
        presser = next(
            (
                intention
                for intention in phase.defensive_intentions
                if intention.intention_type
                == DefensiveIntentionType.PRESS_BALL_CARRIER
            ),
            None,
        )
        if presser is not None:
            defender = state.players_by_id[presser.player_id]
            pressure_arrival = (
                distance(defender.position, phase.primary_action.start)
                / (
                    policy.defender_speed_cm_per_second
                    * defender.speed_category.multiplier
                )
                + _turn_duration_seconds(
                    defender,
                    phase.primary_action.start,
                    policy.turning_speed_degrees_per_second,
                )
            )
            release_time = phase.ball_action_start_offset_seconds
            if pressure_arrival <= release_time:
                tackled_validation = PhaseValidation(
                    valid=False,
                    issues=(
                        *validation.issues,
                        PhaseIssue(
                            PhaseIssueCode.BALL_CARRIER_TACKLED_BEFORE_RELEASE,
                            (
                                f"Defender {defender.id} reaches the ball carrier "
                                f"at {pressure_arrival:.3f}s before the "
                                f"{release_time:.3f}s release"
                            ),
                            phase.primary_action.actor_id,
                        ),
                    ),
                )
                return PhaseSimulationResult(
                    phase=phase,
                    previous_state=state,
                    resulting_state=state,
                    status=PhaseStatus.TACKLED,
                    validation=tackled_validation,
                    changed_player_ids=(),
                    actual_duration_seconds=pressure_arrival,
                )

    if phase.primary_action.action_type == ActionType.MOVE_WITH_BALL:
        interceptions = []
        seen_defenders: set[str] = set()
        for intention in phase.defensive_intentions:
            if intention.intention_type == DefensiveIntentionType.HOLD_SHAPE:
                continue
            if intention.player_id in seen_defenders:
                continue
            seen_defenders.add(intention.player_id)
            defender = state.players_by_id[intention.player_id]
            interception = earliest_linear_interception(
                mover_start=phase.primary_action.start,
                mover_end=phase.primary_action.destination,
                duration_seconds=phase.duration_seconds,
                defender_start=defender.position,
                defender_speed_cm_per_second=(
                    policy.defender_speed_cm_per_second
                    * defender.speed_category.multiplier
                ),
                tackle_radius_cm=policy.tackle_radius_cm,
                defender_start_offset_seconds=(
                    intention.start_offset_seconds
                    + _turn_duration_seconds(
                        defender,
                        phase.primary_action.start,
                        policy.turning_speed_degrees_per_second,
                    )
                ),
                mover_start_offset_seconds=(
                    phase.primary_action.source_analysis.turn_duration_seconds
                ),
            )
            if interception is not None:
                interceptions.append((interception.time_seconds, defender.id, interception))

        if interceptions:
            tackle_time, defender_id, interception = min(
                interceptions,
                key=lambda item: (item[0], item[1]),
            )
            tackled_validation = PhaseValidation(
                valid=False,
                issues=(
                    *validation.issues,
                    PhaseIssue(
                        PhaseIssueCode.DRIBBLER_TACKLED,
                        (
                            f"Defender {defender_id} can tackle the ball carrier "
                            f"at {tackle_time:.3f}s near "
                            f"({interception.position.x:.1f}, "
                            f"{interception.position.y:.1f})"
                        ),
                        phase.primary_action.actor_id,
                    ),
                ),
            )
            return PhaseSimulationResult(
                phase=phase,
                previous_state=state,
                resulting_state=state,
                status=PhaseStatus.TACKLED,
                validation=tackled_validation,
                changed_player_ids=(),
                actual_duration_seconds=tackle_time,
            )

    transition = apply_action_candidate(
        state,
        phase.primary_action,
        TransitionPolicy(enable_defender_reaction=False),
    )
    players = dict(transition.resulting_state.players_by_id)
    changed = set(transition.changed_player_ids)

    for intention in phase.attacking_intentions:
        if intention.player_id == phase.primary_action.receiver_id:
            continue
        player = state.players_by_id[intention.player_id]
        turn_duration = _turn_duration_seconds(
            player,
            intention.target,
            policy.turning_speed_degrees_per_second,
        )
        available = max(
            0,
            phase.duration_seconds
            - intention.start_offset_seconds
            - turn_duration,
        )
        players[player.id] = _move_player(
            player,
            intention.target,
            policy.attacker_speed_cm_per_second
            * player.speed_category.multiplier
            * available,
        )
        changed.add(player.id)
    for intention in phase.defensive_intentions:
        player = state.players_by_id[intention.player_id]
        turn_duration = _turn_duration_seconds(
            player,
            intention.target,
            policy.turning_speed_degrees_per_second,
        )
        available = max(
            0,
            phase.duration_seconds
            - intention.start_offset_seconds
            - turn_duration,
        )
        maximum_distance = (
            policy.defender_speed_cm_per_second
            * player.speed_category.multiplier
            * available
        )
        if intention.intention_type in {
            DefensiveIntentionType.TRACK_RECEIVER,
            DefensiveIntentionType.COVER_GOAL,
        }:
            maximum_distance = min(
                maximum_distance,
                max(0, distance(player.position, intention.target) - policy.tracking_distance_cm),
            )
        players[player.id] = _move_player(
            player,
            intention.target,
            maximum_distance,
        )
        changed.add(player.id)

    resulting_state = replace(
        transition.resulting_state,
        players_by_id=MappingProxyType(players),
    )
    final_validation = validate_phase_result(phase, resulting_state, validation)
    return PhaseSimulationResult(
        phase=phase,
        previous_state=state,
        resulting_state=resulting_state,
        status=(PhaseStatus.SUCCESS if final_validation.valid else PhaseStatus.POSSESSION_LOST),
        validation=final_validation,
        changed_player_ids=tuple(sorted(changed)),
        actual_duration_seconds=phase.duration_seconds,
    )
