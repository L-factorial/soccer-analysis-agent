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
from app.spatial import (
    distance,
    move_toward,
    orientation_degrees,
    turn_duration_seconds,
)
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
    goal_side_cover_distance_cm: float = 900
    minimum_cover_depth_cm: float = 400
    central_cover_half_width_cm: float = 2500
    crossing_trigger_progress_ratio: float = 0.65
    crossing_wide_channel_ratio: float = 0.25
    crossing_box_depth_cm: float = 1200
    crossing_post_inset_cm: float = 300
    # Advanced central dribbles still need a player to stretch the defensive
    # block. The width provider advances without being pulled into the carrier's
    # lane, leaving distinct outside and inside passing options.
    width_provider_progress_ratio: float = 0.65
    width_provider_forward_cm: float = 900
    threat_aware_shape_progress_ratio: float = 0.60
    threat_aware_corridor_weight: float = 0.65
    shot_rebound_depth_cm: float = 800
    shot_rebound_post_inset_cm: float = 300
    shot_rebound_reaction_seconds: float = 0.20
    shot_secondary_block_fraction: float = 0.35


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


def _attacking_progress_ratio(
    state: GameState,
    attacking_team_id: str,
    target: Vector2,
) -> float:
    """Normalize a position from the team's own goal (0) to opponent goal (1)."""
    team = state.teams_by_id[attacking_team_id]
    defended_goal = state.goals_by_id[team.defended_goal_id]
    attacking_goal = state.goals_by_id[team.attacking_goal_id]
    origin = _target_progress(state, attacking_team_id, defended_goal.center)
    end = _target_progress(state, attacking_team_id, attacking_goal.center)
    if end == origin:
        return 0
    return (_target_progress(state, attacking_team_id, target) - origin) / (end - origin)


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


def _preserve_natural_width(
    state: GameState,
    player: PlayerState,
    target: Vector2,
) -> Vector2:
    """Do not pull a runner inward when their current lane is already wider.

    A target remains free to widen a player, but it may not reduce that player's
    distance from the field centre. This keeps an existing winger available as
    an outlet instead of making every forward run converge around the carrier.
    """
    centre_y = state.field.width / 2
    if abs(player.position.y - centre_y) > abs(target.y - centre_y):
        return Vector2(target.x, player.position.y)
    return target


