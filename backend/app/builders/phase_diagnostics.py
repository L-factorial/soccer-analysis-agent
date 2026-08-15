from collections import Counter

from app.domain import TargetZoneSource
from app.models.animation_response import (
    DynamicSpaceDiagnostic,
    PhaseIntentionDiagnostic,
    PlannerDiagnostics,
    SelectedPhaseDiagnostic,
)
from app.models.position import Position
from app.phases import PhaseSearchNode, PhaseSearchResult
from app.phases import check_phase_offside


def build_phase_planner_diagnostics(
    result: PhaseSearchResult,
    selected: PhaseSearchNode | None = None,
) -> PlannerDiagnostics:
    root = result.root
    rejection_reasons = Counter(
        issue
        for candidate in root.action_candidates.rejected
        for issue in candidate.issue_codes
    )
    if result.diagnostics.invalid_phase_count:
        rejection_reasons["invalid_tactical_phase"] = result.diagnostics.invalid_phase_count
    if result.diagnostics.pruned_by_offside_count:
        rejection_reasons["offside"] = result.diagnostics.pruned_by_offside_count
    rejection_reasons.update(dict(result.diagnostics.invalid_issue_counts))
    spaces = tuple(
        DynamicSpaceDiagnostic(
            id=zone.id,
            center=Position(x=zone.center.x, y=zone.center.y),
            radius=zone.radius or 0,
        )
        for zone in root.game_state.target_zones_by_id.values()
        if zone.source == TargetZoneSource.DYNAMIC
    )
    explanation = [f"Computed {len(spaces)} dynamic open-space candidates"]
    if selected is None:
        explanation.append("No tactical-phase sequence reached a validated goal")
    else:
        explanation.append(
            f"Selected {selected.depth} coordinated tactical phases ending in a goal"
        )
        explanation.extend(
            f"{step.phase.template_type.value}: {step.phase.primary_action.actor_id}"
            for step in selected.steps
        )
    diagnostics = result.diagnostics
    selected_phases: list[SelectedPhaseDiagnostic] = []
    phase_start = 0.0
    if selected is not None:
        for step in selected.steps:
            phase = step.phase
            simulation = step.simulation
            action = phase.primary_action
            intentions = tuple(
                PhaseIntentionDiagnostic(
                    side="ATTACKING",
                    player_id=intention.player_id,
                    intention_type=intention.intention_type.value,
                    target=Position(x=intention.target.x, y=intention.target.y),
                )
                for intention in phase.attacking_intentions
            ) + tuple(
                PhaseIntentionDiagnostic(
                    side="DEFENSIVE",
                    player_id=intention.player_id,
                    intention_type=intention.intention_type.value,
                    target=Position(x=intention.target.x, y=intention.target.y),
                    target_player_id=intention.target_player_id,
                )
                for intention in phase.defensive_intentions
            )
            phase_end = phase_start + phase.duration_seconds
            offside = check_phase_offside(simulation.previous_state, phase)
            selected_phases.append(
                SelectedPhaseDiagnostic(
                    id=phase.id,
                    phase_type=phase.template_type.value,
                    action_type=action.action_type.value,
                    actor_id=action.actor_id,
                    receiver_id=action.receiver_id,
                    target_zone_id=action.target_zone_id,
                    target=Position(
                        x=action.destination.x,
                        y=action.destination.y,
                    ),
                    start_time=round(phase_start, 6),
                    duration=round(phase.duration_seconds, 6),
                    end_time=round(phase_end, 6),
                    ball_action_start_time=round(
                        phase_start + phase.ball_action_start_offset_seconds, 6
                    ),
                    offside_line_x=offside.offside_line_x,
                    possession_before=(
                        simulation.previous_state.possession.status.value
                    ),
                    possession_after=(
                        simulation.resulting_state.possession.status.value
                    ),
                    score=round(step.score.total, 6),
                    scored_goal=(
                        simulation.resulting_state.scored_goal_id is not None
                    ),
                    intentions=intentions,
                )
            )
            phase_start = phase_end
    return PlannerDiagnostics(
        planner_type="TACTICAL_PHASE",
        phase_count=selected.depth if selected else None,
        attacking_team_id=root.game_state.possession.team_id,
        reached_depth=diagnostics.reached_depth,
        evaluated_candidate_count=diagnostics.simulated_phase_count,
        root_candidate_count=root.diagnostics.candidate_count,
        root_feasible_candidate_count=root.diagnostics.feasible_candidate_count,
        pruned_by_beam_count=diagnostics.pruned_by_beam_count,
        pruned_by_duration_count=diagnostics.pruned_by_duration_count,
        pruned_by_offside_count=diagnostics.pruned_by_offside_count,
        pruned_by_possession_count=0,
        pruned_by_action_pattern_count=0,
        rejection_reasons=dict(sorted(rejection_reasons.items())),
        dynamic_spaces=spaces,
        selected_sequence_score=round(selected.cumulative_score, 6) if selected else None,
        selected_sequence_depth=selected.depth if selected else None,
        selected_phases=tuple(selected_phases),
        explanation=tuple(explanation),
    )
