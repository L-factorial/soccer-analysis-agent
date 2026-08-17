from dataclasses import dataclass
from itertools import combinations, permutations

from app.analysis import ActionType
from app.domain import (
    AttackingDirection,
    GameState,
    PlayerState,
    TargetZoneSource,
    Vector2,
    is_goalkeeper,
)
from app.spatial import distance, move_toward, orientation_degrees
from app.phases.models import (
    AttackingIntention,
    AttackingIntentionType,
    DefensiveIntention,
    DefensiveIntentionType,
    PhaseTemplateType,
    TacticalPhase,
)


@dataclass(frozen=True, slots=True)
class PhaseGenerationPolicy:
    """Tunable coordinated-movement constants.

    Distance values are centimeters, speeds are centimeters/second, angles are
    degrees, and reaction/start offsets are seconds.
    """
    maximum_phases: int = 50
    support_offset_cm: float = 900
    wide_run_offset_cm: float = 1200
    maximum_dynamic_support_spaces: int = 1
    attacking_shape_action_weight: float = 0.25
    attacking_shape_goal_weight: float = 0.15
    maximum_attacking_shape_shift_cm: float = 700
    hold_shape_ball_weight: float = 0.25
    hold_shape_goal_weight: float = 0.20
    maximum_hold_shape_shift_cm: float = 600
    turning_speed_degrees_per_second: float = 180
    decoy_run_forward_cm: float = 1000
    decoy_run_lateral_cm: float = 1400
    support_reaction_seconds: float = 0.15
    attacking_shape_reaction_seconds: float = 0.25
    # The nearest defender is already actively pressing at the phase boundary.
    press_reaction_seconds: float = 0.0
    tracking_reaction_seconds: float = 0.20
    defensive_shape_reaction_seconds: float = 0.35
    goalkeeper_reaction_seconds: float = 0.15
    support_ahead_tolerance_cm: float = 300


def _nearest(
    players: tuple[PlayerState, ...],
    target: Vector2,
    excluded: set[str] | None = None,
) -> PlayerState | None:
    excluded = excluded or set()
    return min(
        (player for player in players if player.id not in excluded),
        key=lambda player: (distance(player.position, target), player.id),
        default=None,
    )


def _progress(state: GameState, player: PlayerState) -> float:
    direction = state.teams_by_id[player.team_id].attacking_direction
    return player.position.x if direction == AttackingDirection.POSITIVE_X else -player.position.x


def _target_progress(
    state: GameState,
    team_id: str,
    target: Vector2,
) -> float:
    direction = state.teams_by_id[team_id].attacking_direction
    return target.x if direction == AttackingDirection.POSITIVE_X else -target.x


def _off_ball_player_for_role(
    state: GameState,
    players: tuple[PlayerState, ...],
    target: Vector2,
    intention_type: AttackingIntentionType,
    excluded: set[str],
    policy: PhaseGenerationPolicy,
) -> PlayerState | None:
    available = tuple(player for player in players if player.id not in excluded)
    if not available:
        return None
    if intention_type == AttackingIntentionType.SUPPORT_BALL:
        target_progress = _target_progress(state, available[0].team_id, target)
        supporting = tuple(
            player
            for player in available
            if _progress(state, player)
            <= target_progress + policy.support_ahead_tolerance_cm
        )
        pool = supporting or available
        return min(
            pool,
            key=lambda player: (distance(player.position, target), player.id),
        )
    if intention_type == AttackingIntentionType.FORWARD_RUN:
        return min(
            available,
            key=lambda player: (
                -player.speed_category.multiplier,
                distance(player.position, target),
                -_progress(state, player),
                player.id,
            ),
        )
    return _nearest(available, target)


def _assign_forward_runs(
    state: GameState,
    players: tuple[PlayerState, ...],
    targets: tuple[Vector2, ...],
    excluded: set[str],
) -> tuple[tuple[PlayerState, Vector2], ...]:
    """Globally match runners to targets without avoidable lane crossing.

    Arrival time rewards speed while normalized lateral cost preserves natural
    lanes. Joint assignment prevents a greedy fastest-first choice from forcing
    another runner across the field.
    """
    available = tuple(player for player in players if player.id not in excluded)
    assignment_count = min(len(available), len(targets))
    if assignment_count == 0:
        return ()
    best: tuple[float, tuple] | None = None
    best_pairs: tuple[tuple[PlayerState, Vector2], ...] = ()
    for selected_targets in combinations(targets, assignment_count):
        for selected_players in permutations(available, assignment_count):
            pairs = tuple(zip(selected_players, selected_targets, strict=True))
            arrival_cost = sum(
                distance(player.position, target)
                / (650 * player.speed_category.multiplier)
                for player, target in pairs
            )
            lateral_cost = sum(
                abs(player.position.y - target.y) / state.field.width
                for player, target in pairs
            )
            identity = tuple(
                (player.id, round(target.x, 6), round(target.y, 6))
                for player, target in pairs
            )
            rank = (arrival_cost + lateral_cost, identity)
            if best is None or rank < best:
                best = rank
                best_pairs = pairs
    return best_pairs


