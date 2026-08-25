from dataclasses import dataclass

from app.analysis import ActionType
from app.domain import PlayerState, PossessionStatus, TargetZoneSource, is_goalkeeper
from app.spatial import distance, distance_to_goal
from app.phases.models import PhaseSimulationResult, TacticalPhase


@dataclass(frozen=True, slots=True)
class PhaseScoringPolicy:
    """Explainable weights for ranking valid simulated tactical phases.

    These weights affect preference, not physical validity. Goal reward is large
    enough that a valid scoring branch ranks above ordinary field progression.
    """
    forward_progress_weight: float = 35
    goal_proximity_weight: float = 25
    possession_weight: float = 30
    coordination_weight: float = 8
    attacking_width_weight: float = 6
    close_spacing_penalty_weight: float = 5
    minimum_attacking_spacing_cm: float = 800
    duration_penalty_weight: float = 8
    # Repeating a short dribble can otherwise collect forward/proximity reward
    # at every beam depth even when the tactical picture barely changes.
    consecutive_dribble_penalty: float = 12
    # A direction change or a different primary presser is a real tactical
    # response, so retain only this fraction of the repetition penalty.
    meaningful_dribble_change_penalty_ratio: float = 0.25
    dribble_inside_open_space_reward: float = 10
    dribble_near_open_space_reward: float = 5
    dribble_near_open_space_distance_cm: float = 700
    pressured_non_space_dribble_penalty: float = 10
    dribble_pressure_distance_cm: float = 1000
    dribble_exception_forward_progress_cm: float = 1200
    dribble_exception_channel_change_cm: float = 1200
    dribble_exception_shooting_range_cm: float = 2468.88
    dribble_exception_escape_distance_gain_cm: float = 300
    goal_reward: float = 1000
    tactical_preference_weight: float = 12
    preferred_space_weight: float = 250
    preferred_action_types: tuple[str, ...] = ()
    preferred_player_ids: tuple[str, ...] = ()
    preferred_space_ids: tuple[str, ...] = ()
    preferred_off_ball_intentions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseScore:
    """Additive component breakdown used to explain a phase's total score."""
    phase: TacticalPhase
    simulation: PhaseSimulationResult
    forward_progress: float
    goal_proximity: float
    possession: float
    coordination: float
    duration_penalty: float
    goal: float
    tactical_preference: float = 0
    sequence_adjustment: float = 0
    dribble_space: float = 0

    @property
    def total(self) -> float:
        return (
            self.forward_progress
            + self.goal_proximity
            + self.possession
            + self.coordination
            + self.duration_penalty
            + self.goal
            + self.tactical_preference
            + self.sequence_adjustment
            + self.dribble_space
        )


def consecutive_dribble_adjustment(
    previous_phase: TacticalPhase | None,
    current_phase: TacticalPhase,
    policy: PhaseScoringPolicy = PhaseScoringPolicy(),
) -> float:
    """Return a history-aware penalty for repetitive carrier progression.

    Per-phase scoring cannot see the preceding beam edge. This small sequence
    term prevents a carrier from farming progress reward through many nearly
    identical short primitives. A changed dribble direction or pressing
    defender indicates a new tactical problem and therefore receives only a
    reduced penalty rather than being treated as duplicate play.
    """
    if previous_phase is None:
        return 0
    previous_action = previous_phase.primary_action
    current_action = current_phase.primary_action
    if (
        previous_action.action_type != ActionType.MOVE_WITH_BALL
        or current_action.action_type != ActionType.MOVE_WITH_BALL
        or previous_action.actor_id != current_action.actor_id
    ):
        return 0

    previous_pressers = {
        intention.player_id
        for intention in previous_phase.defensive_intentions
        if intention.intention_type.value == "PRESS_BALL_CARRIER"
    }
    current_pressers = {
        intention.player_id
        for intention in current_phase.defensive_intentions
        if intention.intention_type.value == "PRESS_BALL_CARRIER"
    }
    direction_changed = (
        previous_action.source_analysis.dribble_direction
        != current_action.source_analysis.dribble_direction
    )
    presser_changed = previous_pressers != current_pressers
    ratio = (
        policy.meaningful_dribble_change_penalty_ratio
        if direction_changed or presser_changed
        else 1
    )
    return -policy.consecutive_dribble_penalty * ratio


def _distance_from_dynamic_space(state, team_id: str, point) -> float | None:
    """Return distance beyond the nearest circle edge; zero means inside."""
    spaces = tuple(
        zone
        for zone in state.target_zones_by_id.values()
        if zone.source == TargetZoneSource.DYNAMIC
        and zone.attacking_team_id == team_id
    )
    if not spaces:
        return None
    return min(
        max(0, distance(point, zone.center) - (zone.radius or 0))
        for zone in spaces
    )


