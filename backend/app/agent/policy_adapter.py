from dataclasses import dataclass, replace

from app.agent.models import TacticalIntent, TacticalObjective, TacticalTempo
from app.phases import PhaseScoringPolicy, PhaseSearchPolicy


@dataclass(frozen=True, slots=True)
class AdaptedPolicies:
    search: PhaseSearchPolicy
    scoring: PhaseScoringPolicy


def adapt_intent_to_policies(
    intent: TacticalIntent,
    search: PhaseSearchPolicy,
) -> AdaptedPolicies:
    """Map bounded semantic intent into deterministic numeric policy."""
    scoring = PhaseScoringPolicy()
    if intent.tempo == TacticalTempo.FAST:
        search = replace(search, score_discount=0.82)
        scoring = replace(scoring, duration_penalty_weight=20)
    elif intent.tempo == TacticalTempo.PATIENT:
        scoring = replace(scoring, duration_penalty_weight=4)

    if intent.objective == TacticalObjective.RETAIN_POSSESSION:
        scoring = replace(scoring, possession_weight=55)
    elif intent.objective == TacticalObjective.FAST_ATTACK:
        scoring = replace(
            scoring,
            forward_progress_weight=55,
            goal_proximity_weight=40,
            possession_weight=25,
        )
    elif intent.objective in {
        TacticalObjective.CREATE_SPACE,
        TacticalObjective.WIDE_OVERLOAD,
    }:
        scoring = replace(scoring, coordination_weight=20)

    # Risk modifies preference, never legality or rule enforcement.
    scoring = replace(
        scoring,
        possession_weight=max(10, scoring.possession_weight * (1.3 - intent.risk_level)),
        forward_progress_weight=scoring.forward_progress_weight * (
            0.8 + 0.4 * intent.risk_level
        ),
        preferred_action_types=tuple(intent.preferred_action_types),
        preferred_player_ids=tuple(intent.preferred_player_ids),
        preferred_space_ids=tuple(intent.preferred_space_ids),
        preferred_off_ball_intentions=tuple(intent.off_ball_priorities),
    )
    return AdaptedPolicies(search=search, scoring=scoring)