def _support_target(state: GameState, team_id: str, target: Vector2, offset: float) -> Vector2:
    direction = state.teams_by_id[team_id].attacking_direction
    x = target.x - offset if direction == AttackingDirection.POSITIVE_X else target.x + offset
    return Vector2(
        min(state.field.length, max(0, x)),
        min(state.field.width, max(0, target.y)),
    )


def _bounded_target(state: GameState, target: Vector2) -> Vector2:
    return Vector2(
        min(state.field.length, max(0, target.x)),
        min(state.field.width, max(0, target.y)),
    )


def _decoy_target(
    state: GameState,
    runner: PlayerState,
    action_target: Vector2,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Send a runner forward and away from the primary action's lane."""
    direction = state.teams_by_id[runner.team_id].attacking_direction
    forward = (
        policy.decoy_run_forward_cm
        if direction == AttackingDirection.POSITIVE_X
        else -policy.decoy_run_forward_cm
    )
    lateral = (
        -policy.decoy_run_lateral_cm
        if runner.position.y <= action_target.y
        else policy.decoy_run_lateral_cm
    )
    return _bounded_target(
        state,
        Vector2(runner.position.x + forward, runner.position.y + lateral),
    )


def _replace_defender_intention(
    intentions: tuple[DefensiveIntention, ...],
    replacement: DefensiveIntention,
) -> tuple[DefensiveIntention, ...]:
    return tuple(
        replacement if intention.player_id == replacement.player_id else intention
        for intention in intentions
    )


def _turn_duration_seconds(
    player: PlayerState,
    target: Vector2,
    turning_speed_degrees_per_second: float,
) -> float:
    target_orientation = orientation_degrees(player.position, target)
    difference = abs((target_orientation - player.orientation) % 360)
    return min(difference, 360 - difference) / turning_speed_degrees_per_second


def _hold_shape_target(
    state: GameState,
    defender: PlayerState,
    ball_target: Vector2,
    lane_y: float,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Shift an unassigned defender with the play without collapsing shape."""
    team = state.teams_by_id[defender.team_id]
    goal = state.goals_by_id[team.defended_goal_id]
    current_weight = 1 - (
        policy.hold_shape_ball_weight + policy.hold_shape_goal_weight
    )
    shape_anchor = Vector2(
        x=(
            defender.position.x * current_weight
            + ball_target.x * policy.hold_shape_ball_weight
            + goal.center.x * policy.hold_shape_goal_weight
        ),
        y=lane_y,
    )
    return _bounded_target(
        state,
        move_toward(
            defender.position,
            shape_anchor,
            policy.maximum_hold_shape_shift_cm,
        ),
    )


def _attacking_shape_target(
    state: GameState,
    attacker: PlayerState,
    action_target: Vector2,
    lane_y: float,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Advance an unassigned attacker while retaining most of their width."""
    team = state.teams_by_id[attacker.team_id]
    goal = state.goals_by_id[team.attacking_goal_id]
    current_weight = 1 - (
        policy.attacking_shape_action_weight
        + policy.attacking_shape_goal_weight
    )
    shape_anchor = Vector2(
        x=(
            attacker.position.x * current_weight
            + action_target.x * policy.attacking_shape_action_weight
            + goal.center.x * policy.attacking_shape_goal_weight
        ),
        y=lane_y,
    )
    return _bounded_target(
        state,
        move_toward(
            attacker.position,
            shape_anchor,
            policy.maximum_attacking_shape_shift_cm,
        ),
    )


def _available_shape_lanes(
    state: GameState,
    player_count: int,
    occupied_targets: tuple[Vector2, ...],
) -> list[float]:
    """Return distinct lateral formation slots not occupied by primary roles."""
    lanes = [
        state.field.width * (index + 1) / (player_count + 1)
        for index in range(player_count)
    ]
    for target in occupied_targets:
        if not lanes:
            break
        nearest_index = min(
            range(len(lanes)),
            key=lambda index: (abs(lanes[index] - target.y), lanes[index]),
        )
        lanes.pop(nearest_index)
    return lanes


def _complete_attacking_shape(
    state: GameState,
    teammates: tuple[PlayerState, ...],
    primary_player_ids: set[str],
    intentions: tuple[AttackingIntention, ...],
    action_target: Vector2,
    policy: PhaseGenerationPolicy,
) -> tuple[AttackingIntention, ...]:
    assigned = {
        *primary_player_ids,
        *(intention.player_id for intention in intentions),
    }
    unassigned = tuple(
        attacker
        for attacker in sorted(
            teammates,
            key=lambda player: (player.position.y, player.id),
        )
        if attacker.id not in assigned
        and not is_goalkeeper(attacker)
    )
    occupied_targets = (
        action_target,
        *(intention.target for intention in intentions),
    )
    lanes = _available_shape_lanes(
        state,
        len(teammates),
        tuple(occupied_targets),
    )
    # Both collections are laterally ordered, preserving the team's left-to-right
    # shape instead of making every player chase the same central anchor.
    lane_assignments = zip(unassigned, sorted(lanes), strict=False)
    shape_intentions = tuple(
        AttackingIntention(
            player_id=attacker.id,
            intention_type=AttackingIntentionType.SHIFT_WITH_PLAY,
            target=_attacking_shape_target(
                state,
                attacker,
                action_target,
                lane_y,
                policy,
            ),
            start_offset_seconds=policy.attacking_shape_reaction_seconds,
        )
        for attacker, lane_y in lane_assignments
    )
    return (*intentions, *shape_intentions)


def _complete_defensive_shape(
    state: GameState,
    defenders: tuple[PlayerState, ...],
    intentions: tuple[DefensiveIntention, ...],
    action_target: Vector2,
    policy: PhaseGenerationPolicy,
) -> tuple[DefensiveIntention, ...]:
    assigned = {intention.player_id for intention in intentions}
    unassigned = tuple(
        defender
        for defender in sorted(
            defenders,
            key=lambda player: (player.position.y, player.id),
        )
        if defender.id not in assigned
    )
    lanes = _available_shape_lanes(
        state,
        len(defenders),
        tuple(intention.target for intention in intentions),
    )
    shape_intentions = tuple(
        DefensiveIntention(
            player_id=defender.id,
            intention_type=DefensiveIntentionType.HOLD_SHAPE,
            target=_hold_shape_target(
                state,
                defender,
                action_target,
                lane_y,
                policy,
            ),
            target_player_id=None,
            start_offset_seconds=policy.defensive_shape_reaction_seconds,
        )
        for defender, lane_y in zip(unassigned, sorted(lanes), strict=False)
    )
    return (*intentions, *shape_intentions)


def _dribble_support_intentions(
    state: GameState,
    teammates: tuple[PlayerState, ...],
    excluded: set[str],
    destination: Vector2,
    policy: PhaseGenerationPolicy,
) -> tuple[AttackingIntention, ...]:
    support_target = _support_target(
        state,
        teammates[0].team_id,
        destination,
        policy.support_offset_cm,
    )
    forward_targets = [
        _bounded_target(
            state,
            Vector2(destination.x, destination.y - policy.wide_run_offset_cm),
        ),
        _bounded_target(
            state,
            Vector2(destination.x, destination.y + policy.wide_run_offset_cm),
        ),
    ]
    dynamic_spaces = tuple(
        zone
        for zone in state.target_zones_by_id.values()
        if zone.source == TargetZoneSource.DYNAMIC
        and zone.attacking_team_id == teammates[0].team_id
    )
    forward_targets.extend(
        zone.center for zone in dynamic_spaces[: policy.maximum_dynamic_support_spaces]
    )
    forward_targets = list(dict.fromkeys(forward_targets))

    intentions: list[AttackingIntention] = []
    assigned = set(excluded)
    support = _off_ball_player_for_role(
        state,
        teammates,
        support_target,
        AttackingIntentionType.SUPPORT_BALL,
        assigned,
        policy,
    )
    if support is not None:
        assigned.add(support.id)
        intentions.append(
            AttackingIntention(
                player_id=support.id,
                intention_type=AttackingIntentionType.SUPPORT_BALL,
                target=support_target,
                start_offset_seconds=policy.support_reaction_seconds,
            )
        )
    for runner, target in _assign_forward_runs(
        state,
        teammates,
        tuple(forward_targets),
        assigned,
    ):
        intentions.append(
            AttackingIntention(
                player_id=runner.id,
                intention_type=AttackingIntentionType.FORWARD_RUN,
                target=target,
                start_offset_seconds=policy.support_reaction_seconds,
            )
        )
    return tuple(intentions)


def generate_tactical_phases(
    state: GameState,
    feasible_actions: tuple,
    policy: PhaseGenerationPolicy = PhaseGenerationPolicy(),
) -> tuple[TacticalPhase, ...]:
    """Compile feasible ball actions into a small set of coordinated templates."""
    phases: list[TacticalPhase] = []
    deferred_variants: list[TacticalPhase] = []
    phase_sequence = 0
    for action in feasible_actions:
        if action.action_type not in {
            ActionType.PASS_TO_PLAYER,
            ActionType.PASS_TO_SPACE,
            ActionType.MOVE_WITH_BALL,
            ActionType.SHOT,
        }:
            continue
        if (
            action.action_type == ActionType.MOVE_WITH_BALL
            and action.source_analysis.dribble_direction is None
        ):
            # The phase planner uses bounded dribble primitives. Long zone
            # movements remain available to the legacy action planner.
            continue
        actor = state.players_by_id[action.actor_id]
        teammates = tuple(
            state.players_by_id[player_id]
            for player_id in state.player_ids_by_team[actor.team_id]
        )
        defenders = tuple(
            player for player in state.players_by_id.values()
            if player.team_id != actor.team_id
        )
        outfield_teammates = tuple(
            player for player in teammates if not is_goalkeeper(player)
        )
        outfield_defenders = tuple(
            player for player in defenders if not is_goalkeeper(player)
        )
        defending_goalkeepers = tuple(
            player for player in defenders if is_goalkeeper(player)
        )
        excluded_attackers = {actor.id}
        if action.receiver_id:
            excluded_attackers.add(action.receiver_id)
        support = _off_ball_player_for_role(
            state,
            outfield_teammates,
            action.destination,
            AttackingIntentionType.SUPPORT_BALL,
            excluded_attackers,
            policy,
        )
        presser = _nearest(outfield_defenders, action.start)
        tracker = _nearest(
            outfield_defenders,
            action.destination,
            {presser.id} if presser else set(),
        )
        attacking: list[AttackingIntention] = []
        defensive: list[DefensiveIntention] = []

        if action.action_type == ActionType.PASS_TO_SPACE and action.receiver_id:
            attacking.append(
                AttackingIntention(
                    player_id=action.receiver_id,
                    intention_type=AttackingIntentionType.RECEIVE_IN_SPACE,
                    target=action.destination,
                    start_offset_seconds=0,
                    required_arrival_seconds=action.metrics.duration_seconds,
                )
            )
            template = PhaseTemplateType.PASS_INTO_SPACE
        elif action.action_type == ActionType.PASS_TO_PLAYER:
            template = PhaseTemplateType.DIRECT_PASS
        elif action.action_type == ActionType.MOVE_WITH_BALL:
            template = PhaseTemplateType.DRIBBLE_WITH_SUPPORT
        else:
            template = PhaseTemplateType.SHOT

        support_variants: tuple[AttackingIntention | None, ...] = (None,)
        if template == PhaseTemplateType.DRIBBLE_WITH_SUPPORT:
            support_variants = _dribble_support_intentions(
                state,
                outfield_teammates,
                excluded_attackers,
                action.destination,
                policy,
            ) or (None,)
        elif support is not None and template != PhaseTemplateType.SHOT:
            support_variants = (
                AttackingIntention(
                    player_id=support.id,
                    intention_type=AttackingIntentionType.SUPPORT_BALL,
                    target=_support_target(
                        state,
                        actor.team_id,
                        action.destination,
                        policy.support_offset_cm,
                    ),
                    start_offset_seconds=policy.support_reaction_seconds,
                ),
            )
        if presser is not None:
            defensive.append(
                DefensiveIntention(
                    player_id=presser.id,
                    intention_type=DefensiveIntentionType.PRESS_BALL_CARRIER,
                    target=action.start,
                    target_player_id=actor.id,
                    start_offset_seconds=policy.press_reaction_seconds,
                )
            )
        if tracker is not None:
            defensive.append(
                DefensiveIntention(
                    player_id=tracker.id,
                    intention_type=(
                        DefensiveIntentionType.COVER_GOAL
                        if template == PhaseTemplateType.SHOT
                        else DefensiveIntentionType.TRACK_RECEIVER
                    ),
                    target=action.destination,
                    target_player_id=action.receiver_id,
                    start_offset_seconds=(
                        policy.goalkeeper_reaction_seconds
                        if template == PhaseTemplateType.SHOT
                        else policy.tracking_reaction_seconds
                    ),
                )
            )
        for goalkeeper in defending_goalkeepers:
            defended_goal = state.goals_by_id[
                state.teams_by_id[goalkeeper.team_id].defended_goal_id
            ]
            defensive.append(
                DefensiveIntention(
                    player_id=goalkeeper.id,
                    intention_type=DefensiveIntentionType.COVER_GOAL,
                    target=defended_goal.center,
                    target_player_id=action.actor_id,
                    start_offset_seconds=policy.goalkeeper_reaction_seconds,
                )
            )
        core_defensive = tuple(defensive)

        hold = getattr(action.source_analysis, "ball_carrier_hold_time_seconds", 0)
        phase_duration = action.metrics.duration_seconds
        if action.action_type in {
            ActionType.PASS_TO_PLAYER,
            ActionType.PASS_TO_SPACE,
            ActionType.SHOT,
        }:
            turn_duration = _turn_duration_seconds(
                actor,
                action.destination,
                policy.turning_speed_degrees_per_second,
            )
            hold = max(hold, turn_duration)
            ball_travel = (
                action.metrics.ball_travel_duration_seconds
                or action.metrics.duration_seconds
            )
            phase_duration = max(phase_duration, hold + ball_travel)
        for support_variant in support_variants:
            base_attacking = (
                (*attacking, support_variant)
                if support_variant is not None
                else tuple(attacking)
            )
            tactical_variants: list[
                tuple[tuple[AttackingIntention, ...], tuple[DefensiveIntention, ...]]
            ] = [(tuple(base_attacking), core_defensive)]

            # Add two explicit off-ball alternatives: the marker follows a decoy,
            # or protects the primary lane instead. The resulting states are then
            # compared by beam search at this and subsequent depths.
            if template != PhaseTemplateType.SHOT and tracker is not None:
                assigned_attackers = {
                    *excluded_attackers,
                    *(intention.player_id for intention in base_attacking),
                }
                decoy = _nearest(
                    outfield_teammates,
                    action.destination,
                    assigned_attackers,
                )
                if decoy is not None:
                    decoy_intention = AttackingIntention(
                        player_id=decoy.id,
                        intention_type=AttackingIntentionType.DECOY_RUN,
                        target=_decoy_target(state, decoy, action.destination, policy),
                        start_offset_seconds=0,
                    )
                    decoy_attack = (*base_attacking, decoy_intention)
                    tracking_decoy = DefensiveIntention(
                        player_id=tracker.id,
                        intention_type=DefensiveIntentionType.TRACK_RECEIVER,
                        target=decoy_intention.target,
                        target_player_id=decoy.id,
                        start_offset_seconds=policy.tracking_reaction_seconds,
                    )
                    tactical_variants.append(
                        (
                            decoy_attack,
                            _replace_defender_intention(
                                core_defensive,
                                tracking_decoy,
                            ),
                        )
                    )
                    lane_target = Vector2(
                        action.start.x + (action.destination.x - action.start.x) * 0.65,
                        action.start.y + (action.destination.y - action.start.y) * 0.65,
                    )
                    cover_lane = DefensiveIntention(
                        player_id=tracker.id,
                        intention_type=DefensiveIntentionType.COVER_PASSING_LANE,
                        target=lane_target,
                        target_player_id=None,
                        start_offset_seconds=policy.tracking_reaction_seconds,
                    )
                    tactical_variants.append(
                        (
                            decoy_attack,
                            _replace_defender_intention(core_defensive, cover_lane),
                        )
                    )

            for variant_index, (variant_attacking, variant_defensive) in enumerate(
                tactical_variants
            ):
                phase_attacking = _complete_attacking_shape(
                    state,
                    teammates,
                    excluded_attackers,
                    variant_attacking,
                    action.destination,
                    policy,
                )
                phase_defensive = _complete_defensive_shape(
                    state,
                    defenders,
                    variant_defensive,
                    action.destination,
                    policy,
                )
                phase_sequence += 1
                generated_phase = TacticalPhase(
                    id=f"phase-{phase_sequence:04d}",
                    template_type=template,
                    attacking_team_id=actor.team_id,
                    primary_action=action,
                    attacking_intentions=tuple(phase_attacking),
                    defensive_intentions=tuple(phase_defensive),
                    duration_seconds=phase_duration,
                    ball_action_start_offset_seconds=hold,
                )
                if variant_index == 0:
                    phases.append(generated_phase)
                    if len(phases) == policy.maximum_phases:
                        return tuple(phases)
                else:
                    # Preserve coverage of every feasible primary action before
                    # spending the remaining phase budget on tactical branches.
                    deferred_variants.append(generated_phase)
    remaining = max(0, policy.maximum_phases - len(phases))
    return tuple((*phases, *deferred_variants[:remaining]))
