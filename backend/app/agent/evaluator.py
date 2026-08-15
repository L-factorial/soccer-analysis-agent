from app.agent.models import PlanEvaluation, TacticalIntent
from app.phases import PhaseSearchNode, PhaseSearchResult


def best_scoring_sequence(result: PhaseSearchResult) -> PhaseSearchNode | None:
    team_id = result.root.game_state.possession.team_id
    return next(
        (
            node for node in result.best_sequences
            if node.analyzed_state.game_state.scoring_team_id == team_id
        ),
        None,
    )


def evaluate_plan(
    result: PhaseSearchResult,
    intent: TacticalIntent,
) -> PlanEvaluation:
    selected = best_scoring_sequence(result)
    if selected is None:
        return PlanEvaluation(
            goalScored=False,
            instructionAlignment=0,
            reasons=["No legal goal-scoring sequence was found."],
        )
    actions = {step.phase.primary_action.action_type.value for step in selected.steps}
    target_spaces = {
        step.phase.primary_action.target_zone_id
        for step in selected.steps
        if step.phase.primary_action.target_zone_id is not None
    }
    involved_players = {
        player_id
        for step in selected.steps
        for player_id in (
            step.phase.primary_action.actor_id,
            step.phase.primary_action.receiver_id,
            *(intention.player_id for intention in step.phase.attacking_intentions),
        )
        if player_id is not None
    }
    intentions = {
        intention.intention_type.value
        for step in selected.steps
        for intention in step.phase.attacking_intentions
    }
    checks: list[bool] = []
    if intent.preferred_action_types:
        checks.append(bool(actions.intersection(intent.preferred_action_types)))
    if intent.off_ball_priorities:
        checks.append(bool(intentions.intersection(intent.off_ball_priorities)))
    if intent.preferred_player_ids:
        checks.append(bool(involved_players.intersection(intent.preferred_player_ids)))
    if intent.preferred_space_ids:
        uses_preferred_space = bool(
            target_spaces.intersection(intent.preferred_space_ids)
        )
        checks.append(uses_preferred_space)
        if not uses_preferred_space:
            return PlanEvaluation(
                goalScored=True,
                instructionAlignment=0,
                reasons=[
                    "The scoring sequence did not use a preferred space: "
                    + ", ".join(intent.preferred_space_ids)
                    + "."
                ],
            )
    alignment = sum(checks) / len(checks) if checks else 1.0
    reasons = [] if alignment >= 0.5 else [
        "The scoring sequence did not use enough preferred actions, players, spaces, "
        "or off-ball priorities."
    ]
    return PlanEvaluation(
        goalScored=True,
        instructionAlignment=alignment,
        reasons=reasons,
    )
