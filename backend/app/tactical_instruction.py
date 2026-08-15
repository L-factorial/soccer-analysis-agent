from dataclasses import dataclass, replace
import re

from app.phases import PhaseScoringPolicy, PhaseSearchPolicy


@dataclass(frozen=True, slots=True)
class TacticalInstructionPolicy:
    search: PhaseSearchPolicy
    scoring: PhaseScoringPolicy
    applied_directives: tuple[str, ...]


def interpret_tactical_instruction(
    instruction: str | None,
    search: PhaseSearchPolicy,
    scoring: PhaseScoringPolicy = PhaseScoringPolicy(),
) -> TacticalInstructionPolicy:
    """Translate a small, deterministic tactical vocabulary into planner weights."""
    words = set(re.findall(r"[a-z]+", (instruction or "").lower()))
    directives: list[str] = []

    if words.intersection(("quick", "quickly", "fast", "direct", "tempo")):
        search = replace(search, score_discount=0.82)
        scoring = replace(scoring, duration_penalty_weight=20)
        directives.append("FAST_TEMPO")

    if words.intersection(("safe", "safely", "patient", "possession", "retain")):
        scoring = replace(
            scoring,
            possession_weight=55,
            duration_penalty_weight=min(scoring.duration_penalty_weight, 5),
        )
        directives.append("PRIORITIZE_POSSESSION")

    if words.intersection(("attack", "aggressive", "forward", "goal")):
        scoring = replace(
            scoring,
            forward_progress_weight=55,
            goal_proximity_weight=40,
            possession_weight=min(scoring.possession_weight, 25),
        )
        directives.append("ATTACK_AGGRESSIVELY")

    if words.intersection(("wide", "space", "decoy", "overload")):
        scoring = replace(scoring, coordination_weight=20)
        directives.append("CREATE_SPACE")

    return TacticalInstructionPolicy(
        search=search,
        scoring=scoring,
        applied_directives=tuple(dict.fromkeys(directives)),
    )