def _width_provider_target(
    state: GameState,
    player: PlayerState,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Advance the naturally widest teammate while retaining their touchline lane."""
    direction = state.teams_by_id[player.team_id].attacking_direction
    forward = (
        policy.width_provider_forward_cm
        if direction == AttackingDirection.POSITIVE_X
        else -policy.width_provider_forward_cm
    )
    return _bounded_target(
        state,
        Vector2(player.position.x + forward, player.position.y),
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
    return turn_duration_seconds(
        player.orientation,
        target_orientation,
        turning_speed_degrees_per_second,
    )


def _hold_shape_target(
    state: GameState,
    defender: PlayerState,
    ball_target: Vector2,
    lane_y: float,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Shift an unassigned defender without abandoning the danger corridor.

    In deeper areas, lateral formation lanes preserve width. Once the threat is
    advanced, blindly preserving a wide lane can make a weak-side defender run
    away from an incoming receiver and then reverse toward goal on the shot.
    Final-third defenders therefore compress toward the defended goal corridor,
    and their assigned target may never widen their current lateral separation
    from that corridor.
    """
    team = state.teams_by_id[defender.team_id]
    goal = state.goals_by_id[team.defended_goal_id]
    attacking_team = next(
        candidate
        for candidate in state.teams_by_id.values()
        if candidate.id != defender.team_id
    )
    target_lane_y = lane_y
    if (
        _attacking_progress_ratio(state, attacking_team.id, ball_target)
        >= policy.threat_aware_shape_progress_ratio
    ):
        compressed_lane_y = (
            lane_y * (1 - policy.threat_aware_corridor_weight)
            + goal.center.y * policy.threat_aware_corridor_weight
        )
        # Compression must improve or retain corridor coverage. This explicit
        # clamp protects against an unoccupied formation lane lying even wider
        # than the defender's current weak-side position.
        target_lane_y = (
            compressed_lane_y
            if abs(compressed_lane_y - goal.center.y)
            <= abs(defender.position.y - goal.center.y)
            else defender.position.y
        )
    current_weight = 1 - (
        policy.hold_shape_ball_weight + policy.hold_shape_goal_weight
    )
    shape_anchor = Vector2(
        x=(
            defender.position.x * current_weight
            + ball_target.x * policy.hold_shape_ball_weight
            + goal.center.x * policy.hold_shape_goal_weight
        ),
        y=target_lane_y,
    )
    return _bounded_target(
        state,
        move_toward(
            defender.position,
            shape_anchor,
            policy.maximum_hold_shape_shift_cm,
        ),
    )


def _goal_side_cover_target(
    state: GameState,
    defending_team_id: str,
    threat: Vector2,
    policy: PhaseGenerationPolicy,
) -> Vector2:
    """Place the covering defender between the threat and the defended goal."""
    goal = state.goals_by_id[state.teams_by_id[defending_team_id].defended_goal_id]
    return move_toward(threat, goal.center, policy.goal_side_cover_distance_cm)


def _is_effective_goal_side_cover(
    state: GameState,
    attacking_team_id: str,
    threat: Vector2,
    position: Vector2,
    policy: PhaseGenerationPolicy,
) -> bool:
    """Return whether a position protects a deep, central route to goal.

    Merely being a few centimeters beyond the carrier is not meaningful cover,
    and a defender isolated near the opposite touchline cannot protect the
    shooting corridor. Both depth and lateral proximity are therefore required.
    """
    threat_progress = _target_progress(state, attacking_team_id, threat)
    defender_progress = _target_progress(state, attacking_team_id, position)
    return (
        defender_progress
        >= threat_progress + policy.minimum_cover_depth_cm
        and abs(position.y - threat.y) <= policy.central_cover_half_width_cm
    )


def _decoy_tracking_preserves_cover(
    state: GameState,
    attacking_team_id: str,
    outfield_defenders: tuple[PlayerState, ...],
    presser_id: str | None,
    tracker_id: str,
    threat: Vector2,
    decoy_target: Vector2,
    policy: PhaseGenerationPolicy,
) -> bool:
    """Allow a marker to follow a decoy only when central cover survives.

    The attacking planner must not be able to choose a defensive mistake as an
    offensive branch. If the tracker would leave the protected corridor, some
    other non-pressing outfield defender must already provide effective cover;
    otherwise the correct response is to hand off the decoy and protect goal.
    """
    if _is_effective_goal_side_cover(
        state,
        attacking_team_id,
        threat,
        decoy_target,
        policy,
    ):
        return True
    return any(
        defender.id not in {presser_id, tracker_id}
        and _is_effective_goal_side_cover(
            state,
            attacking_team_id,
            threat,
            defender.position,
            policy,
        )
        for defender in outfield_defenders
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
    """Build one coordinated off-ball unit for a dribble.

    The returned intentions belong in the same phase. Earlier versions returned
    the same flat collection but treated each item as an alternative phase,
    leaving only one purposeful runner while everyone else shifted generically.
    """
    support_target = _support_target(
        state,
        teammates[0].team_id,
        destination,
        policy.support_offset_cm,
    )
    team_id = teammates[0].team_id
    attacking_goal = state.goals_by_id[state.teams_by_id[team_id].attacking_goal_id]
    attacking_progress_ratio = _attacking_progress_ratio(
        state,
        team_id,
        destination,
    )
    is_final_third = (
        attacking_progress_ratio >= policy.crossing_trigger_progress_ratio
    )
    is_wide = (
        destination.y <= state.field.width * policy.crossing_wide_channel_ratio
        or destination.y
        >= state.field.width * (1 - policy.crossing_wide_channel_ratio)
    )
    crossing_attack = is_final_third and is_wide

    if crossing_attack:
        direction = state.teams_by_id[team_id].attacking_direction
        box_x = (
            attacking_goal.center.x - policy.crossing_box_depth_cm
            if direction == AttackingDirection.POSITIVE_X
            else attacking_goal.center.x + policy.crossing_box_depth_cm
        )
        low_post_y = (
            attacking_goal.bottom_left.y + policy.crossing_post_inset_cm
        )
        high_post_y = (
            attacking_goal.top_right.y - policy.crossing_post_inset_cm
        )
        # Preserve natural lanes: a low-side carrier offers near post first and
        # far post second; a high-side carrier reverses that ordering.
        post_targets = (
            (Vector2(box_x, low_post_y), Vector2(box_x, high_post_y))
            if destination.y <= attacking_goal.center.y
            else (Vector2(box_x, high_post_y), Vector2(box_x, low_post_y))
        )
        forward_targets = [_bounded_target(state, target) for target in post_targets]
    else:
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
    if not crossing_attack:
        forward_targets.extend(
            zone.center
            for zone in dynamic_spaces[: policy.maximum_dynamic_support_spaces]
        )
    forward_targets = list(dict.fromkeys(forward_targets))

    intentions: list[AttackingIntention] = []
    assigned = set(excluded)
    if crossing_attack:
        # Box arrivals are time-critical, so choose both runners before assigning
        # the safer behind-ball support role. This lets two teammates attack a
        # potential cross concurrently instead of sacrificing one as support.
        for runner, target in _assign_forward_runs(
            state,
            teammates,
            tuple(forward_targets),
            assigned,
        ):
            assigned.add(runner.id)
            intentions.append(
                AttackingIntention(
                    player_id=runner.id,
                    intention_type=AttackingIntentionType.FORWARD_RUN,
                    target=target,
                    start_offset_seconds=policy.support_reaction_seconds,
                )
            )
    elif attacking_progress_ratio >= policy.width_provider_progress_ratio:
        # A central carrier does not trigger the crossing template, but the
        # attack should still stretch the block. Reserve the naturally widest
        # teammate before support and box lanes are allocated so arrival-time
        # matching cannot pull that player back toward the ball.
        available = tuple(player for player in teammates if player.id not in assigned)
        width_provider = max(
            available,
            key=lambda player: (
                abs(player.position.y - state.field.width / 2),
                player.speed_category.multiplier,
                player.id,
            ),
            default=None,
        )
        if width_provider is not None:
            assigned.add(width_provider.id)
            intentions.append(
                AttackingIntention(
                    player_id=width_provider.id,
                    intention_type=AttackingIntentionType.FORWARD_RUN,
                    target=_width_provider_target(state, width_provider, policy),
                    start_offset_seconds=policy.support_reaction_seconds,
                )
            )
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
    if not crossing_attack:
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
                    # Retain a runner's natural width when the generic lane is
                    # closer to the carrier than the runner's current lane.
                    target=_preserve_natural_width(state, runner, target),
                    start_offset_seconds=policy.support_reaction_seconds,
                )
            )
    return tuple(intentions)