def _dribble_escapes_primary_pressure(simulation: PhaseSimulationResult, policy) -> bool:
    """Detect whether the selected dribble materially increases presser space."""
    phase = simulation.phase
    presser_id = next(
        (
            intention.player_id
            for intention in phase.defensive_intentions
            if intention.intention_type.value == "PRESS_BALL_CARRIER"
        ),
        None,
    )
    if presser_id is None:
        return False
    actor_id = phase.primary_action.actor_id
    before = simulation.previous_state
    after = simulation.resulting_state
    initial_gap = distance(
        before.players_by_id[actor_id].position,
        before.players_by_id[presser_id].position,
    )
    resulting_gap = distance(
        after.players_by_id[actor_id].position,
        after.players_by_id[presser_id].position,
    )
    return (
        resulting_gap - initial_gap
        >= policy.dribble_exception_escape_distance_gain_cm
    )


def _dribble_has_tactical_exception(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> bool:
    """Allow useful non-space dribbles that alter the tactical problem."""
    phase = simulation.phase
    action = phase.primary_action
    before = simulation.previous_state
    actor = before.players_by_id[action.actor_id]
    goal = before.goals_by_id[before.teams_by_id[actor.team_id].attacking_goal_id]
    enters_shooting_range = (
        distance_to_goal(actor.position, goal)
        > policy.dribble_exception_shooting_range_cm
        and distance_to_goal(action.destination, goal)
        <= policy.dribble_exception_shooting_range_cm
    )
    return any(
        (
            action.metrics.forward_progress_cm
            >= policy.dribble_exception_forward_progress_cm,
            abs(action.destination.y - actor.position.y)
            >= policy.dribble_exception_channel_change_cm,
            enters_shooting_range,
            _dribble_escapes_primary_pressure(simulation, policy),
        )
    )


def _dribble_space_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward intentional use of space and penalize pressured arbitrary endpoints."""
    phase = simulation.phase
    action = phase.primary_action
    if action.action_type != ActionType.MOVE_WITH_BALL:
        return 0
    edge_distance = _distance_from_dynamic_space(
        simulation.previous_state,
        phase.attacking_team_id,
        action.destination,
    )
    if edge_distance == 0:
        return policy.dribble_inside_open_space_reward
    if (
        edge_distance is not None
        and edge_distance <= policy.dribble_near_open_space_distance_cm
    ):
        proximity = 1 - edge_distance / policy.dribble_near_open_space_distance_cm
        return policy.dribble_near_open_space_reward * proximity

    defenders = tuple(
        player
        for player in simulation.resulting_state.players_by_id.values()
        if player.team_id != phase.attacking_team_id
    )
    nearest_defender = min(
        (distance(action.destination, defender.position) for defender in defenders),
        default=float("inf"),
    )
    if (
        nearest_defender <= policy.dribble_pressure_distance_cm
        and not _dribble_has_tactical_exception(simulation, policy)
    ):
        return -policy.pressured_non_space_dribble_penalty
    return 0


def _forward_progress_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward movement in the attacking direction, capped to one field length."""
    action = simulation.phase.primary_action
    field_length = simulation.resulting_state.field.length
    progress_ratio = max(
        -1,
        min(1, action.metrics.forward_progress_cm / field_length),
    )
    return progress_ratio * policy.forward_progress_weight


def _goal_proximity_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward improvement in goal distance, capped to one field length."""
    action = simulation.phase.primary_action
    field_length = simulation.resulting_state.field.length
    proximity_ratio = max(
        -1,
        min(1, action.metrics.goal_proximity_improvement_cm / field_length),
    )
    return proximity_ratio * policy.goal_proximity_weight


def _possession_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward retained attacking control and penalize every other outcome."""
    possession = simulation.resulting_state.possession
    retains_control = (
        possession.status == PossessionStatus.CONTROLLED
        and possession.team_id == simulation.phase.attacking_team_id
    )
    return policy.possession_weight if retains_control else -policy.possession_weight


def _assigned_intentions_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward phases that coordinate up to four attacking/defensive intentions."""
    phase = simulation.phase
    coordination_count = len(phase.attacking_intentions) + len(
        phase.defensive_intentions
    )
    return min(1, coordination_count / 4) * policy.coordination_weight


def _support_quality_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward the best non-receiver support lane for clearance and separation."""
    phase = simulation.phase
    state = simulation.resulting_state
    defenders = tuple(
        player
        for player in state.players_by_id.values()
        if player.team_id != phase.attacking_team_id
    )
    best_support_quality = 0.0
    for intention in phase.attacking_intentions:
        if intention.player_id == phase.primary_action.receiver_id:
            continue
        support_position = state.players_by_id[intention.player_id].position
        clearance = min(
            (distance(support_position, defender.position) for defender in defenders),
            default=1500,
        )
        lateral_separation = abs(
            support_position.y - phase.primary_action.destination.y
        )
        best_support_quality = max(
            best_support_quality,
            0.6 * min(1, clearance / 1500)
            + 0.4 * min(1, lateral_separation / 1200),
        )
    return best_support_quality * policy.coordination_weight


def _outfield_attackers(
    simulation: PhaseSimulationResult,
) -> tuple[PlayerState, ...]:
    """Return attacking outfield players used by width and spacing scenarios."""
    phase = simulation.phase
    return tuple(
        player
        for player in simulation.resulting_state.players_by_id.values()
        if player.team_id == phase.attacking_team_id and not is_goalkeeper(player)
    )


def _attacking_width_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward the fraction of field width occupied by attacking outfielders."""
    attackers = _outfield_attackers(simulation)
    if len(attackers) <= 1:
        return 0
    width = max(player.position.y for player in attackers) - min(
        player.position.y for player in attackers
    )
    return (
        width
        / simulation.resulting_state.field.width
        * policy.attacking_width_weight
    )


def _close_spacing_penalty(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Penalize pairs of attackers that finish without distinct passing lanes."""
    attackers = _outfield_attackers(simulation)
    close_pairs = sum(
        1
        for index, player in enumerate(attackers)
        for teammate in attackers[index + 1 :]
        if distance(player.position, teammate.position)
        < policy.minimum_attacking_spacing_cm
    )
    return -close_pairs * policy.close_spacing_penalty_weight


def _coordination_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Combine intention, support-lane, width, and close-spacing scenarios."""
    return (
        _assigned_intentions_score(simulation, policy)
        + _support_quality_score(simulation, policy)
        + _attacking_width_score(simulation, policy)
        + _close_spacing_penalty(simulation, policy)
    )


def _duration_penalty(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Penalize elapsed phase time, with the penalty capped at 12 seconds."""
    return -policy.duration_penalty_weight * min(
        1,
        simulation.phase.duration_seconds / 12,
    )


def _goal_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Apply the terminal reward only when the attacking team scored."""
    scored = (
        simulation.resulting_state.scoring_team_id
        == simulation.phase.attacking_team_id
    )
    return policy.goal_reward if scored else 0


def _tactical_preference_score(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy,
) -> float:
    """Reward configured action, player, space, and off-ball preferences."""
    phase = simulation.phase
    action = phase.primary_action
    preference_checks: list[bool] = []
    if policy.preferred_action_types:
        preference_checks.append(action.action_type.value in policy.preferred_action_types)
    if policy.preferred_player_ids:
        involved_players = {
            action.actor_id,
            action.receiver_id,
            *(intention.player_id for intention in phase.attacking_intentions),
        }
        preference_checks.append(
            bool(involved_players.intersection(policy.preferred_player_ids))
        )
    if policy.preferred_off_ball_intentions:
        intention_types = {
            intention.intention_type.value for intention in phase.attacking_intentions
        }
        preference_checks.append(
            bool(intention_types.intersection(policy.preferred_off_ball_intentions))
        )

    score = (
        sum(preference_checks) / len(preference_checks)
        * policy.tactical_preference_weight
        if preference_checks
        else 0
    )
    if (
        policy.preferred_space_ids
        and action.target_zone_id in policy.preferred_space_ids
    ):
        score += policy.preferred_space_weight
    return score


def score_phase_result(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy = PhaseScoringPolicy(),
) -> PhaseScore:
    """Assemble the independently calculated scenarios into one phase score."""
    phase = simulation.phase
    return PhaseScore(
        phase=phase,
        simulation=simulation,
        forward_progress=_forward_progress_score(simulation, policy),
        goal_proximity=_goal_proximity_score(simulation, policy),
        possession=_possession_score(simulation, policy),
        coordination=_coordination_score(simulation, policy),
        duration_penalty=_duration_penalty(simulation, policy),
        goal=_goal_score(simulation, policy),
        tactical_preference=_tactical_preference_score(simulation, policy),
        dribble_space=_dribble_space_score(simulation, policy),
    )
