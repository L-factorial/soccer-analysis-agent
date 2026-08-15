from collections import Counter

from app.domain import TargetZoneSource
from app.models.animation_response import DynamicSpaceDiagnostic, PlannerDiagnostics
from app.models.position import Position
from app.planning import SearchResult, SearchSequence


def build_planner_diagnostics(
    result: SearchResult,
    selected: SearchSequence | None = None,
) -> PlannerDiagnostics:
    root = result.root
    rejection_reasons = Counter(
        issue_code
        for candidate in root.action_candidates.rejected
        for issue_code in candidate.issue_codes
    )
    dynamic_spaces = tuple(
        DynamicSpaceDiagnostic(
            id=zone.id,
            center=Position(x=zone.center.x, y=zone.center.y),
            radius=zone.radius or 0,
        )
        for zone in root.game_state.target_zones_by_id.values()
        if zone.source == TargetZoneSource.DYNAMIC
    )
    explanation: list[str] = []
    if dynamic_spaces:
        explanation.append(
            f"Computed {len(dynamic_spaces)} dynamic open-space candidates"
        )
    if selected is not None:
        explanation.append(
            f"Selected a {selected.depth}-action sequence ending in a goal"
        )
        explanation.extend(
            f"{step.candidate.action_type.value} by {step.candidate.actor_id}"
            for step in selected.steps
        )
    else:
        explanation.append(
            "No retained sequence reached a validated goal state"
        )

    diagnostics = result.diagnostics
    return PlannerDiagnostics(
        attacking_team_id=root.game_state.possession.team_id,
        reached_depth=diagnostics.reached_depth,
        evaluated_candidate_count=diagnostics.evaluated_child_count,
        root_candidate_count=root.diagnostics.candidate_count,
        root_feasible_candidate_count=root.diagnostics.feasible_candidate_count,
        pruned_by_beam_count=diagnostics.pruned_by_beam_count,
        pruned_by_duration_count=diagnostics.pruned_by_duration_count,
        pruned_by_possession_count=diagnostics.pruned_by_possession_count,
        pruned_by_action_pattern_count=(
            diagnostics.pruned_by_action_pattern_count
        ),
        rejection_reasons=dict(sorted(rejection_reasons.items())),
        dynamic_spaces=dynamic_spaces,
        selected_sequence_score=(
            round(selected.cumulative_score, 6) if selected is not None else None
        ),
        selected_sequence_depth=selected.depth if selected is not None else None,
        explanation=tuple(explanation),
    )
