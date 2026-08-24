"""Application-neutral orchestration of the deterministic soccer engine."""

from dataclasses import dataclass

from app.domain import GameState, PossessionStatus
from app.game_engine.config import default_phase_search_policy
from app.game_engine.instructions import (
    TacticalInstructionPolicy,
    interpret_tactical_instruction,
)
from app.game_engine.solutions import select_distinct_solutions
from app.phases import (
    PhaseSearchNode,
    PhaseSearchPolicy,
    PhaseSearchResult,
    search_tactical_phases,
)
from app.planning import AnalyzedGameState, analyze_game_state


class PossessionNotControlledError(ValueError):
    """Raised when no single attacking team can safely start a search."""


@dataclass(frozen=True, slots=True)
class GameEnginePlan:
    """Engine output before presentation scheduling is applied.

    `selected_solutions` contains only goal-scoring routes. It may be empty when
    the bounded search completed successfully but did not reach a goal; callers
    can then expose `search_result.diagnostics` without losing engine telemetry.
    """

    analyzed_root: AnalyzedGameState
    search_result: PhaseSearchResult
    selected_solutions: tuple[PhaseSearchNode, ...]
    instruction_policy: TacticalInstructionPolicy

    @property
    def primary_solution(self) -> PhaseSearchNode | None:
        return self.selected_solutions[0] if self.selected_solutions else None


class SoccerGameEngine:
    """Analyze one immutable field state and search for routes to goal.

    The engine owns tactical decisions through solution selection. It does not
    know about FastAPI, HTTP errors, JSON aliases, animation timestamps, or
    commentary. Those are adapters around this boundary.
    """

    def __init__(self, search_policy: PhaseSearchPolicy | None = None) -> None:
        self._search_policy = search_policy or default_phase_search_policy()

    def plan(
        self,
        initial_state: GameState,
        tactical_instruction: str | None = None,
    ) -> GameEnginePlan:
        """Return distinct scoring routes found within configured search bounds."""
        analyzed = analyze_game_state(initial_state)
        if analyzed.game_state.possession.status != PossessionStatus.CONTROLLED:
            raise PossessionNotControlledError(
                "A single player must unambiguously control the ball"
            )

        instruction_policy = interpret_tactical_instruction(
            tactical_instruction,
            self._search_policy,
        )
        search_result = search_tactical_phases(
            analyzed,
            instruction_policy.search,
            scoring_policy=instruction_policy.scoring,
        )
        attacking_team_id = analyzed.game_state.possession.team_id
        scoring_sequences = tuple(
            sequence
            for sequence in search_result.best_sequences
            if sequence.analyzed_state.game_state.scoring_team_id
            == attacking_team_id
        )
        selected_solutions = (
            select_distinct_solutions(
                scoring_sequences[0],
                scoring_sequences[1:],
                self._search_policy.maximum_solution_count,
            )
            if scoring_sequences
            else ()
        )
        return GameEnginePlan(
            analyzed_root=analyzed,
            search_result=search_result,
            selected_solutions=selected_solutions,
            instruction_policy=instruction_policy,
        )
