"""Public boundary for deterministic soccer planning.

HTTP handlers and other delivery mechanisms should enter the game engine through
this package instead of assembling analysis, search, and solution-selection
steps themselves.
"""

from app.game_engine.config import default_phase_search_policy
from app.game_engine.instructions import (
    TacticalInstructionPolicy,
    interpret_tactical_instruction,
)
from app.game_engine.service import (
    GameEnginePlan,
    PossessionNotControlledError,
    SoccerGameEngine,
)
from app.game_engine.solutions import (
    select_distinct_solutions,
    sequence_tactical_signature,
)

__all__ = [
    "GameEnginePlan",
    "PossessionNotControlledError",
    "SoccerGameEngine",
    "TacticalInstructionPolicy",
    "default_phase_search_policy",
    "interpret_tactical_instruction",
    "select_distinct_solutions",
    "sequence_tactical_signature",
]
