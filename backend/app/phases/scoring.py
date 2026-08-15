from dataclasses import dataclass

from app.analysis import ActionType
from app.domain import PossessionStatus
from app.spatial import distance, distance_to_goal
from app.phases.models import PhaseSimulationResult, TacticalPhase


@dataclass(frozen=True, slots=True)
class PhaseScoringPolicy:
    forward_progress_weight: float = 35
    goal_proximity_weight: float = 25
    possession_weight: float = 30
    coordination_weight: float = 8
    duration_penalty_weight: float = 8
    goal_reward: float = 1000
    tactical_preference_weight: float = 12
    preferred_space_weight: float = 250
    preferred_action_types: tuple[str, ...] = ()
    preferred_player_ids: tuple[str, ...] = ()
    preferred_space_ids: tuple[str, ...] = ()
    preferred_off_ball_intentions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseScore:
    phase: TacticalPhase
    simulation: PhaseSimulationResult
    forward_progress: float
    goal_proximity: float
    possession: float
    coordination: float
    duration_penalty: float
    goal: float
    tactical_preference: float = 0

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
        )


def score_phase_result(
    simulation: PhaseSimulationResult,
    policy: PhaseScoringPolicy = PhaseScoringPolicy(),
) -> PhaseScore:
    phase = simulation.phase
    state = simulation.resulting_state
    action = phase.primary_action
    field_length = state.field.length
    forward = max(-1, min(1, action.metrics.forward_progress_cm / field_length))
    proximity = max(
        -1,
        min(1, action.metrics.goal_proximity_improvement_cm / field_length),
    )
    possession = state.possession
    retains = (
        possession.status == PossessionStatus.CONTROLLED
        and possession.team_id == phase.attacking_team_id
    )
    coordination_count = len(phase.attacking_intentions) + len(phase.defensive_intentions)
    defenders = tuple(
        player
        for player in state.players_by_id.values()
        if player.team_id != phase.attacking_team_id
    )
    support_quality = 0.0
    for intention in phase.attacking_intentions:
        if intention.player_id == action.receiver_id:
            continue
        support_position = state.players_by_id[intention.player_id].position
        clearance = min(
            (distance(support_position, defender.position) for defender in defenders),
            default=1500,
        )
        lateral_separation = abs(support_position.y - action.destination.y)
        support_quality = max(
            support_quality,
            0.6 * min(1, clearance / 1500)
            + 0.4 * min(1, lateral_separation / 1200),
        )
    scored = state.scoring_team_id == phase.attacking_team_id
    preference_checks: list[bool] = []
    if policy.preferred_action_types:
        preference_checks.append(action.action_type.value in policy.preferred_action_types)
    if policy.preferred_player_ids:
        involved_players = {
            action.actor_id,
            action.receiver_id,
            *(intention.player_id for intention in phase.attacking_intentions),
        }
        preference_checks.append(bool(involved_players.intersection(policy.preferred_player_ids)))
    targets_preferred_space = (
        bool(policy.preferred_space_ids)
        and action.target_zone_id in policy.preferred_space_ids
    )
    if policy.preferred_off_ball_intentions:
        intention_types = {
            intention.intention_type.value
            for intention in phase.attacking_intentions
        }
        preference_checks.append(
            bool(intention_types.intersection(policy.preferred_off_ball_intentions))
        )
    tactical_preference = (
        sum(preference_checks) / len(preference_checks)
        * policy.tactical_preference_weight
        if preference_checks else 0
    )
    if targets_preferred_space:
        tactical_preference += policy.preferred_space_weight
    return PhaseScore(
        phase=phase,
        simulation=simulation,
        forward_progress=forward * policy.forward_progress_weight,
        goal_proximity=proximity * policy.goal_proximity_weight,
        possession=policy.possession_weight if retains else -policy.possession_weight,
        coordination=(
            min(1, coordination_count / 4) * policy.coordination_weight
            + support_quality * policy.coordination_weight
        ),
        duration_penalty=-policy.duration_penalty_weight * min(
            1, phase.duration_seconds / 12
        ),
        goal=policy.goal_reward if scored else 0,
        tactical_preference=tactical_preference,
    )