def _shot_attacking_intentions(
    state: GameState,
    teammates: tuple[PlayerState, ...],
    actor_id: str,
    policy: PhaseGenerationPolicy,
) -> tuple[AttackingIntention, ...]:
    """Assign two rebound runs and preserve one player behind the shot.

    Generic SHIFT_WITH_PLAY pulls every teammate toward the shooter. A shot has
    different needs: near/far-post rebound occupation plus one rest-defense
    player who remains available against a clearance or counterattack.
    """
    available = tuple(
        player
        for player in teammates
        if player.id != actor_id and not is_goalkeeper(player)
    )
    if not available:
        return ()
    attacking_team_id = state.players_by_id[actor_id].team_id
    team = state.teams_by_id[attacking_team_id]
    goal = state.goals_by_id[team.attacking_goal_id]
    rebound_x = (
        goal.center.x - policy.shot_rebound_depth_cm
        if team.attacking_direction == AttackingDirection.POSITIVE_X
        else goal.center.x + policy.shot_rebound_depth_cm
    )
    rebound_targets = (
        Vector2(rebound_x, goal.bottom_left.y + policy.shot_rebound_post_inset_cm),
        Vector2(rebound_x, goal.top_right.y - policy.shot_rebound_post_inset_cm),
    )

    # Keep the deepest teammate as rest defense. The remaining players are
    # matched jointly to the two rebound lanes to avoid unnecessary crossing.
    rest_defender = min(
        available,
        key=lambda player: (_progress(state, player), player.id),
    )
    assigned = {actor_id, rest_defender.id}
    intentions = [
        AttackingIntention(
            player_id=rest_defender.id,
            intention_type=AttackingIntentionType.HOLD_POSITION,
            target=rest_defender.position,
            start_offset_seconds=0,
        )
    ]
    intentions.extend(
        AttackingIntention(
            player_id=runner.id,
            intention_type=AttackingIntentionType.FORWARD_RUN,
            target=target,
            start_offset_seconds=policy.shot_rebound_reaction_seconds,
        )
        for runner, target in _assign_forward_runs(
            state,
            available,
            rebound_targets,
            assigned,
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
        # A shot blocker aims at an early point on the trajectory, not the goal
        # endpoint. The presser owns the shooter; the second
        # defender owns an early segment of the shot line, producing a distinct
        # blocking angle instead of duplicating pressure at the ball.
        if action.action_type == ActionType.SHOT:
            tracker_target = Vector2(
                action.start.x
                + (action.destination.x - action.start.x)
                * policy.shot_secondary_block_fraction,
                action.start.y
                + (action.destination.y - action.start.y)
                * policy.shot_secondary_block_fraction,
            )
            tracker = _nearest(
                tuple(
                    defender
                    for defender in outfield_defenders
                    if presser is None or defender.id != presser.id
                ),
                tracker_target,
            )
        elif action.action_type == ActionType.MOVE_WITH_BALL and outfield_defenders:
            tracker_target = _goal_side_cover_target(
                state,
                outfield_defenders[0].team_id,
                action.destination,
                policy,
            )
            tracker = _nearest(
                outfield_defenders,
                tracker_target,
                {presser.id} if presser else set(),
            )
        else:
            tracker_target = action.destination
            tracker = _nearest(
                outfield_defenders,
                tracker_target,
                {presser.id} if presser else set(),
            )
        attacking: list[AttackingIntention] = []
        defensive: list[DefensiveIntention] = []

        if action.action_type == ActionType.PASS_TO_SPACE and action.receiver_id:
            receiver_run_time = action.metrics.receiver_arrival_time_seconds or 0
            ball_travel_time = (
                action.metrics.ball_travel_duration_seconds
                or action.metrics.duration_seconds
            )
            attacking.append(
                AttackingIntention(
                    player_id=action.receiver_id,
                    intention_type=AttackingIntentionType.RECEIVE_IN_SPACE,
                    target=action.destination,
                    # Delay a shorter run so receiver and ball reach the target
                    # together. If the run would take longer than ball travel,
                    # pass analysis rejects the candidate rather than adding a
                    # visible stationary hold after the passer receives.
                    start_offset_seconds=max(
                        0,
                        ball_travel_time - receiver_run_time,
                    ),
                    required_arrival_seconds=ball_travel_time,
                )
            )
            template = PhaseTemplateType.PASS_INTO_SPACE
        elif action.action_type == ActionType.PASS_TO_PLAYER:
            template = PhaseTemplateType.DIRECT_PASS
        elif action.action_type == ActionType.MOVE_WITH_BALL:
            template = PhaseTemplateType.DRIBBLE_WITH_SUPPORT
        else:
            template = PhaseTemplateType.SHOT

        attacking_role_variants: tuple[tuple[AttackingIntention, ...], ...] = ((),)
        if template == PhaseTemplateType.DRIBBLE_WITH_SUPPORT:
            coordinated_roles = _dribble_support_intentions(
                state,
                outfield_teammates,
                excluded_attackers,
                action.destination,
                policy,
            )
            attacking_role_variants = (coordinated_roles,)
        elif support is not None and template != PhaseTemplateType.SHOT:
            attacking_role_variants = (
                (
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
                ),
            )
        elif template == PhaseTemplateType.SHOT:
            attacking_role_variants = (
                _shot_attacking_intentions(
                    state,
                    outfield_teammates,
                    actor.id,
                    policy,
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
            if template == PhaseTemplateType.SHOT:
                tracker_intention = DefensiveIntentionType.COVER_GOAL
            elif template == PhaseTemplateType.DRIBBLE_WITH_SUPPORT:
                tracker_intention = DefensiveIntentionType.COVER_PASSING_LANE
            else:
                tracker_intention = DefensiveIntentionType.TRACK_RECEIVER
            defensive.append(
                DefensiveIntention(
                    player_id=tracker.id,
                    intention_type=tracker_intention,
                    target=tracker_target,
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
        for coordinated_roles in attacking_role_variants:
            base_attacking = (*attacking, *coordinated_roles)
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
                    if _decoy_tracking_preserves_cover(
                        state,
                        actor.team_id,
                        outfield_defenders,
                        presser.id if presser else None,
                        tracker.id,
                        action.destination,
                        decoy_intention.target,
                        policy,
                    ):
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
