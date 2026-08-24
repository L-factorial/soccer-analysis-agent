from dataclasses import dataclass

from app.analysis import ActionType
from app.domain import AttackingDirection, GameState, PlayerState, Vector2
from app.phases.models import TacticalPhase
from app.spatial import move_toward, orientation_degrees, turn_duration_seconds


@dataclass(frozen=True, slots=True)
class OffsidePolicy:
    """Numerical tolerance applied to release-time offside comparisons."""
    attacker_speed_cm_per_second: float = 650
    defender_speed_cm_per_second: float = 500
    turning_speed_degrees_per_second: float = 180
    position_tolerance_cm: float = 1


@dataclass(frozen=True, slots=True)
class OffsideCheck:
    applicable: bool
    offside: bool
    receiver_id: str | None
    receiver_position_at_release: Vector2 | None
    offside_line_x: float | None
    reason: str


def _attacking_progress(
    state: GameState,
    direction: AttackingDirection,
    position: Vector2,
) -> float:
    return (
        position.x
        if direction == AttackingDirection.POSITIVE_X
        else state.field.length - position.x
    )


def _turn_duration(
    player: PlayerState,
    target: Vector2,
    degrees_per_second: float,
) -> float:
    target_orientation = orientation_degrees(player.position, target)
    return turn_duration_seconds(
        player.orientation,
        target_orientation,
        degrees_per_second,
    )


def _receiver_position_at_release(
    state: GameState,
    phase: TacticalPhase,
    policy: OffsidePolicy,
) -> Vector2 | None:
    receiver_id = phase.primary_action.receiver_id
    if receiver_id is None:
        return None
    receiver = state.players_by_id[receiver_id]
    intention = next(
        (
            item
            for item in phase.attacking_intentions
            if item.player_id == receiver_id
        ),
        None,
    )
    if intention is None:
        return receiver.position
    return _player_position_at_release(
        receiver,
        intention.target,
        intention.start_offset_seconds,
        phase.ball_action_start_offset_seconds,
        policy.attacker_speed_cm_per_second,
        policy,
    )


def _player_position_at_release(
    player: PlayerState,
    target: Vector2,
    start_offset_seconds: float,
    release_seconds: float,
    speed_cm_per_second: float,
    policy: OffsidePolicy,
) -> Vector2:
    available = max(
        0,
        release_seconds
        - start_offset_seconds
        - _turn_duration(
            player,
            target,
            policy.turning_speed_degrees_per_second,
        ),
    )
    return move_toward(
        player.position,
        target,
        speed_cm_per_second
        * player.speed_category.multiplier
        * available,
    )


def check_phase_offside(
    state: GameState,
    phase: TacticalPhase,
    policy: OffsidePolicy = OffsidePolicy(),
) -> OffsideCheck:
    """Evaluate the intended receiver at the instant a pass is released."""
    action = phase.primary_action
    if action.action_type not in {
        ActionType.PASS_TO_PLAYER,
        ActionType.PASS_TO_SPACE,
    } or action.receiver_id is None:
        return OffsideCheck(False, False, None, None, None, "not_a_pass")

    actor = state.players_by_id[action.actor_id]
    team = state.teams_by_id[actor.team_id]
    receiver_position = _receiver_position_at_release(state, phase, policy)
    opponents = tuple(
        player
        for player in state.players_by_id.values()
        if player.team_id != actor.team_id
    )
    if receiver_position is None or len(opponents) < 2:
        return OffsideCheck(
            False,
            False,
            action.receiver_id,
            receiver_position,
            None,
            "fewer_than_two_opponents",
        )

    direction = team.attacking_direction
    receiver_progress = _attacking_progress(state, direction, receiver_position)
    if receiver_progress <= state.field.length / 2 + policy.position_tolerance_cm:
        return OffsideCheck(
            True,
            False,
            action.receiver_id,
            receiver_position,
            None,
            "receiver_in_own_half",
        )

    defender_intentions = {
        intention.player_id: intention for intention in phase.defensive_intentions
    }
    defender_progress = []
    for defender in opponents:
        intention = defender_intentions.get(defender.id)
        position = (
            _player_position_at_release(
                defender,
                intention.target,
                intention.start_offset_seconds,
                phase.ball_action_start_offset_seconds,
                policy.defender_speed_cm_per_second,
                policy,
            )
            if intention is not None
            else defender.position
        )
        defender_progress.append(_attacking_progress(state, direction, position))
    defender_progress.sort(reverse=True)
    second_last_progress = defender_progress[1]
    ball_progress = _attacking_progress(state, direction, state.ball.position)
    offside_line_progress = max(second_last_progress, ball_progress)
    offside = (
        receiver_progress
        > offside_line_progress + policy.position_tolerance_cm
    )
    offside_line_x = (
        offside_line_progress
        if direction == AttackingDirection.POSITIVE_X
        else state.field.length - offside_line_progress
    )
    return OffsideCheck(
        True,
        offside,
        action.receiver_id,
        receiver_position,
        offside_line_x,
        "receiver_beyond_offside_line" if offside else "receiver_onside",
    )
